# syntax=docker/dockerfile:1
# Base image is pinned to a minor line, never `latest`. Pin by digest in your registry policy.
FROM python:3.14-slim-bookworm AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
RUN python -m venv /opt/venv
COPY backend/requirements/prod.txt /tmp/prod.txt
# Hash-enforced install; all dependencies ship wheels, so no compiler is needed.
RUN /opt/venv/bin/pip install --require-hashes --only-binary=:all: -r /tmp/prod.txt

FROM python:3.14-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=config.settings.prod
RUN groupadd --system --gid 10001 app && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=app:app backend/ /app/
COPY --chown=app:app docker/gunicorn.conf.py /app/gunicorn.conf.py
COPY --chown=app:app docker/entrypoint.sh /entrypoint.sh
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import os,urllib.request as u; h=os.environ['DJANGO_ALLOWED_HOSTS'].split(',')[0].strip(); u.urlopen(u.Request('http://127.0.0.1:8000/healthz', headers={'Host': h}), timeout=3)"]
ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "config.asgi:application", "-c", "gunicorn.conf.py"]
