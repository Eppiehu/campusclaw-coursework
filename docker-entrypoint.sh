#!/bin/sh
set -eu
if [ ! -f /app/data/app.db ]; then
  python scripts/init_db.py
fi
exec gunicorn --bind 0.0.0.0:8080 --workers 2 'app:create_app()'
