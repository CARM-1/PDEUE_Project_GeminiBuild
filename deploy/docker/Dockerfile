FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/pdeue/backend \
    PDEUE_CREDENTIAL_BROKER=ephemeral-memory \
    PDEUE_CREDENTIAL_LEASE_TTL_SECONDS=300

WORKDIR /opt/pdeue
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && groupadd --system pdeue \
    && useradd --system --gid pdeue --home-dir /var/lib/pdeue-paper-soak pdeue \
    && mkdir -p /var/lib/pdeue-paper-soak \
    && chown pdeue:pdeue /var/lib/pdeue-paper-soak
COPY --chown=pdeue:pdeue backend /opt/pdeue/backend
COPY --chown=pdeue:pdeue deploy/docker/entrypoint.sh /opt/pdeue/entrypoint.sh

USER pdeue
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]
ENTRYPOINT ["/opt/pdeue/entrypoint.sh"]
