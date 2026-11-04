"""Model router: a fixed model tier per task, fallback when a model fails, a daily budget.

Routing is by rule, as the architecture says: small model for easy work, large model for offers and
hard customer mails, escalation to large when the small model is unsure or a check in code fails.
In Azure the same table lives in LiteLLM; here it is plain code so it runs offline.

  BRAIN_MODEL_SMALL / BRAIN_MODEL_LARGE   model per tier (default: BRAIN_MODEL, else the sandbox stand-in)
  BRAIN_MODEL_FALLBACK                    comma separated models to try when the tier's model fails
  BRAIN_DAILY_BUDGET_EUR                  hard cap per day per environment (maintenance screen can lower it)
"""
from __future__ import annotations

import os
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import ModelCall, Setting
from .clock import utcnow

TASK_TIER = {
    "triage": "small", "followup": "small", "partner_request": "small", "partner_chase": "small",
    "partner_reply": "small", "galileo": "small", "answer": "small", "change_plan": "small",
    "supplier_note": "small", "trip_alert": "small",
    "extras": "small", "call_notes": "small", "invoice_extract": "small",
    "proposal": "large", "change_reply": "large", "complaint_reply": "large", "alternatives": "large",
    "next_trip": "large", "roadbook_intro": "large",
}

# EUR per million tokens (input, output). Estimates; replace with the contract prices.
PRICES = {
    "sandbox": (0.0, 0.0),
    "ollama:": (0.0, 0.0),
    "openai:gpt-4o-mini": (0.15, 0.60),
    "openai:gpt-4o": (2.30, 9.20),
    "openai:mistral-large": (1.80, 5.50),
}


class BudgetExceeded(RuntimeError):
    pass


def model_for(tier: str) -> list[str]:
    base = os.getenv("BRAIN_MODEL", "sandbox")
    first = os.getenv(f"BRAIN_MODEL_{tier.upper()}", base)
    fallback = [m.strip() for m in os.getenv("BRAIN_MODEL_FALLBACK", "").split(",") if m.strip()]
    return [first] + [m for m in fallback if m != first]


def tier_for(task: str) -> str:
    return TASK_TIER.get(task, "small")


def price(model: str, tokens_in: int, tokens_out: int) -> float:
    p = PRICES.get(model) or next((v for k, v in PRICES.items() if k.endswith(":") and model.startswith(k)), (0.0, 0.0))
    return round((tokens_in * p[0] + tokens_out * p[1]) / 1_000_000, 6)


def daily_cap(s: Session) -> float:
    st = s.get(Setting, "budget_cap_eur")
    if st is not None:
        return float(st.value)
    return float(os.getenv("BRAIN_DAILY_BUDGET_EUR", "5"))


def spent_today(s: Session) -> float:
    start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return float(s.scalar(select(func.coalesce(func.sum(ModelCall.cost_eur), 0.0)).where(ModelCall.created_at >= start)) or 0.0)


def check_budget(s: Session) -> None:
    if spent_today(s) >= daily_cap(s):
        raise BudgetExceeded(f"Daily model budget of EUR {daily_cap(s):.2f} reached; agents pause until tomorrow")
