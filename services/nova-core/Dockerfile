FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# psql client for staging-entrypoint.sh (database creation)
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Tester stage running pytest
FROM base AS tester
RUN pip install --no-cache-dir pytest pytest-asyncio
COPY app ./app
COPY tests ./tests
RUN pytest

# Final stage for deployment
FROM base
COPY app ./app
COPY static ./static
COPY alembic.ini .
COPY alembic ./alembic
COPY staging-entrypoint.sh .
RUN chmod +x staging-entrypoint.sh

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
