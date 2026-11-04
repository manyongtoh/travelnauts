#!/usr/bin/env bash
# Backup and restore drill. Run monthly in pilot and live, and after any change to the database setup.
#   scripts/backup_drill.sh postgresql://brain@host:5432/brain
# 1. verify the source  2. pg_dump  3. restore into a new database  4. verify the copy
# 5. the counts and the audit chain head must match  6. the newest migration must run on the restored data
set -euo pipefail
SRC="${1:?source database url}"
BASE="${SRC%/*}"; COPY="brain_restore_$(date +%Y%m%d%H%M%S)"
OUT="${BRAIN_DRILL_DIR:-data/ops}"; mkdir -p "$OUT"
DUMP="$OUT/$COPY.dump"
sa() { echo "$1" | sed 's#^postgresql://#postgresql+psycopg://#'; }

echo "1. verify source";      BRAIN_DATABASE_URL="$(sa "$SRC")" python3 -m brain.cli verify > "$OUT/drill-source.json"
echo "2. backup";             pg_dump --format=custom --no-owner "$SRC" -f "$DUMP"; ls -lh "$DUMP" | awk '{print "   " $5}'
echo "3. restore to $COPY";   psql "$SRC" -qc "create database $COPY"
                              pg_restore --no-owner -d "$BASE/$COPY" "$DUMP"
echo "4. verify copy";        BRAIN_DATABASE_URL="$(sa "$BASE/$COPY")" python3 -m brain.cli verify > "$OUT/drill-copy.json"
echo "5. compare"
python3 - "$OUT/drill-source.json" "$OUT/drill-copy.json" <<'PY'
import json, sys
a, b = (json.load(open(p)) for p in sys.argv[1:3])
diff = {t: (a["rows"].get(t), b["rows"].get(t)) for t in set(a["rows"]) | set(b["rows"]) if a["rows"].get(t) != b["rows"].get(t)}
same_head = a["audit_chain"].get("head") == b["audit_chain"].get("head")
print(f"   tables: {len(b['rows'])}, rows: {sum(b['rows'].values())}, differences: {diff or 'none'}")
print(f"   audit chain: {b['audit_chain']['entries']} entries, ok: {b['audit_chain']['ok']}, same head as source: {same_head}")
sys.exit(0 if (not diff and same_head and b["ok"]) else 1)
PY
echo "6. newest migration on restored data"
# Put the copy back one migration, with all its data, and migrate forward again: proves the newest migration
# runs on real volumes before it runs in live.
BRAIN_DATABASE_URL="$(sa "$BASE/$COPY")" python3 -m brain.cli migrate > /dev/null
BRAIN_DATABASE_URL="$(sa "$BASE/$COPY")" python3 -m alembic downgrade -1 > /dev/null 2>&1
BRAIN_DATABASE_URL="$(sa "$BASE/$COPY")" python3 -m alembic upgrade head > /dev/null 2>&1 && echo "   down one migration and up again: ok"
BRAIN_DATABASE_URL="$(sa "$BASE/$COPY")" python3 -m alembic check > /dev/null 2>&1 && echo "   schema matches the code" || { echo "   schema differs from the code"; exit 1; }
echo "drill passed. copy kept as $COPY; drop it with: psql $SRC -c 'drop database $COPY'"
