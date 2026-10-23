# Supply immutable image references from the operator's approved image manifest.
ARG PYTHON_IMAGE
ARG UV_IMAGE
FROM ${UV_IMAGE} AS uv
FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /opt/trimbin
COPY api/pyproject.toml api/uv.lock ./api/
COPY agents/ ./agents/
COPY api/app ./api/app
RUN cd api && uv sync --locked --no-dev --no-editable --python /usr/local/bin/python

FROM ${PYTHON_IMAGE}
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home --shell /usr/sbin/nologin trimbin
COPY --from=build /opt/trimbin /opt/trimbin
ENV PATH="/opt/trimbin/api/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /opt/trimbin/api
USER 10001:10001
CMD ["uvicorn", "app.portable:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
