"""The tenant: everything that makes this brain one company's brain, loaded from a tenant pack.

The core knows no client. A client repo (for example acme-brain) registers a tenant pack under the
entry point group `brain.tenants`; the core ships one invented sample tenant, Wolkenwaai Reizen, for tests and
demos. BRAIN_TENANT picks the pack by name; with one pack installed besides the sample, that one is used.

A pack is validated when it loads, so a mistake in a client's configuration stops the brain at start-up instead
of showing up in a mail to a family.

    [project.entry-points."brain.tenants"]
    acme = "acme_brain:pack"
"""
from __future__ import annotations

import contextvars
import os
import re
import tomllib
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import lru_cache
from importlib.metadata import entry_points
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Iterator, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

GROUP = "brain.tenants"
SAMPLE = "wolkenwaai"
SLUG = r"^[a-z][a-z0-9-]{1,30}$"


class PricingTemplate(BaseModel):
    """The calculation template: margin on cost per kind of line, as a fraction (0.22 = 22%)."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    margins: dict[str, float] = Field(min_length=1)
    default_margin: float = Field(0.2, ge=0, lt=1)

    @field_validator("margins")
    @classmethod
    def _range(cls, v: dict[str, float]) -> dict[str, float]:
        bad = {k: m for k, m in v.items() if not 0 <= m < 1}
        if bad:
            raise ValueError(f"margins must be fractions between 0 and 1, got {bad}")
        return v

    def margin(self, kind: str) -> float:
        return self.margins.get(kind, self.default_margin)


class TenantConfig(BaseModel):
    """One company's settings. Every field is checked when the pack loads."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant_id: str = Field(pattern=SLUG, description="stable id, stored on every row")
    name: str = Field(min_length=2, description="the company name as families and partners see it")
    own_domains: list[str] = Field(min_length=1, description="mail domains of the company itself")
    name_words: list[str] = Field(default_factory=list,
                                  description="words that are never a person's name (the company name is added)")
    back_office_signature: str = ""
    emergency_line: str = Field(min_length=6)
    reference_prefix: str = Field(pattern=r"^[A-Z]{2,4}$", description="booking references read <prefix>-R012")
    galileo_agency_remark: str = Field(pattern=r"^P\.[A-Z]{4}\*[A-Z0-9]+$",
                                       description="the agency phone remark in Galileo, for example P.AMSB*NAME")
    autonomy_max: int = Field(2, ge=1, le=3, description="highest autonomy level any agent may reach here")
    pricing: PricingTemplate

    @field_validator("own_domains")
    @classmethod
    def _domains(cls, v: list[str]) -> list[str]:
        out = [d.strip().lower() for d in v]
        bad = [d for d in out if not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", d)]
        if bad:
            raise ValueError(f"not a mail domain: {bad}")
        return out

    @model_validator(mode="after")
    def _defaults(self) -> "TenantConfig":
        words = {w.lower() for w in self.name_words} | {w.lower() for w in re.findall(r"[\w-]+", self.name)}
        object.__setattr__(self, "name_words", sorted(words))
        if not self.back_office_signature:
            object.__setattr__(self, "back_office_signature", f"{self.name} back office")
        return self

    @property
    def short_name(self) -> str:
        """The name as it is signed in mails: 'Wolkenwaai' for 'Wolkenwaai Reizen'."""
        return self.name.split()[0]

    def is_own_domain(self, domain: str) -> bool:
        return domain.lower() in self.own_domains

    def reference(self, request_id: str) -> str:
        """Our booking reference for a trip request: 'r012' -> 'WW-R012'."""
        return f"{self.reference_prefix}-{request_id.upper()}"

    @property
    def ref_re(self) -> str:
        """The prefix as a regex fragment, for finding our references in partner mails."""
        return re.escape(self.reference_prefix)


@dataclass(frozen=True)
class TenantPack:
    """What a client repo hands the core: its config, its house prompt and optional agent prompt overrides."""
    config: TenantConfig
    house_prompt: str
    agent_prompts: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.house_prompt.strip():
            raise ValueError(f"tenant {self.config.tenant_id}: the house prompt is empty")
        object.__setattr__(self, "agent_prompts", MappingProxyType(dict(self.agent_prompts)))


def pack_from_dir(path: Path | str) -> TenantPack:
    """Build a pack from a folder with tenant.toml, house.md and optionally agents/<task>.md."""
    p = Path(path)
    with open(p / "tenant.toml", "rb") as f:
        raw = tomllib.load(f)
    agents = {f.stem: f.read_text(encoding="utf-8") for f in sorted((p / "agents").glob("*.md"))} \
        if (p / "agents").is_dir() else {}
    return TenantPack(config=TenantConfig.model_validate(raw), house_prompt=(p / "house.md").read_text(encoding="utf-8"),
                      agent_prompts=agents)


def available() -> dict[str, Callable[[], TenantPack]]:
    return {ep.name: ep.load for ep in entry_points(group=GROUP)}


@lru_cache(maxsize=None)
def load(name: str | None = None) -> TenantPack:
    found = available()
    if name is None:
        name = os.getenv("BRAIN_TENANT") or None
    if name is None:
        clients = sorted(n for n in found if n != SAMPLE)
        name = clients[0] if len(clients) == 1 else SAMPLE
    if name not in found:
        raise RuntimeError(f"tenant pack {name!r} is not installed (installed: {sorted(found) or 'none'}); "
                           f"install the client repo or set BRAIN_TENANT")
    pack = found[name]()()
    if not isinstance(pack, TenantPack):
        raise TypeError(f"entry point {GROUP}:{name} must return a TenantPack")
    if pack.config.tenant_id != name:
        raise ValueError(f"entry point {name!r} returned tenant_id {pack.config.tenant_id!r}; they must match")
    return pack


def tenant() -> TenantConfig:
    return load().config


def reload() -> TenantPack:
    """Used by tests and the CLI after BRAIN_TENANT changes."""
    load.cache_clear()
    return load()


# --- The tenant a piece of work runs for ---------------------------------------------------------------------
# One deployment serves one tenant, so this is the pack's tenant_id. Tests (and a later shared deployment) can
# run work for another tenant inside `as_tenant`; the database scopes every query to it.

_current: contextvars.ContextVar[str | None] = contextvars.ContextVar("brain_tenant_id", default=None)


def current_tenant_id() -> str:
    return _current.get() or tenant().tenant_id


@contextmanager
def as_tenant(tenant_id: str) -> Iterator[str]:
    if not re.fullmatch(SLUG, tenant_id):
        raise ValueError(f"not a tenant id: {tenant_id!r}")
    token = _current.set(tenant_id)
    try:
        yield tenant_id
    finally:
        _current.reset(token)


COMPANY = "%COMPANY%"


def fill_company(obj):
    """Put the tenant's name into synthetic text written with the %COMPANY% token (strings, tuples, lists)."""
    if isinstance(obj, str):
        return obj.replace(COMPANY, tenant().short_name)
    if isinstance(obj, tuple):
        return tuple(fill_company(x) for x in obj)
    if isinstance(obj, list):
        return [fill_company(x) for x in obj]
    if isinstance(obj, dict):
        return {k: fill_company(v) for k, v in obj.items()}
    return obj
