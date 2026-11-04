"""Shared plumbing: run one model step with a typed output, and log every run.

Each agent does its own lookups in plain code first (TravelSpirit, the knowledge base, the
price list). The model only gets that context and writes or classifies. This keeps the agents
predictable and makes every answer traceable to its sources.
"""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from typing import Any, TypeVar

from pydantic import BaseModel
from pydantic_ai import Agent
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import AgentRun
from ..models import build_model

T = TypeVar("T", bound=BaseModel)

HOUSE_RULES = (
    "You work for Travelnauts, a Dutch tour operator for family trips. Write customer texts in Dutch, warm and personal, "
    "addressing the family as 'jullie'. Use only the facts in CONTEXT. Never invent prices, hotels, rules or dates. "
    "If CONTEXT does not hold the answer, say so. Do not use em dashes or en dashes. "
    "A specialist reviews everything you write before it is sent."
)


def run_step(task: str, output_type: type[T], instructions: str, context: dict, model_name: str | None = None) -> tuple[T, str]:
    name = model_name or get_settings().model
    agent = Agent(build_model(name), output_type=output_type, instructions=f"[task:{task}]\n{HOUSE_RULES}\n{instructions}")
    prompt = "CONTEXT:\n" + json.dumps(context, ensure_ascii=False, default=str, indent=1)
    result = agent.run_sync(prompt)
    return result.output, name


@contextmanager
def audit(s: Session, agent: str, subject: str | None, input_summary: str = ""):
    """Write one AgentRun row per run, also when it fails."""
    run = AgentRun(agent=agent, model=get_settings().model, subject=subject, input_summary=input_summary[:500])
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
        s.add(run)
        s.commit()
