#!/bin/bash
set -euo pipefail
umask 077
exec 9>/var/lock/trimbin-release.lock
flock 9
cd /opt/trimbin/current/deploy/production
stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup="/srv/trimbin/backups/$stamp"
mkdir -p "$backup"
compose=(docker compose --env-file /srv/trimbin/private/images.env)
# Stop writers across both authorities for one consistent cross-store snapshot.
trap '"${compose[@]}" start api media editorial analysis projection vectors exports renders >/dev/null' EXIT
"${compose[@]}" stop api media editorial analysis projection vectors exports renders >/dev/null
"${compose[@]}" exec -T postgres pg_dump -U postgres -d trimbin -Fc > "$backup/postgres.dump"
"${compose[@]}" exec -T clickhouse sh -c 'clickhouse-client --user default --password "$(cat /run/secrets/clickhouse_admin)" --query "$1"' sh "BACKUP DATABASE default TO Disk('backups', '$stamp')" >/dev/null
bucket=$(aws sts get-caller-identity --query Account --output text)
aws s3 cp "$backup/postgres.dump" "s3://trimbin-backups-$bucket/$stamp/postgres.dump" --only-show-errors
aws s3 sync "/srv/trimbin/backups/clickhouse/$stamp" "s3://trimbin-backups-$bucket/$stamp/clickhouse/" --only-show-errors
aws s3 sync /srv/trimbin/media/originals "s3://trimbin-backups-$bucket/originals/" --only-show-errors
aws s3 sync /srv/trimbin/media/exports "s3://trimbin-backups-$bucket/exports/" --only-show-errors
echo "Trimbin backup complete: $stamp"
