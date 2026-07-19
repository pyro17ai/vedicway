# syntax=docker/dockerfile:1.7
FROM node:22.17.0-bookworm-slim@sha256:b04ce4ae4e95b522112c2e5c52f781471a5cbc3b594527bcddedee9bc48c03a0 AS node-runtime

FROM python:3.11.13-slim-bookworm@sha256:86adf8dbadc3d6e82ee5dd2c74bec2e1c2467cdad47886280501df722372d2e1 AS runtime-base

ARG CODEX_CLI_VERSION=0.144.6

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PATH=/opt/venv/bin:/usr/local/bin:${PATH} \
    VIRTUAL_ENV=/opt/venv

COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

WORKDIR /opt/vedicway

COPY docker/backend/package.json docker/backend/package-lock.json ./
RUN npm ci --no-audit --no-fund \
    && test "$(node -p "require('./node_modules/@openai/codex/package.json').version")" = "${CODEX_CLI_VERSION}" \
    && ln -s /opt/vedicway/node_modules/.bin/codex /usr/local/bin/codex \
    && npx playwright install --with-deps chromium \
    && rm -rf /root/.cache /var/lib/apt/lists/*

COPY backend ./backend
COPY scripts/wheelhouse_contract.py ./scripts/wheelhouse_contract.py
COPY --from=pyjhora . /tmp/pyjhora-wheelhouse
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install "uv==0.11.6" \
    && cd /opt/vedicway/backend \
    && uv sync --frozen --no-dev --active --no-editable \
    && python /opt/vedicway/scripts/wheelhouse_contract.py /tmp/pyjhora-wheelhouse \
    && /opt/venv/bin/pip install --no-index --find-links=/tmp/pyjhora-wheelhouse pyjhora-mcp==0.1.0 \
    && cd /opt/vedicway \
    && rm -rf /tmp/pyjhora-wheelhouse \
    && groupadd --gid 10001 vedicway \
    && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin vedicway \
    && mkdir -p /var/lib/vedicway/data /var/lib/vedicway/media /var/lib/vedicway/codex-home /var/lib/vedicway/agent-workdir \
    && chown -R 10001:10001 /var/lib/vedicway /ms-playwright /opt/vedicway/backend

COPY docker/backend/entrypoint.sh /usr/local/bin/vedicway-entrypoint
COPY docker/backend/run-alembic.sh /usr/local/bin/vedicway-run-alembic
RUN chmod 0555 /usr/local/bin/vedicway-entrypoint /usr/local/bin/vedicway-run-alembic

USER 10001:10001
WORKDIR /opt/vedicway/backend

ENV VEDICWAY_DATA_DIR=/var/lib/vedicway/data \
    VEDICWAY_MEDIA_DIR=/var/lib/vedicway/media \
    VEDICWAY_CODEX_HOME=/var/lib/vedicway/codex-home \
    VEDICWAY_AGENT_WORKDIR=/var/lib/vedicway/agent-workdir \
    VEDICWAY_CODEX_EXECUTABLE=/usr/local/bin/codex \
    HOME=/var/lib/vedicway/codex-home

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=4s --start-period=30s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/ready', timeout=2).read()" || exit 1

ENTRYPOINT ["/usr/local/bin/vedicway-entrypoint"]
CMD ["uvicorn", "vedicway_backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-server-header"]
