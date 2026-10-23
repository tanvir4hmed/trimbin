#!/bin/bash
set -euo pipefail
umask 077
release_dir=$(cd "$(dirname "$0")/../.." && pwd)
cd "$release_dir/deploy/production"
flock -n /var/lock/trimbin-release.lock -c true
exec 9>/var/lock/trimbin-release.lock
flock 9
mountpoint -q /srv/trimbin
python3 configure.py
if [ "${TRIMBIN_LOCAL_BUILD:-false}" != true ]; then
  registry="${TRIMBIN_APP_IMAGE%%/*}"
  aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin "$registry" >/dev/null
fi
if test -f /srv/trimbin/private/images.env; then
  cp /srv/trimbin/private/images.env /srv/trimbin/private/images.previous.env
fi
printf 'TRIMBIN_APP_IMAGE=%s\nTRIMBIN_WEB_IMAGE=%s\n' "$TRIMBIN_APP_IMAGE" "$TRIMBIN_WEB_IMAGE" > /srv/trimbin/private/images.env
compose=(docker compose --env-file /srv/trimbin/private/images.env -f "$release_dir/deploy/production/compose.yaml")
if [ "${TRIMBIN_LOCAL_BUILD:-false}" != true ]; then
  "${compose[@]}" pull --quiet
fi
"${compose[@]}" up -d --wait --wait-timeout 240 postgres clickhouse
"${compose[@]}" run --rm --no-deps bootstrap
"${compose[@]}" up -d --remove-orphans api web media editorial analysis projection vectors exports renders gateway
healthy=false
for attempt in $(seq 1 60); do
  if curl --fail --silent http://localhost/api/ready >/dev/null && curl --fail --silent http://localhost/projects >/dev/null; then
    healthy=true
    break
  fi
  sleep 5
done
if [ "$healthy" != true ]; then
  echo 'Trimbin rollout failed readiness; restoring previous images when available' >&2
  if test -f /srv/trimbin/private/images.previous.env; then
    cp /srv/trimbin/private/images.previous.env /srv/trimbin/private/images.env
    "${compose[@]}" up -d --remove-orphans api web media editorial analysis projection vectors exports renders gateway
  fi
  exit 1
fi
ln -sfn "$release_dir" /opt/trimbin/current
install -m 755 "$release_dir/deploy/production/backup.sh" /opt/trimbin/backup.sh
printf '%s\n' '[Unit]' 'Description=Trimbin consistent backup' '[Service]' 'Type=oneshot' 'ExecStart=/opt/trimbin/backup.sh' > /etc/systemd/system/trimbin-backup.service
printf '%s\n' '[Unit]' 'Description=Trimbin daily backup' '[Timer]' 'OnCalendar=daily' 'Persistent=true' '[Install]' 'WantedBy=timers.target' > /etc/systemd/system/trimbin-backup.timer
systemctl daemon-reload
systemctl enable --now trimbin-backup.timer
echo 'Trimbin release healthy'
