import os

import pytest

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
os.environ["BRAIN_MODEL"] = "sandbox"
os.environ["BRAIN_TRIAGE_MODEL"] = "sandbox"


@pytest.fixture()
def world(tmp_path):
    from brain import db
    from brain.synth.generate import build
    os.environ["BRAIN_VAULT"] = str(tmp_path / "vault")
    os.environ["BRAIN_FILES"] = str(tmp_path / "files")
    db.reset_engine(f"sqlite:///{tmp_path / 'test.db'}")
    build(seed=7, n_families=60, hard=False)
    with db.session() as s:
        yield s
    db.reset_engine()
