FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Tester stage running pytest
FROM base AS tester
RUN pip install --no-cache-dir pytest pytest-asyncio
COPY app.py .
COPY tests ./tests
RUN pytest

# Final stage for deployment
FROM base
COPY app.py .

EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
