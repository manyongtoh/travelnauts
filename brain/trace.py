"""Trace context: one trace id per agent run, shared by its tool calls and model calls.

Locally the trace lives in Postgres (agent_runs, tool_calls, model_calls). With LANGFUSE_HOST and keys
set, the same spans are also sent to Langfuse (self-hosted in Azure), after PII masking.
"""
from __future__ import annotations

import contextvars
import os
import uuid

_trace: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace", default=None)


def current_trace() -> str | None:
    return _trace.get()


def start_trace() -> tuple[str, contextvars.Token]:
    tid = uuid.uuid4().hex[:16]
    return tid, _trace.set(tid)


def end_trace(token: contextvars.Token) -> None:
    _trace.reset(token)


def langfuse():
    """Return a Langfuse client when configured, else None. Optional dependency."""
    if not os.getenv("LANGFUSE_HOST"):
        return None
    try:
        from langfuse import Langfuse  # type: ignore
    except ImportError:
        return None
    return Langfuse()
