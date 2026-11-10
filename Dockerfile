# Faamily backend image
#
# Multi-stage-ish: dependency layer is cached separately from the source
# layer, so editing app/ code does not re-download pip packages.
#
# Build:  docker build -t faamily-backend .
# Run:    docker run --rm -p 8000:8000 --env-file .env faamily-backend

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# --- OS packages -----------------------------------------------------------
# libpq5 is required by psycopg at runtime; build-essential is needed only
# while installing packages that lack a wheel (kept out of the final layer).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

# --- Dependencies -----------------------------------------------------------
# Copied first so this layer is cached across source-code changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# --- Application source -----------------------------------------------------
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
COPY init_db.py ./
COPY pyproject.toml ./

# --- Non-root user ----------------------------------------------------------
# Running as root inside a container is unnecessary and widens the blast
# radius if the process is ever compromised.
RUN groupadd --system --gid 1000 faamily \
    && useradd --system --uid 1000 --gid faamily --home-dir /app faamily \
    && mkdir -p /app/data \
    && chown -R faamily:faamily /app
USER faamily

EXPOSE 8000

# The app expects DATABASE_URL etc. from the environment — never bake
# secrets into the image.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# --proxy-headers: let uvicorn read X-Forwarded-* (scheme, host) from Nginx.
# --forwarded-allow-ips: restrict to the private Docker network, so a
#   spoofed header from an untrusted source is ignored.
# Rate limiting has its own stricter control: TRUSTED_PROXY_HOPS in .env.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='172.28.0.0/16'"]
