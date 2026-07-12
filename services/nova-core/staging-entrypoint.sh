#!/usr/bin/env bash
# Staging entrypoint: create staging DB, run migrations, start uvicorn.
# Only runs in the nova-staging container (via docker-compose.staging.yml entrypoint override).
# Production uses the default Dockerfile CMD (uvicorn directly).

set -euo pipefail

# Extract connection parameters from environment (same vars as production, but POSTGRES_DB=nova_staging)
PGHOST="${POSTGRES_HOST:-postgres}"
PGPORT="${POSTGRES_PORT:-5432}"
PGUSER="${POSTGRES_USER:-nova}"
PGPASSWORD="${POSTGRES_PASSWORD}"
PGDB="${POSTGRES_DB:-nova_staging}"

echo "staging-entrypoint: ensuring database '$PGDB' exists on $PGHOST:$PGPORT ..."

# Create the database if it does not exist.
# We connect to the 'postgres' maintenance database to issue CREATE DATABASE.
PGPASSWORD="$PGPASSWORD" psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d postgres -tc \
  "SELECT 1 FROM pg_database WHERE datname = '$PGDB'" | grep -q 1 \
  || PGPASSWORD="$PGPASSWORD" psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d postgres -c \
       "CREATE DATABASE $PGDB OWNER $PGUSER"

echo "staging-entrypoint: database ready, running Alembic migrations ..."

# Run Alembic migrations against the staging database.
# (The database URL is built from env vars; ensure POSTGRES_DB=nova_staging is set in .env.staging)
cd /app
python -m alembic upgrade head

echo "staging-entrypoint: migrations complete, starting uvicorn ..."

# Start uvicorn on 0.0.0.0:8080 (as the Dockerfile CMD would, but done here explicitly)
exec uvicorn app.main:app --host 0.0.0.0 --port 8080
