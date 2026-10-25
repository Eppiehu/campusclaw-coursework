#!/bin/sh
set -eu
# Run only from the dedicated release folder, never from another Compose project.
case "$(pwd)" in /opt/campusclaw-nexus/releases/*) ;; *) echo 'Use the dedicated Nexus release folder'; exit 1;; esac
test -s .env.nexus.local
test -s web/dist/index.html
docker compose --env-file .env.nexus.local -f docker-compose.nexus.yml config --quiet
docker compose --env-file .env.nexus.local -f docker-compose.nexus.yml build api
docker compose --env-file .env.nexus.local -f docker-compose.nexus.yml up -d db redis
docker compose --env-file .env.nexus.local -f docker-compose.nexus.yml run --rm --no-deps api python scripts/nexus_init.py
docker compose --env-file .env.nexus.local -f docker-compose.nexus.yml up -d api worker scheduler
docker compose --env-file .env.nexus.local -f docker-compose.nexus.yml ps
