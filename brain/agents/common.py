"""Shared plumbing for every agent.

run_step(): one model step with a typed output. It picks the model tier for the task, checks the daily
budget, builds the prompt from the three layers (Travelnauts, agent, task context), masks personal data
before the model sees it and puts it back afterwards, falls back to the next model if one fails, and
logs the model call (tier, model, prompt version, tokens, cost) under the current trace.

audit(): one AgentRun per run with a trace id; refuses to run when the agent is paused.
"""
from __future__ import annotations

import json
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


class AgentPaused(RuntimeError):
    pass


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
    for i, name in enumerate(models):
        t0 = time.perf_counter()
        call = ModelCall(trace_id=current_trace(), task=task, tier=tier, model=name, prompt_version=version,
                         escalated=escalated, fallback_from=models[i - 1] if i else None)
        try:
            agent = Agent(build_model(name), output_type=output_type, instructions=system)
            result = agent.run_sync(prompt)
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
    raise RuntimeError(f"All models failed for {task}: {last_error}")


def is_paused(s: Session, agent: str) -> bool:
    st = s.get(Setting, f"paused:{agent}")
    return bool(st and st.value)


@contextmanager
def audit(s: Session, agent: str, subject: str | None, input_summary: str = ""):
    """One AgentRun row per run, with a trace id, also when it fails."""
    if is_paused(s, agent):
        raise AgentPaused(f"Agent {agent} is paused on the maintenance screen")
    from ..config import get_settings
    tid, token = start_trace()
    run = AgentRun(agent=agent, model=get_settings().model, subject=subject, input_summary=input_summary[:500], trace_id=tid)
    t0 = time.perf_counter()
    box: dict[str, Any] = {"sources": [], "output": ""}
    try:
        yield box
    except Exception as e:  # noqa: BLE001
        run.ok = False
        run.error = f"{type(e).__name__}: {e}"[:1000]
        raise
    finally:
        run.ms = int((time.perf_counter() - t0) * 1000)
        run.sources = box["sources"]
        run.output_summary = str(box["output"])[:500]
        calls = s.query(ModelCall).filter(ModelCall.trace_id == tid).all()
        run.cost_eur = round(sum(c.cost_eur for c in calls), 6)
        if calls:
            run.model = ",".join(sorted({c.model for c in calls if c.ok}) or {calls[-1].model})
        end_trace(token)
        s.add(run)
        s.commit()
