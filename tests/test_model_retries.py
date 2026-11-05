"""A busy hosted model (429/500/503) is tried again before it counts as failed; other errors are not retried."""
import pytest


def test_transient_errors_are_retried(monkeypatch):
    from brain.agents import common
    monkeypatch.setattr(common.time, "sleep", lambda s: None)
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("status_code: 503, model_name: gemma-4-31b-it, body: high demand")
        return "ok"
    assert common._with_transient_retries(flaky, "openai:gemma-4-31b-it") == "ok" and len(calls) == 3

    calls.clear()

    def broken():
        calls.append(1)
        raise ValueError("schema mismatch")
    with pytest.raises(ValueError):
        common._with_transient_retries(broken, "openai:gemma-4-31b-it")
    assert len(calls) == 1
    calls.clear()
    with pytest.raises(RuntimeError):
        common._with_transient_retries(lambda: (calls.append(1), (_ for _ in ()).throw(RuntimeError("status_code: 500")))[1], "ollama:gemma4:e4b")
    assert len(calls) == 1  # a local model is not retried: it is not busy, it is slow


def test_repeated_line_is_flagged():
    from brain.guardrails import check_output
    line = "Halong Bay (3 nachten): jullie slapen in Bai Tu Long Family Junk."
    assert any("repeated" in p for p in check_output(f"Beste Wouter,\n\n{line}\n{line}\n"))
    assert not check_output(f"Beste Wouter,\n\n{line}\n")
