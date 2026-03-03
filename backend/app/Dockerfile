FROM python:3.13.7-slim AS builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    protobuf-compiler && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir 'uv==0.8.3'

WORKDIR /app

ENV UV_PROJECT_ENVIRONMENT="/venv"

COPY pyproject.toml README.md ./

RUN uv lock

RUN uv sync --frozen --no-dev

FROM python:3.13.7-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/sh gateway

WORKDIR /app

COPY --from=builder /venv /venv
COPY . ./

RUN chown -R gateway:gateway /app /venv

USER gateway

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PATH="/venv/bin:$PATH"

EXPOSE 8000

HEALTHCHECK --start-period=60s --retries=3 --interval=30s --timeout=5s \
    CMD ["curl", "-f", "http://localhost:8000/health"]

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port 8000 --workers $(($(nproc) * 4))"]
