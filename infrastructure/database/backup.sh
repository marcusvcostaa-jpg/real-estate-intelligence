#!/bin/sh
# Daily pg_dump into /backups with retention. Runs as the `backup` compose service.
# ponytail: sleep loop instead of cron; move to host cron / managed backups in production.
set -eu
: "${BACKUP_RETENTION_DAYS:=14}"
: "${BACKUP_INTERVAL_SECONDS:=86400}"

until pg_isready -q; do sleep 2; done

while true; do
  file="/backups/${PGDATABASE}_$(date -u +%Y%m%dT%H%M%SZ).dump"
  if pg_dump --format=custom --file="$file.partial"; then
    mv "$file.partial" "$file"
    echo "backup ok: $file"
  else
    rm -f "$file.partial"
    echo "backup FAILED" >&2
  fi
  find /backups -name "${PGDATABASE}_*.dump" -mtime "+${BACKUP_RETENTION_DAYS}" -delete
  sleep "$BACKUP_INTERVAL_SECONDS"
done
