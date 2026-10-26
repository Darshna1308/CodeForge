# syntax=docker/dockerfile:1
# Build context: repository root.
FROM python:3.12-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY packages/core /src/packages/core
COPY apps/worker/pyproject.toml /src/apps/worker/pyproject.toml
COPY apps/worker/codeforge_worker /src/apps/worker/codeforge_worker
RUN pip install /src/packages/core /src/apps/worker

# Only the static docker CLI binary is taken from the official image.
FROM docker:27-cli AS dockercli

FROM python:3.12-slim
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=build /opt/venv /opt/venv
WORKDIR /app
# The worker drives the Docker daemon through the mounted socket, which makes it
# a privileged component (see docs/SECURITY.md). Untrusted code never runs here:
# it runs in sibling sandbox containers that have no access to the socket.
EXPOSE 9100
CMD ["python", "-m", "codeforge_worker.main"]
