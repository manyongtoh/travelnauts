"""One check of a database's health, used after every restore and in the daily runbook.

Reports the row count of every table, whether the audit chain is unbroken and whether the schema is at the
newest migration. Two restores of the same backup must give the same counts and the same chain head.
"""
from __future__ import annotations

from sqlalchemy import func, inspect, select, table, text

from . import db
from .auditchain import verify as verify_chain


def _schema_head() -> tuple[str | None, str | None]:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    from .config import ROOT
    head = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini"))).get_current_head()
    with db.engine().connect() as c:
        try:
            current = c.execute(text("select version_num from alembic_version")).scalar()
        except Exception:  # noqa: BLE001  a database built by create_all has no version table
            current = None
    return current, head


def verify_database() -> dict:
    eng = db.engine()
    counts = {}
    with eng.connect() as c:
        for t in sorted(inspect(eng).get_table_names()):
            if t == "alembic_version":
                continue
            counts[t] = c.execute(select(func.count()).select_from(table(t))).scalar()  # name quoted by SQLAlchemy
    with db.session() as s:
        chain = verify_chain(s)
    current, head = _schema_head()
    problems = []
    if not chain["ok"]:
        problems.append(f"audit chain broken at entry {chain['broken_at']}")
    if current is not None and current != head:
        problems.append(f"schema at {current}, newest is {head}: run brain migrate")
    return {"ok": not problems, "problems": problems, "schema": current or "not managed by migrations",
            "schema_head": head, "audit_chain": chain, "rows": counts}


def adopt_unmanaged(cfg) -> str | None:
    """A database that has tables but no migration history (built by seed or create_all) is stamped at the newest
    migration only when its schema matches the code exactly. Otherwise it stops: guessing would corrupt it."""
    from alembic import command
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    eng = db.engine()
    tables = set(inspect(eng).get_table_names())
    if "alembic_version" in tables or not (tables & set(db.Base.metadata.tables)):
        return None
    with eng.connect() as c:
        diff = compare_metadata(MigrationContext.configure(c), db.Base.metadata)
    if diff:
        raise SystemExit(f"This database was built without migrations and differs from the code in {len(diff)} places; "
                         "restore it from a migrated backup or ask the admin. Nothing was changed.")
    command.stamp(cfg, "head")
    return "Database was built without migrations but matches the code; recorded it at the newest migration."
