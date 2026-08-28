# Two stages. The build stage carries compilers and headers that a running
# service has no use for, and shipping them enlarges both the image and the
# attack surface for no benefit.

FROM python:3.12-slim AS build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Dependencies before source. Layer caching then means a code change rebuilds in
# seconds rather than reinstalling the world — which matters when CI runs on
# every push.
COPY api/pyproject.toml ./
RUN pip install --prefix=/install --no-cache-dir \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.32.0" \
    "pydantic>=2.9.0" \
    "pydantic-settings>=2.5.0" \
    "clickhouse-connect>=0.8.0" \
    "aiohttp>=3.10.0" \
    "google-cloud-storage>=2.18.0" \
    "google-cloud-firestore>=2.19.0" \
    "google-cloud-pubsub>=2.23.0" \
    "google-cloud-secret-manager>=2.20.0"

# The agents, installed as a package rather than copied in.
#
# The worker calls the Slate Agent, so this image carries both. One image with
# two entrypoints, because ffmpeg, the measurement code and the ClickHouse
# client are already here and a second Dockerfile would be a second dependency
# list to keep in step — drift there would show up as the worker measuring
# differently from the eval harness.
COPY agents/ ./agents/
RUN pip install --prefix=/install --no-cache-dir --no-deps ./agents \
    && pip install --prefix=/install --no-cache-dir "google-genai>=1.0.0"


FROM python:3.12-slim

# ffmpeg is not a convenience here — it is where every measurement comes from.
# Exposure, focus, stability and audio levels are computed with it in the same
# pass that builds proxies, which is why they are exact and effectively free.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# Never root. A compromised process should not be able to write to its own image.
RUN useradd --create-home --shell /usr/sbin/nologin trimbin
WORKDIR /app

COPY --from=build /install /usr/local
COPY --chown=trimbin:trimbin api/app ./app

USER trimbin

EXPOSE 8080

# Cloud Run supplies PORT and terminates TLS, so the server binds plainly to
# whatever it is given.
#
# One worker per instance, and concurrency handled by the event loop. Cloud Run
# scales by adding instances; adding workers inside one only multiplies the
# memory footprint of a service that is waiting on a database most of the time.
CMD exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port ${PORT} \
    --workers 1 \
    --timeout-keep-alive 65 \
    --no-access-log
