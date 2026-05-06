# Dockerfile - AI选品系统容器镜像

FROM python:3.11-slim AS builder

WORKDIR /build

ARG PMS_PYTHON_EXTRAS=""

RUN set -eux; \
    export DEBIAN_FRONTEND=noninteractive; \
    install_with_retry() { \
      attempt=1; \
      until [ "$attempt" -gt 5 ]; do \
        apt-get update; \
        if apt-get install -y --no-install-recommends --fix-missing "$@" \
          && apt-get install -f -y --no-install-recommends; then \
          rm -rf /var/lib/apt/lists/*; \
          return 0; \
        fi; \
        apt-get install -f -y --no-install-recommends || true; \
        rm -rf /var/lib/apt/lists/*; \
        if [ "$attempt" -eq 5 ]; then \
          return 1; \
        fi; \
        sleep $((attempt * 5)); \
        attempt=$((attempt + 1)); \
      done; \
    }; \
    install_with_retry \
      cpp \
      gcc \
      libpq-dev

COPY pyproject.toml README.md ./
COPY src ./src

RUN if [ -n "$PMS_PYTHON_EXTRAS" ]; then \
      pip install --no-cache-dir --prefix=/install ".[${PMS_PYTHON_EXTRAS}]"; \
    else \
      pip install --no-cache-dir --prefix=/install .; \
    fi


FROM python:3.11-slim AS runtime

LABEL maintainer="PMS Team <dev@pms.com>"
LABEL description="AI选品系统 - 当前开发基线镜像"
LABEL version="0.1.0"

RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /usr/sbin/nologin appuser

RUN set -eux; \
    export DEBIAN_FRONTEND=noninteractive; \
    install_with_retry() { \
      attempt=1; \
      until [ "$attempt" -gt 5 ]; do \
        apt-get update; \
        if apt-get install -y --no-install-recommends --fix-missing "$@" \
          && apt-get install -f -y --no-install-recommends; then \
          rm -rf /var/lib/apt/lists/*; \
          return 0; \
        fi; \
        apt-get install -f -y --no-install-recommends || true; \
        rm -rf /var/lib/apt/lists/*; \
        if [ "$attempt" -eq 5 ]; then \
          return 1; \
        fi; \
        sleep $((attempt * 5)); \
        attempt=$((attempt + 1)); \
      done; \
    }; \
    install_with_retry \
      libpq5 \
      curl \
      ffmpeg; \
    mkdir -p /app/logs /app/.cache/huggingface /app/.cache/whisper /app/.cache/sentence-transformers

WORKDIR /app

COPY --from=builder /install /usr/local
COPY --chown=appuser:appuser src/ /app/src/
COPY --chown=appuser:appuser pyproject.toml README.md /app/
COPY --chown=appuser:appuser .env.example /app/.env.example
COPY --chown=appuser:appuser alembic.ini /app/alembic.ini
COPY --chown=appuser:appuser alembic/ /app/alembic/

RUN chown -R appuser:appuser /app

USER appuser

ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENVIRONMENT=production

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
