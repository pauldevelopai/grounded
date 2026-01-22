#!/bin/bash
set -e

echo "Waiting for postgres..."
while ! pg_isready -h db -U ${POSTGRES_USER:-toolkitrag}; do
  sleep 1
done
echo "PostgreSQL started"

echo "Running migrations..."
alembic upgrade head

echo "Starting application..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
