#!/bin/sh
set -eu
if [ -n "${DATABASE_URL:-}" ]; then
  python scripts/init_mysql.py
else
  python scripts/init_db.py
fi
exec gunicorn --bind 0.0.0.0:8080 --workers 2 --threads 4 --timeout 120 'app:create_app()'
