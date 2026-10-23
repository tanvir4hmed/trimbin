FROM ghcr.io/astral-sh/uv:0.13.4 AS uv
FROM python:3.12-slim-bookworm AS build
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /opt/trimbin
COPY agents ./agents
COPY api/pyproject.toml api/uv.lock ./api/
COPY api/app ./api/app
RUN cd api && uv sync --locked --no-dev --no-editable --python /usr/local/bin/python

FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home --shell /usr/sbin/nologin trimbin
COPY --from=build /opt/trimbin /opt/trimbin
COPY clickhouse /opt/trimbin/clickhouse
COPY config /opt/trimbin/config
COPY tools/production_bootstrap.py /opt/trimbin/tools/production_bootstrap.py
ENV PATH="/opt/trimbin/api/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /opt/trimbin/api
USER 10001:10001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
