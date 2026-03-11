# syntax=docker/dockerfile:1.6
# Build context must be the workspace root: docker build -f services/processing-service/Dockerfile .
FROM python:3.11-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-nor \
    tesseract-ocr-eng \
    libgl1 \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata

WORKDIR /app

FROM base AS builder
RUN pip install hatchling
COPY services/shared-lib /tmp/shared-lib
COPY services/processing-service/pyproject.toml services/processing-service/README.md ./
COPY services/processing-service/src ./src
RUN pip install --prefix=/install /tmp/shared-lib && \
    PYTHONPATH=/install/lib/python3.11/site-packages pip install --prefix=/install "." && \
    pip install --prefix=/install --ignore-installed "packaging>=23.0"

FROM base AS runtime
COPY --from=builder /install /usr/local
COPY services/processing-service/src ./src

RUN addgroup --system allergo && adduser --system --ingroup allergo allergo
USER allergo

CMD ["python", "-m", "processing_service"]
