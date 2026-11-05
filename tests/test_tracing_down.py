"""When Langfuse is down an agent still runs, and the log says tracing stopped (once, not on every run)."""
import logging
from types import SimpleNamespace


def test_tracing_failure_is_logged_once(monkeypatch, caplog):
    from brain import trace
    from brain.agents import common

    class Down:
        def trace(self, **_):
            raise ConnectionError("langfuse unreachable")

    monkeypatch.setattr(trace, "langfuse", lambda: Down())
    monkeypatch.setattr(common, "_trace_warned_at", 0.0)
    run = SimpleNamespace(trace_id="t1", agent="triage", subject="x", ok=True, ms=1, output_summary="ok")
    with caplog.at_level(logging.WARNING, logger="brain.agents"):
        common._export_langfuse(run, [])
        common._export_langfuse(run, [])
    hits = [r for r in caplog.records if "Langfuse tracing failed" in r.getMessage()]
    assert len(hits) == 1 and "unreachable" in hits[0].getMessage()
