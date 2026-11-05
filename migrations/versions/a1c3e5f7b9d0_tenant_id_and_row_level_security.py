"""tenant id on every table, row-level security on Postgres

Every existing row gets the tenant of this deployment (BRAIN_TENANT, from the installed tenant pack).
On Postgres every table gets a policy: a session sees and writes only rows of the tenant in the setting
brain.tenant_id, which the app sets at the start of every transaction. The app must connect as a role that is
not a superuser and has no BYPASSRLS, otherwise Postgres skips these policies.

Keys that are single columns (settings.key, counters.name, cache.key, family_addresses.email,
portal_links.token_hash) stay unique per database: one database per client, as today.

Revision ID: a1c3e5f7b9d0
Revises: cfc1df687704
Create Date: 2026-11-05 17:20:00
"""
from alembic import op
import sqlalchemy as sa


revision = 'a1c3e5f7b9d0'
down_revision = 'cfc1df687704'
branch_labels = None
depends_on = None

TABLES = ['agent_runs', 'audit_chain', 'cache', 'counters', 'drafts', 'employees', 'families', 'family_addresses',
          'invoice_checks', 'jobs', 'knowledge', 'knowledge_gaps', 'mails', 'model_calls', 'partner_requests',
          'partners', 'past_proposals', 'portal_lines', 'portal_links', 'portal_messages', 'price_items', 'quotes',
          'requests', 'settings', 'teams', 'tool_calls']


def rls_on(table: str) -> list[str]:
    rule = "tenant_id = current_setting('brain.tenant_id', true)"
    return [f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
            f"CREATE POLICY tenant_isolation ON {table} USING ({rule}) WITH CHECK ({rule})"]


def upgrade() -> None:
    from brain.tenant import tenant
    tid = tenant().tenant_id
    for table in TABLES:
        op.add_column(table, sa.Column('tenant_id', sa.String(), nullable=True))
        op.execute(sa.text(f"UPDATE {table} SET tenant_id = :t").bindparams(t=tid))
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.alter_column('tenant_id', existing_type=sa.String(), nullable=False)
            batch_op.create_index(batch_op.f(f'ix_{table}_tenant_id'), ['tenant_id'], unique=False)
    # portal messages by our own people were stored under the client's name; the core now calls them "team"
    op.execute("UPDATE portal_messages SET author = 'team' WHERE author <> 'partner'")
    if op.get_bind().dialect.name == "postgresql":
        for table in TABLES:
            for stmt in rls_on(table):
                op.execute(stmt)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in TABLES:
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
            op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    for table in TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_index(batch_op.f(f'ix_{table}_tenant_id'))
            batch_op.drop_column('tenant_id')
