FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/pdeue/backend:/opt/pdeue \
    DATABASE_URL=sqlite:////var/lib/pdeue-paper-soak/pdeue.db \
    PDEUE_CREDENTIAL_BROKER=ephemeral-memory \
    PDEUE_CREDENTIAL_LEASE_TTL_SECONDS=300

WORKDIR /opt/pdeue
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && groupadd --system pdeue \
    && useradd --system --gid pdeue --home-dir /var/lib/pdeue-paper-soak pdeue \
    && mkdir -p /var/lib/pdeue-paper-soak \
    && chown pdeue:pdeue /var/lib/pdeue-paper-soak
COPY fleet_engine.py /opt/pdeue/fleet_engine.py
COPY backend/app /opt/pdeue/backend/app
COPY backend/scripts /opt/pdeue/backend/scripts
COPY backend/tests/fixtures/static_crypto_history.jsonl /opt/pdeue/backend/tests/fixtures/static_crypto_history.jsonl
COPY contracts/schemas /opt/pdeue/contracts/schemas
COPY docs/manuals /opt/pdeue/docs/manuals
RUN chmod -R a+rX /opt/pdeue/fleet_engine.py /opt/pdeue/backend /opt/pdeue/contracts /opt/pdeue/docs
COPY --chmod=0755 deploy/docker/entrypoint.sh /opt/pdeue/entrypoint.sh

USER pdeue
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]
ENTRYPOINT ["/opt/pdeue/entrypoint.sh"]
