"""Shared plumbing for every agent.

run_step(): one model step with a typed output. It picks the model tier for the task, checks the daily
budget, builds the prompt from the three layers (house, agent, task context), masks personal data
before the model sees it and puts it back afterwards, falls back to the next model if one fails, and
logs the model call (tier, model, prompt version, tokens, cost) under the current trace.

audit(): one AgentRun per run with a trace id; refuses to run when the agent is paused.
"""
from __future__ import annotations

import contextvars
import json
import os
import re
import time
from contextlib import contextmanager
from typing import Any, TypeVar

from pydantic import BaseModel
from pydantic_ai import Agent
from sqlalchemy.orm import Session

from ..db import AgentRun, ModelCall, Setting
from ..models import build_model
from ..router import check_budget, model_for, price, tier_for
from ..trace import current_trace, end_trace, start_trace

T = TypeVar("T", bound=BaseModel)
_depth: contextvars.ContextVar[int] = contextvars.ContextVar("audit_depth", default=0)
_calls: contextvars.ContextVar[list | None] = contextvars.ContextVar("model_calls", default=None)


class AgentPaused(RuntimeError):
    pass


TRANSIENT_RETRIES = int(os.getenv("BRAIN_MODEL_TRANSIENT_RETRIES", "2"))
TRANSIENT = re.compile(r"status_code: (429|500|502|503|504)\b|timed out|Timeout|overloaded|high demand", re.I)


def _with_transient_retries(call, name: str = ""):
    """A busy provider answers 429, 500 or 503 now and then (Google's Gemma API did so on 25 of 84 calls). Wait and
    try again a couple of times before counting it as a failure or moving on to the fallback model."""
    tries = TRANSIENT_RETRIES if name.startswith("openai:") else 0  # hosted only: a local model that times out is not busy
    for attempt in range(tries + 1):
        try:
            return call()
        except Exception as e:  # noqa: BLE001
            if attempt == tries or not TRANSIENT.search(str(e)):
                raise
            time.sleep(min(30, 3 * 3 ** attempt))  # 3 s, then 9 s


def run_step(s: Session, task: str, output_type: type[T], instructions: str, context: dict,
             tier: str | None = None, escalated: bool = False) -> tuple[T, str]:
    from .. import prompts
    from ..guardrails import Pseudonymiser
    tier = tier or tier_for(task)
    check_budget(s)
    system, version = prompts.build(task, instructions)
    masker = Pseudonymiser()
    masked = masker.mask(context)
    prompt = "CONTEXT:\n" + json.dumps(masked, ensure_ascii=False, default=str, indent=1)
    last_error = None
    models = model_for(tier)
    healthy = [m for m in models if not circuit_open(s, m)] or models[-1:]  # skip a model that keeps failing
    models = healthy
    for i, name in enumerate(models):
        t0 = time.perf_counter()
        call = ModelCall(trace_id=current_trace(), task=task, tier=tier, model=name, prompt_version=version,
                         escalated=escalated, fallback_from=models[i - 1] if i else None)
        try:
            agent = Agent(build_model(name), output_type=output_type, instructions=system,
                          retries=OUTPUT_RETRIES,  # a malformed answer is sent back to the model to fix
                          model_settings={"timeout": MODEL_TIMEOUT, "temperature": 0.2})
            result = _with_transient_retries(lambda: agent.run_sync(prompt), name)
            usage = result.usage
            usage = usage if hasattr(usage, "input_tokens") else usage()
            call.tokens_in = int(getattr(usage, "input_tokens", 0) or 0)
            call.tokens_out = int(getattr(usage, "output_tokens", 0) or 0)
            call.cost_eur = price(name, call.tokens_in, call.tokens_out)
            out = output_type.model_validate(masker.unmask(result.output.model_dump()))
            return out, name
        except Exception as e:  # noqa: BLE001  try the next model
            call.ok = False
            last_error = e
        finally:
            call.ms = int((time.perf_counter() - t0) * 1000)
            s.add(call)
            s.flush()
            if _calls.get() is not None:
                _calls.get().append({c.name: getattr(call, c.name) for c in call.__table__.columns if c.name != "id"})
    raise RuntimeError(f"All models failed for {task}: {last_error}")


import os as _os

MODEL_TIMEOUT = float(_os.getenv("BRAIN_MODEL_TIMEOUT", "60"))
OUTPUT_RETRIES = int(_os.getenv("BRAIN_OUTPUT_RETRIES", "2"))
BREAKER_FAILURES, BREAKER_MINUTES = 5, 5


def circuit_open(s: Session, model: str) -> bool:
    """After 5 failed calls to a model in 5 minutes, stop sending it work for a while and use the fallback."""
    from datetime import timedelta
    from ..clock import utcnow
    since = utcnow() - timedelta(minutes=BREAKER_MINUTES)
    recent = s.query(ModelCall).filter(ModelCall.model == model, ModelCall.created_at >= since).order_by(ModelCall.id.desc()).limit(BREAKER_FAILURES).all()
    return len(recent) >= BREAKER_FAILURES and not any(c.ok for c in recent)


def is_paused(s: Session, agent: str) -> bool:
    st = s.get(Setting, f"paused:{agent}")
    return bool(st and st.value)


@contextmanager
def audit(s: Session, agent: str, subject: str | None, input_summary: str = ""):
    """One AgentRun row per run, with a trace id, also when it fails.

    The outermost run is one transaction: inside it, s.commit() only flushes. If the agent fails, everything it
    wrote is rolled back, and only the run record and its model calls (so cost is never lost) are saved. A retry
    then starts from a clean state. Nested runs (an agent calling another) share the outer transaction.
    """
    if is_paused(s, agent):
        raise AgentPaused(f"Agent {agent} is paused on the maintenance screen")
    from ..config import get_settings
    depth = _depth.get()
    outer = depth == 0
    tid, token = start_trace()
    dtoken = _depth.set(depth + 1)
    ctoken = _calls.set([]) if outer else None
    if outer:
        real_commit = s.commit
        s.commit = s.flush  # type: ignore[method-assign]
    run = AgentRun(agent=agent, model=get_settings().model, subject=subject, input_summary=input_summary[:500], trace_id=tid)
    t0 = time.perf_counter()
    box: dict[str, Any] = {"sources": [], "output": ""}
    failed: BaseException | None = None
    try:
        yield box
    except BaseException as e:  # noqa: BLE001
        failed = e
        run.ok = False
        run.error = f"{type(e).__name__}: {e}"[:1000]
        raise
    finally:
        run.ms = int((time.perf_counter() - t0) * 1000)
        run.sources = box["sources"]
        run.output_summary = str(box["output"])[:500]
        end_trace(token)
        _depth.reset(dtoken)
        if outer:
            del s.commit  # back to the real commit
            calls = _calls.get() or []
            _calls.reset(ctoken)
            run.cost_eur = round(sum(c["cost_eur"] or 0 for c in calls), 6)
            if calls:
                run.model = ",".join(sorted({c["model"] for c in calls if c["ok"]}) or {calls[-1]["model"]})
            if failed is not None:
                s.rollback()
                for c in calls:  # cost and failures are kept even when the work is undone
                    s.add(ModelCall(**c))
                from ..toolserver import keep_failed_calls
                keep_failed_calls(s)
            _export_langfuse(run, [ModelCall(**c) for c in calls])
            s.add(run)
            real_commit()
        else:
            s.add(run)
            s.flush()

def _export_langfuse(run: AgentRun, calls: list[ModelCall]) -> None:
    """Send the trace to Langfuse when configured. Only masked summaries and numbers, never raw content."""
    from ..trace import langfuse
    lf = langfuse()
    if lf is None:
        return
    try:  # pragma: no cover - needs a Langfuse server
        lf.trace(id=run.trace_id, name=run.agent, metadata={"subject": run.subject, "ok": run.ok, "ms": run.ms},
                 output=run.output_summary[:200])
        for c in calls:
            lf.generation(trace_id=run.trace_id, name=c.task, model=c.model,
                          usage={"input": c.tokens_in, "output": c.tokens_out}, metadata={"tier": c.tier, "prompt": c.prompt_version,
                                                                                         "cost_eur": c.cost_eur, "ok": c.ok})
    except Exception:  # noqa: BLE001  tracing must never break an agent
        pass
