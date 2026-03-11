# syntax=docker/dockerfile:1.6
# Build context must be the workspace root: docker build -f services/ingest-service/Dockerfile .
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

FROM base AS builder
RUN pip install hatchling
COPY services/shared-lib /tmp/shared-lib
COPY services/ingest-service/pyproject.toml services/ingest-service/README.md ./
COPY services/ingest-service/src ./src
RUN pip install --prefix=/install /tmp/shared-lib && \
    PYTHONPATH=/install/lib/python3.11/site-packages pip install --prefix=/install "."

FROM base AS runtime
COPY --from=builder /install /usr/local
COPY services/ingest-service/src ./src

RUN addgroup --system allergo && adduser --system --ingroup allergo allergo
USER allergo

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live')"

CMD ["python", "-m", "ingest_service"]
