"""Who is calling: people (Entra ID app roles) and agents (managed identities).

In the sandbox a person picks who they are on the sign-in screen and the browser sends that id in
the X-Brain-User header. With BRAIN_AUTH=entra the API instead validates the Entra ID token
(OpenID Connect, signature checked against the tenant's keys) and reads the app roles from it.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

# Human roles, as Entra ID app roles. Matches the access table in the architecture document.
ROLES = {
    "specialist": "Sales specialist",
    "back_office": "Back office",
    "team_lead": "Team lead",
    "content": "Product and content",
    "admin": "Admin",
}

# What each role may do through the API. The tool server has its own, finer table for agents.
PERMISSIONS = {
    "requests.own": {"specialist", "team_lead"},
    "requests.all": {"team_lead", "back_office"},
    "requests.reassign": {"team_lead"},
    "drafts.approve_customer": {"specialist"},          # only on own requests
    "drafts.approve_partner": {"back_office"},
    "knowledge.search": {"specialist", "back_office", "team_lead", "content"},
    "knowledge.approve": {"content", "team_lead"},
    "knowledge.edit": {"content"},
    "team.metrics": {"team_lead", "admin"},
    "backoffice.board": {"back_office", "team_lead"},
    "triage.run": {"specialist", "team_lead", "back_office", "admin"},
    "jobs.run": {"admin", "team_lead", "back_office"},
    "audit.read": {"admin", "team_lead"},
    "maintenance": {"admin"},
    "users.manage": {"admin", "team_lead"},
    "content.break_glass": {"admin"},
    "sandbox.reset": {"admin"},
}


@dataclass(frozen=True)
class Principal:
    id: str
    name: str
    roles: frozenset[str]
    team_id: str | None = None
    kind: str = "human"  # human | agent

    def can(self, permission: str) -> bool:
        return bool(self.roles & PERMISSIONS.get(permission, set()))


# Agents, each with only the tools it needs (least privilege). "draft" tools write drafts, never send.
AGENTS: dict[str, set[str]] = {
    "agent:triage": {"ts.read_mail", "ts.read_relation", "ts.list_trips"},
    "agent:proposal_writer": {"ts.read_relation", "ts.read_trip", "knowledge.search", "calc.quote", "examples.search",
                              "ts.draft_reisplan"},
    "agent:change": {"ts.read_mail", "ts.read_relation", "ts.read_trip", "calc.quote"},
    "agent:follow_up": {"ts.read_relation", "ts.read_trip", "knowledge.search"},
    "agent:partner_desk": {"ts.read_trip", "ts.read_relation", "partners.list", "partners.read_reply"},
    "agent:galileo_helper": {"ts.read_relation", "ts.read_trip", "galileo.write_commands"},
    "agent:knowledge_desk": {"knowledge.search"},
    "agent:supplier_watcher": {"partners.list", "prices.read"},
    "agent:customer_insight": {"stats.requests"},
    "agent:team_insight": {"stats.requests"},
    "agent:trip_monitor": {"ts.list_trips", "travel.flight_status", "ts.read_relation"},
}


def agent(name: str) -> Principal:
    pid = name if name.startswith("agent:") else f"agent:{name}"
    if pid not in AGENTS:
        raise KeyError(f"Unknown agent {pid}")
    return Principal(id=pid, name=pid, roles=frozenset(), kind="agent")


def from_employee(e) -> Principal:
    return Principal(id=e.id, name=e.name, roles=frozenset({e.role}), team_id=e.team_id)


def auth_mode() -> str:
    return os.getenv("BRAIN_AUTH", "sandbox")


@dataclass
class EntraConfig:
    tenant_id: str = field(default_factory=lambda: os.getenv("ENTRA_TENANT_ID", ""))
    client_id: str = field(default_factory=lambda: os.getenv("ENTRA_CLIENT_ID", ""))

    @property
    def issuer(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant_id}/v2.0"

    @property
    def jwks_url(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant_id}/discovery/v2.0/keys"


def verify_entra_token(token: str, cfg: EntraConfig, jwks_client=None) -> dict:
    """Validate an Entra ID access token: signature, issuer, audience, expiry. Returns the claims.

    The app roles arrive in the "roles" claim; the object id in "oid". Tested in the sandbox with a
    locally generated key; in Azure it uses the tenant's published keys.
    """
    import jwt
    jwks_client = jwks_client or jwt.PyJWKClient(cfg.jwks_url)
    key = jwks_client.get_signing_key_from_jwt(token).key
    return jwt.decode(token, key, algorithms=["RS256"], audience=cfg.client_id, issuer=cfg.issuer,
                      options={"require": ["exp", "iss", "aud", "oid"]})
