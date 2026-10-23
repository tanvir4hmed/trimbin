#!/bin/bash
set -euo pipefail
dnf install -y docker git python3
systemctl enable --now docker
mkdir -p /usr/local/lib/docker/cli-plugins /srv/trimbin /opt/trimbin
curl --fail --location --retry 5 https://github.com/docker/compose/releases/download/v2.39.4/docker-compose-linux-x86_64 -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod 755 /usr/local/lib/docker/cli-plugins/docker-compose
systemctl enable --now amazon-ssm-agent
# Persistent data volume is attached by Terraform. Never format a nonempty device.
for attempt in $(seq 1 120); do
  device=$(lsblk -dnpo NAME,SERIAL | awk '$2 ~ /^vol/ && $1 !~ /nvme0n1$/ {print $1; exit}')
  if [ -n "$device" ]; then break; fi
  sleep 5
done
test -n "$device"
if ! blkid "$device" >/dev/null 2>&1; then mkfs.ext4 "$device"; fi
uuid=$(blkid -s UUID -o value "$device")
grep -q "UUID=$uuid " /etc/fstab || printf 'UUID=%s /srv/trimbin ext4 defaults,nofail 0 2\n' "$uuid" >> /etc/fstab
mountpoint -q /srv/trimbin || mount /srv/trimbin
mkdir -p /srv/trimbin/{postgres,clickhouse,private,backups,model-cache}
mkdir -p /srv/trimbin/media/{originals,staging,derived,library,exports}
chmod 700 /srv/trimbin/private /srv/trimbin/backups
chown -R 10001:10001 /srv/trimbin/media /srv/trimbin/model-cache
