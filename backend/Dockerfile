# ---------------------------------------------------------------------------
# Karya backend - production image
#
# Two stages so the runtime image contains no compiler, no pip cache and no
# build metadata: only Python, the resolved dependencies and the application.
#
# What this image is NOT: an orchestrator. It runs one uvicorn process with a
# configurable worker count. Replicas, rolling deploys, secret injection and
# autoscaling belong to whatever runs the container - see docs/PRODUCTION.md.
# ---------------------------------------------------------------------------

# Pinned to a digest-stable minor version rather than `3.12` or `latest`, so a
# rebuild months from now produces the same interpreter.
FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Dependencies are installed into a self-contained virtualenv that the runtime
# stage copies wholesale. Simpler and more predictable than --user installs, and
# it keeps everything Karya needs under one path.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copied before the source so the (slow, rarely-changing) dependency layer is
# cached across application edits.
COPY pyproject.toml constraints.txt README.md ./
COPY app ./app

# --require-hashes is deliberately NOT used: constraints.txt pins exact versions
# but not hashes, because hashes would have to be regenerated for every platform
# wheel and this project has no lock tooling yet. Version pinning is the
# reproducibility guarantee; see docs/PRODUCTION.md for the honest limits of it.
RUN pip install --constraint constraints.txt .

# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Non-root, with a fixed high uid/gid so a mounted volume's ownership is
# predictable and so the container cannot be confused with a host user.
RUN groupadd --gid 10001 karya \
 && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin karya

COPY --from=builder /opt/venv /opt/venv

WORKDIR /srv/karya
# Alembic is not installed as part of the package, so the migration scripts are
# copied explicitly. They are needed to run `alembic upgrade head` - which is a
# deploy step, NOT something this image does on startup: two replicas starting
# together would both try to migrate.
COPY --chown=root:root alembic.ini ./
COPY --chown=root:root alembic ./alembic
COPY --chown=root:root app ./app

# Root owns the code and the application user only reads it, so a compromised
# process cannot rewrite its own source.
USER karya

EXPOSE 8000

# Hits liveness, which never touches the database - so a database blip does not
# make Docker report the container unhealthy and restart it. Readiness (/ready)
# is what a load balancer should poll, and that one does check PostgreSQL.
# `python -c` rather than curl: the slim image has no curl, and installing one
# purely for a health check adds a package and a CVE surface for no benefit.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"]

# Exec form, so uvicorn is PID 1 and receives SIGTERM directly - no shell
# swallowing the signal. Uvicorn then stops accepting connections, lets in-flight
# requests finish within the grace period, and runs the lifespan shutdown that
# disposes the connection pool.
#
# WEB_CONCURRENCY is uvicorn's own env var for the worker count. It is left
# unset here on purpose: the right value depends on the CPU allocation and on
# the database connection budget, so the deployment decides.
#
# --no-access-log because Karya emits its own structured access line, which logs
# the matched route template rather than the raw path (a raw path can carry a
# search term) and carries the correlation id.
#
# NOTE what is deliberately absent: --proxy-headers / --forwarded-allow-ips.
# Those make uvicorn rewrite the client address from X-Forwarded-For, and Karya's
# per-address rate limits key on that address. Trusting the header from *any*
# peer would let any client spoof its address and bypass those limits entirely.
# A deployment behind a load balancer MUST add both, naming the balancer:
#
#   --proxy-headers --forwarded-allow-ips=10.0.0.7
#
# Without them every request appears to come from the proxy and shares one
# per-address budget. docs/PRODUCTION.md states this as a requirement.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "30", "--no-access-log"]
