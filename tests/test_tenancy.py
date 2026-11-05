"""Tenant isolation: a second invented tenant, Zeebries Reizen, shares the database with the sample tenant.
Neither sees, counts, changes or deletes the other's rows. On Postgres, row-level security holds the same line
for raw SQL that bypasses the app, and refuses a row written under the wrong tenant."""
import os
import uuid

import pytest
from sqlalchemy import create_engine, delete, func, select, text, update

from brain import autonomy
from brain.db import Draft, Family, Job, Team
from brain.tenant import TenantConfig, as_tenant, current_tenant_id, load, tenant

OTHER = "zeebries"


def other_family(s):
    with as_tenant(OTHER):
        s.add(Team(id="zb-asia", name="Zeebries Azie", destinations=["japan"]))
        s.add(Family(id="zb-fam-1", surname="Zeebries", contact_name="Mees Zeebries", adults=2, child_ages=[6]))
        s.add(Draft(kind="followup", title="Zeebries follow-up", body="Beste Mees"))
        s.commit()
    s.expunge_all()


def test_a_second_tenant_sees_only_its_own_rows(world):
    mine = world.scalar(select(func.count()).select_from(Family))
    assert mine > 0
    other_family(world)
    assert world.scalar(select(func.count()).select_from(Family)) == mine  # the sample tenant: unchanged
    assert world.get(Family, "zb-fam-1") is None and world.get(Team, "zb-asia") is None
    assert not world.scalars(select(Draft).where(Draft.title.like("Zeebries%"))).all()
    with as_tenant(OTHER):
        assert [f.id for f in world.scalars(select(Family))] == ["zb-fam-1"]
        assert world.get(Family, "zb-fam-1").tenant_id == OTHER
        assert world.scalar(select(func.count()).select_from(Draft)) == 1


def test_updates_and_deletes_never_reach_the_other_tenant(world):
    other_family(world)
    world.execute(update(Draft).values(status="rejected"))
    world.execute(delete(Team).where(Team.id.like("zb-%")))
    world.commit()
    world.expunge_all()
    with as_tenant(OTHER):
        assert world.scalars(select(Draft)).one().status == "draft"
        assert world.get(Team, "zb-asia") is not None


def test_new_rows_carry_the_current_tenant(world):
    assert current_tenant_id() == tenant().tenant_id
    f = world.scalars(select(Family)).first()
    assert f.tenant_id == tenant().tenant_id
    with as_tenant(OTHER):
        world.add(Job(kind="noop"))
        world.commit()
    assert world.scalars(select(Job).where(Job.kind == "noop")).first() is None
    with pytest.raises(ValueError):
        with as_tenant("Not A Slug"):
            pass


def test_every_task_starts_at_autonomy_level_one(world):
    d = Draft(kind="proposal", title="t", body="b")
    j = Job(kind="triage")
    world.add_all([d, j])
    world.commit()
    assert d.autonomy_level == 1 and j.autonomy_level == 1
    assert autonomy.ceiling("proposal") == 1 and autonomy.ceiling("followup") == 2


def test_the_tenant_config_refuses_mistakes():
    base = load().config.model_dump()
    for bad in ({"own_domains": ["not a domain"]}, {"tenant_id": "Has Spaces"}, {"autonomy_max": 4},
                {"pricing": {"margins": {"hotel": 1.5}}}, {"surprise": True}, {"reference_prefix": "tn"}):
        with pytest.raises(ValueError):
            TenantConfig.model_validate(base | bad)


PG = os.getenv("BRAIN_TEST_DATABASE_URL", "")


@pytest.mark.skipif(not PG.startswith("postgresql"), reason="row-level security is a Postgres feature")
def test_row_level_security_holds_for_raw_sql(world):
    """The app's own scoping is one line; Postgres is the second. Here the app is bypassed entirely."""
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "mig", Path(__file__).parent.parent / "migrations" / "versions" / "a1c3e5f7b9d0_tenant_id_and_row_level_security.py")
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    other_family(world)
    world.close()
    role = f"brain_app_{uuid.uuid4().hex[:8]}"  # not a superuser and no BYPASSRLS, as the app must connect
    admin = create_engine(PG)
    try:
        with admin.begin() as c:
            for stmt in mig.rls_on("families"):
                c.exec_driver_sql(stmt)
            c.exec_driver_sql(f"CREATE ROLE {role} NOSUPERUSER NOBYPASSRLS")
            c.exec_driver_sql(f"GRANT SELECT, INSERT ON families TO {role}")
        with admin.connect() as c:
            c.exec_driver_sql(f"SET ROLE {role}")
            assert c.scalar(text("select count(*) from families")) == 0  # no tenant set: nothing at all
            c.execute(text("select set_config('brain.tenant_id', :t, false)"), {"t": OTHER})
            assert c.scalars(text("select id from families")).all() == ["zb-fam-1"]
            c.execute(text("select set_config('brain.tenant_id', :t, false)"), {"t": tenant().tenant_id})
            assert "zb-fam-1" not in c.scalars(text("select id from families")).all()
            with pytest.raises(Exception, match="row-level security"):
                c.execute(text("insert into families (id, surname, contact_name, adults, child_ages, child_birth_years,"
                               " past_destinations, notes, synthetic, tenant_id) values ('x', 'X', 'X', 1, '[]', '[]',"
                               " '[]', '', true, :t)"), {"t": OTHER})
            c.rollback()
    finally:
        with admin.begin() as c:
            c.exec_driver_sql("RESET ROLE")
            c.exec_driver_sql("DROP POLICY IF EXISTS tenant_isolation ON families")
            c.exec_driver_sql("ALTER TABLE families NO FORCE ROW LEVEL SECURITY")
            c.exec_driver_sql("ALTER TABLE families DISABLE ROW LEVEL SECURITY")
            c.exec_driver_sql(f"REVOKE ALL ON families FROM {role}")
            c.exec_driver_sql(f"DROP ROLE IF EXISTS {role}")
        admin.dispose()
