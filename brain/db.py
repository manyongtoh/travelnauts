"""Database tables. SQLite by default, Postgres in docker-compose (same models).

Everything has a `synthetic` flag. The sandbox refuses to start on rows without it,
so real data cannot slip in by accident during the synthetic stage.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

import os

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, event, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from .config import get_settings
from .clock import utcnow


class Base(DeclarativeBase):
    pass


def now() -> datetime:
    from .clock import utcnow as _u
    return _u().replace(microsecond=0)


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # e.g. "asia"
    name: Mapped[str] = mapped_column(String)
    destinations: Mapped[list] = mapped_column(JSON, default=list)


class Employee(Base):
    __tablename__ = "employees"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)  # specialist | back_office | team_lead | content | admin
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_active: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class Family(Base):
    __tablename__ = "families"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    surname: Mapped[str] = mapped_column(String)
    contact_name: Mapped[str] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    adults: Mapped[int] = mapped_column(Integer)
    child_ages: Mapped[list] = mapped_column(JSON, default=list)
    city: Mapped[str | None] = mapped_column(String, nullable=True)
    past_destinations: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class Partner(Base):
    __tablename__ = "partners"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)  # local_agent | hotel | airline | insurer
    destination: Mapped[str] = mapped_column(String)
    email: Mapped[str] = mapped_column(String)
    avg_reply_days: Mapped[float] = mapped_column(Float, default=2.0)
    reliability: Mapped[float] = mapped_column(Float, default=0.9)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class PriceItem(Base):
    """The price list that today lives in the Excel calculation."""
    __tablename__ = "price_items"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    destination: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)  # flight | hotel | transfer | excursion | car
    name: Mapped[str] = mapped_column(String)
    stop: Mapped[str | None] = mapped_column(String, nullable=True)
    unit: Mapped[str] = mapped_column(String)  # per_person | per_room_night | per_trip | per_day
    cost_eur: Mapped[float] = mapped_column(Float)
    partner_id: Mapped[str | None] = mapped_column(ForeignKey("partners.id"), nullable=True)
    family_friendly: Mapped[bool] = mapped_column(Boolean, default=True)
    min_child_age: Mapped[int] = mapped_column(Integer, default=0)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class Mail(Base):
    """A mail in the (fake) TravelSpirit Mail inbox."""
    __tablename__ = "mails"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    received_at: Mapped[datetime] = mapped_column(DateTime)
    sender: Mapped[str] = mapped_column(String)
    subject: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text)
    family_id: Mapped[str | None] = mapped_column(ForeignKey("families.id"), nullable=True, index=True)
    partner_id: Mapped[str | None] = mapped_column(ForeignKey("partners.id"), nullable=True)
    # Ground truth, only used by the test bench, never shown to agents.
    truth: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String, default="new", index=True)  # new | triaged | done | flagged
    triage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    attachments: Mapped[list] = mapped_column(JSON, default=list)  # [{"name", "path", "mime"}]
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class TripRequest(Base):
    __tablename__ = "requests"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    family_id: Mapped[str] = mapped_column(ForeignKey("families.id"), index=True)
    mail_id: Mapped[str | None] = mapped_column(ForeignKey("mails.id"), nullable=True)
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id"), nullable=True, index=True)
    specialist_id: Mapped[str | None] = mapped_column(ForeignKey("employees.id"), nullable=True, index=True)
    destination: Mapped[str] = mapped_column(String)
    days: Mapped[int] = mapped_column(Integer)
    depart_month: Mapped[str] = mapped_column(String)
    budget_eur: Mapped[float | None] = mapped_column(Float, nullable=True)
    wishes: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String, default="new", index=True)  # new | proposal_draft | proposal_sent | booked | lost
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    proposal_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    depart_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    flights: Mapped[list] = mapped_column(JSON, default=list)
    payment_status: Mapped[str | None] = mapped_column(String, nullable=True)  # deposit | paid
    insurance: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    passports_checked: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_customer_contact: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)

    family: Mapped[Family] = relationship()


class PastProposal(Base):
    """Earlier proposals: the examples the brain learns the house style and routes from."""
    __tablename__ = "past_proposals"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    destination: Mapped[str] = mapped_column(String)
    days: Mapped[int] = mapped_column(Integer)
    party: Mapped[str] = mapped_column(String)
    route: Mapped[list] = mapped_column(JSON)  # [{"stop": "Bangkok", "nights": 3}, ...]
    text: Mapped[str] = mapped_column(Text)
    price_pp_eur: Mapped[float] = mapped_column(Float)
    booked: Mapped[bool] = mapped_column(Boolean)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class Draft(Base):
    """Anything an agent writes. Nothing leaves the building until a person approves it."""
    __tablename__ = "drafts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String, index=True)  # proposal | followup | partner_request | partner_chase | galileo | answer
    request_id: Mapped[str | None] = mapped_column(ForeignKey("requests.id"), nullable=True, index=True)
    partner_request_id: Mapped[int | None] = mapped_column(ForeignKey("partner_requests.id"), nullable=True)
    title: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String, default="draft", index=True)  # draft | approved | rejected
    final_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    edit_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String, nullable=True)


class PartnerRequest(Base):
    __tablename__ = "partner_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("requests.id"), index=True)
    partner_id: Mapped[str] = mapped_column(ForeignKey("partners.id"), index=True)
    what: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="to_send")  # to_send | waiting | chased | answered | declined
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    chased_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    offer: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    partner: Mapped[Partner] = relationship()


class KnowledgeItem(Base):
    __tablename__ = "knowledge"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text)
    destination: Mapped[str | None] = mapped_column(String, nullable=True)
    topic: Mapped[str] = mapped_column(String)  # season | family | partner | policy | house_voice | entry
    owner_id: Mapped[str] = mapped_column(ForeignKey("employees.id"))
    status: Mapped[str] = mapped_column(String, default="proposed")  # proposed | approved | archived | retired
    approved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_by: Mapped[date] = mapped_column(Date)
    version: Mapped[int] = mapped_column(Integer, default=1)
    source: Mapped[str | None] = mapped_column(String, nullable=True)  # vault path, e.g. thailand/bangkok.md#met-kinderen
    roles: Mapped[list] = mapped_column(JSON, default=lambda: ["specialist", "back_office", "team_lead", "content"])
    content_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    # A changed note waits here for approval; until then agents keep using the approved body above.
    pending_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    pending_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class KnowledgeGap(Base):
    __tablename__ = "knowledge_gaps"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(String)  # no_answer | weak_source | heavy_rewrite | outdated
    team_id: Mapped[str | None] = mapped_column(String, nullable=True)
    destination: Mapped[str | None] = mapped_column(String, nullable=True)
    count: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String, default="open")  # open | written | dismissed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class AgentRun(Base):
    """The audit log: every agent run, with inputs, sources, model and timing."""
    __tablename__ = "agent_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)
    subject: Mapped[str | None] = mapped_column(String, nullable=True)
    input_summary: Mapped[str] = mapped_column(Text, default="")
    sources: Mapped[list] = mapped_column(JSON, default=list)
    output_summary: Mapped[str] = mapped_column(Text, default="")
    ms: Mapped[int] = mapped_column(Integer, default=0)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    cost_eur: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)


class Quote(Base):
    """Every price given, with the version of the price tables it came from, so any quote is traceable."""
    __tablename__ = "quotes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str | None] = mapped_column(String, nullable=True)
    destination: Mapped[str] = mapped_column(String)
    price_version: Mapped[str] = mapped_column(String)
    sell_eur: Mapped[float] = mapped_column(Float)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class InvoiceCheck(Base):
    """A supplier invoice compared with what we agreed: match, differs or unknown."""
    __tablename__ = "invoice_checks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mail_id: Mapped[str] = mapped_column(String)
    partner_id: Mapped[str | None] = mapped_column(String, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String, nullable=True)
    invoice_no: Mapped[str | None] = mapped_column(String, nullable=True)
    amount_eur: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_eur: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String)  # match | differs | unknown
    note: Mapped[str] = mapped_column(Text, default="")
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ToolCall(Base):
    """One call through the tool server: who, which tool, how long, allowed or not. No customer content."""
    __tablename__ = "tool_calls"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    caller: Mapped[str] = mapped_column(String)
    tool: Mapped[str] = mapped_column(String)
    allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    cached: Mapped[bool] = mapped_column(Boolean, default=False)
    args_summary: Mapped[str] = mapped_column(String, default="")
    ms: Mapped[int] = mapped_column(Integer, default=0)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)


class ModelCall(Base):
    """One model call: tier, model, prompt version, tokens, cost, fallback used."""
    __tablename__ = "model_calls"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    task: Mapped[str] = mapped_column(String)
    tier: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)
    prompt_version: Mapped[str] = mapped_column(String, default="")
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_eur: Mapped[float] = mapped_column(Float, default=0.0)
    ms: Mapped[int] = mapped_column(Integer, default=0)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    fallback_from: Mapped[str | None] = mapped_column(String, nullable=True)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)


class AuditEntry(Base):
    """Append-only, hash-chained record of human decisions. Pseudonymous ids and references only."""
    __tablename__ = "audit_chain"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=now)
    actor: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    object_type: Mapped[str] = mapped_column(String)
    object_id: Mapped[str] = mapped_column(String)
    ref: Mapped[str | None] = mapped_column(String, nullable=True)
    input_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    prev_hash: Mapped[str] = mapped_column(String, unique=True)  # one successor per entry: the chain cannot fork
    hash: Mapped[str] = mapped_column(String)


class Job(Base):
    """The work queue. Agents pick up jobs; a person never waits on an agent."""
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String, default="queued", index=True)  # queued | running | done | failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    run_after: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    worker: Mapped[str | None] = mapped_column(String, nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Setting(Base):
    """Operational switches: paused agents, budget caps, last run of scheduled jobs."""
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Counter(Base):
    """Safe running numbers (request numbers), also with many workers at the same time."""
    __tablename__ = "counters"
    name: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[int] = mapped_column(Integer, default=0)


def next_number(s: Session, name: str, start_from: int = 0) -> int:
    from sqlalchemy import update
    from sqlalchemy.exc import IntegrityError
    for _ in range(5):
        res = s.execute(update(Counter).where(Counter.name == name).values(value=Counter.value + 1).returning(Counter.value)).first()
        if res:
            return int(res[0])
        try:
            with s.begin_nested():
                s.add(Counter(name=name, value=start_from))
        except IntegrityError:
            continue
    raise RuntimeError(f"Could not get a number for {name}")


class CacheEntry(Base):
    __tablename__ = "cache"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String)  # exact | semantic
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    value: Mapped[Any] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


_engine = None
_Session: sessionmaker | None = None


def engine():
    global _engine, _Session
    if _engine is None:
        url = get_settings().database_url
        if url.startswith("sqlite:///"):
            from pathlib import Path
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        if url.startswith("sqlite"):
            _engine = create_engine(url, future=True, connect_args={"timeout": 30})

            @event.listens_for(_engine, "connect")
            def _sqlite_pragmas(conn, _):  # enforce foreign keys like Postgres does; allow concurrent readers
                cur = conn.cursor()
                cur.execute("PRAGMA foreign_keys=ON")
                cur.execute("PRAGMA journal_mode=WAL")
                cur.close()
        else:
            _engine = create_engine(url, future=True, pool_size=int(os.getenv("BRAIN_DB_POOL", "10")), max_overflow=20,
                                    pool_pre_ping=True, pool_recycle=1800)
        _Session = sessionmaker(_engine, expire_on_commit=False)
    return _engine


def session() -> Session:
    engine()
    assert _Session is not None
    return _Session()


def reset_engine(url: str | None = None) -> None:
    """Used by tests to point at a fresh database."""
    global _engine, _Session
    import os
    if url:
        os.environ["BRAIN_DATABASE_URL"] = url
    _engine = None
    _Session = None


def create_all(drop: bool = False) -> None:
    e = engine()
    if drop:
        Base.metadata.drop_all(e)
    Base.metadata.create_all(e)


def assert_synthetic_only(s: Session) -> None:
    """Refuse to run on real rows while the data stage is synthetic."""
    if get_settings().data_stage != "synthetic":
        return
    for model in (Family, Partner, Mail, TripRequest, PastProposal, KnowledgeItem, Employee, PriceItem):
        row = s.scalars(select(model).where(model.synthetic.is_(False)).limit(1)).first()
        if row is not None:
            raise RuntimeError(f"Non synthetic row found in {model.__tablename__} while BRAIN_DATA_STAGE=synthetic")


def as_dict(obj: Any) -> dict:
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
