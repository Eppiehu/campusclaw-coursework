#!/bin/sh
set -eu
case "$(pwd)" in /opt/campusclaw-nexus/releases/*) ;; *) echo 'Use the dedicated Nexus release folder'; exit 1;; esac
umask 077
mkdir -p /opt/campusclaw-nexus/backups
target="/opt/campusclaw-nexus/backups/nexus-$(date -u +%Y%m%dT%H%M%SZ).sql"
docker compose --env-file .env.nexus.local -f docker-compose.nexus.yml exec -T db pg_dump -U nexus nexus > "$target"
test -s "$target"
echo 'Nexus database backup completed'
