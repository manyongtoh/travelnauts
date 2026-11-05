"""Autonomy levels: how far an agent may go on its own with a piece of work.

  1  draft: the agent drafts, a person approves. The default for every task, and always for anything with money.
  2  act and sample: it goes out by itself after a short hold with a Stop button (automatic send, earned per
     person and kind after ten unchanged approvals, see autosend.py).
  3  act: a person handles only the exceptions. Not used yet.

Every Draft and Job carries its level (autonomy_level, default 1). The ceiling is the lowest of: the tenant's
autonomy_max (tenant.toml), the ceiling for the kind of work below, and what a person has switched on.
"""
from __future__ import annotations

DRAFT, ACT_AND_SAMPLE, ACT = 1, 2, 3
LEVELS = {DRAFT: "draft, a person approves", ACT_AND_SAMPLE: "sent by itself after a hold with Stop",
          ACT: "acts, a person handles exceptions"}

# The highest level a kind of work can ever reach. Anything not listed (proposals, changes, answers, complaint
# replies, alternatives, roadbooks, anything with money) stays at level 1.
KIND_CEILING = {"followup": ACT_AND_SAMPLE, "extras": ACT_AND_SAMPLE, "partner_request": ACT_AND_SAMPLE,
                "partner_chase": ACT_AND_SAMPLE}


def ceiling(kind: str) -> int:
    from .tenant import tenant
    return min(tenant().autonomy_max, KIND_CEILING.get(kind, DRAFT))


def may_act_alone(kind: str) -> bool:
    return ceiling(kind) >= ACT_AND_SAMPLE
