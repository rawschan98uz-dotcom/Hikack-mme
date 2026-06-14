#!/bin/sh
set -e

cd "$(dirname "$0")"

echo "Running migrations..."
if [ -z "$DATABASE_URL" ]; then
  echo "ERROR: DATABASE_URL is not set. Link PostgreSQL in Railway Variables."
  exit 1
fi
python manage.py migrate --noinput

if [ "$SEED_DEMO" = "1" ]; then
  echo "Seeding demo data..."
  python manage.py seed_demo
fi

echo "Starting gunicorn on port ${PORT:-8000}..."
exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --timeout 120
