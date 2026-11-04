"""Settings, read from environment variables (see .env.example).

The sandbox runs without any network access by default:
  BRAIN_MODEL=sandbox       deterministic stand-in model, no network
  BRAIN_MODEL=ollama:gemma4 a local Gemma model through Ollama
  BRAIN_MODEL=openai:<name> any OpenAI compatible endpoint (BRAIN_MODEL_BASE_URL)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DATA_STAGES = ("synthetic", "anonymised", "live")


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: os.getenv("BRAIN_DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'brain.db'}"))
    model: str = field(default_factory=lambda: os.getenv("BRAIN_MODEL", "sandbox"))
    triage_model: str = field(default_factory=lambda: os.getenv("BRAIN_TRIAGE_MODEL", os.getenv("BRAIN_MODEL", "sandbox")))
    model_base_url: str = field(default_factory=lambda: os.getenv("BRAIN_MODEL_BASE_URL", "http://localhost:11434/v1"))
    model_api_key: str = field(default_factory=lambda: os.getenv("BRAIN_MODEL_API_KEY", "ollama"))
    data_stage: str = field(default_factory=lambda: os.getenv("BRAIN_DATA_STAGE", "synthetic"))
    travelspirit_mode: str = field(default_factory=lambda: os.getenv("BRAIN_TRAVELSPIRIT", "fake"))
    travelspirit_write: str = field(default_factory=lambda: os.getenv("BRAIN_TRAVELSPIRIT_WRITE", "drafts"))
    seed: int = field(default_factory=lambda: int(os.getenv("BRAIN_SEED", "42")))
    # Days after which the follow-up agent drafts a reminder, and the partner desk chases.
    followup_after_days: int = 5
    chase_partner_after_days: int = 3

    def check(self) -> None:
        if self.data_stage not in DATA_STAGES:
            raise ValueError(f"BRAIN_DATA_STAGE must be one of {DATA_STAGES}")
        if self.data_stage == "live":
            raise RuntimeError(
                "Live data is not allowed in the sandbox. Live use needs the go-live approval "
                "from Inge and Jonas, the pentest, the DPIA and the updated privacy texts."
            )
        if self.travelspirit_write not in ("off", "drafts"):
            raise ValueError("BRAIN_TRAVELSPIRIT_WRITE must be 'off' or 'drafts'; agents never write final records")


def get_settings() -> Settings:
    s = Settings()
    s.check()
    return s
