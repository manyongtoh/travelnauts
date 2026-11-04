"""Test, pilot and live: same code, different configuration, rules checked at start-up.

  BRAIN_ENV=test    synthetic data only, fake or recorded TravelSpirit, drafts in the brain
  BRAIN_ENV=pilot   anonymised data, TravelSpirit read-only user, no writing, Entra ID sign-in
  BRAIN_ENV=live    real customer data, draft-write API user, Entra ID sign-in (refused in this sandbox)

Each environment has its own resource group, database, Key Vault and Entra app registration (see infra/).
The checks below stop a misconfiguration from mixing them, for example a test key in live.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

PROFILES = {
    "test": {"data_stage": "synthetic", "travelspirit_write": {"off", "drafts"}, "auth": {"sandbox", "entra"},
             "can_reach_customers": False},
    "pilot": {"data_stage": "anonymised", "travelspirit_write": {"off"}, "auth": {"entra"}, "can_reach_customers": False},
    "live": {"data_stage": "live", "travelspirit_write": {"drafts"}, "auth": {"entra"}, "can_reach_customers": True},
}


@dataclass
class EnvCheck:
    env: str
    ok: bool
    problems: list[str]


def check(env: str | None = None, environ: dict | None = None) -> EnvCheck:
    e = environ if environ is not None else os.environ
    env = env or e.get("BRAIN_ENV", "test")
    if env not in PROFILES:
        return EnvCheck(env, False, [f"Unknown BRAIN_ENV {env!r}"])
    p = PROFILES[env]
    problems = []
    stage = e.get("BRAIN_DATA_STAGE", "synthetic")
    if stage != p["data_stage"]:
        problems.append(f"{env} needs BRAIN_DATA_STAGE={p['data_stage']}, not {stage}")
    write = e.get("BRAIN_TRAVELSPIRIT_WRITE", "drafts")
    if write not in p["travelspirit_write"]:
        problems.append(f"{env} allows TravelSpirit write {sorted(p['travelspirit_write'])}, not {write}")
    auth = e.get("BRAIN_AUTH", "sandbox")
    if auth not in p["auth"]:
        problems.append(f"{env} needs sign-in {sorted(p['auth'])}, not {auth}")
    kv = e.get("AZURE_KEYVAULT_NAME", "")
    if kv and env not in kv:
        problems.append(f"Key Vault {kv!r} does not belong to {env}: every environment has its own secrets")
    db = e.get("BRAIN_DATABASE_URL", "")
    for other in PROFILES:
        if other != env and f"brain-{other}" in db:
            problems.append(f"Database URL points at the {other} environment")
    if env != "test" and e.get("BRAIN_MODEL", "sandbox") == "sandbox":
        problems.append(f"{env} must use a real model, not the sandbox stand-in")
    return EnvCheck(env, not problems, problems)
