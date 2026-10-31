#!/bin/sh
# Restore a dump into a target database (default: $PGDATABASE). DESTRUCTIVE for the target.
# Usage (from repo root):
#   docker compose run --rm --entrypoint sh backup /scripts/restore.sh /backups/<file>.dump [target_db]
set -eu
dump="${1:?usage: restore.sh <dump-file> [target_db]}"
target="${2:-$PGDATABASE}"

echo "Restoring $dump into database '$target' (existing objects will be replaced)..."
pg_restore --clean --if-exists --no-owner --dbname="$target" "$dump"
echo "restore ok"
