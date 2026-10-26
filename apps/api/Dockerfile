# syntax=docker/dockerfile:1
# Build context: repository root (shared packages/core is installed alongside).
FROM python:3.12-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY packages/core /src/packages/core
COPY apps/api/pyproject.toml /src/apps/api/pyproject.toml
COPY apps/api/codeforge_api /src/apps/api/codeforge_api
RUN pip install /src/packages/core /src/apps/api

FROM python:3.12-slim
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin app
COPY --from=build /opt/venv /opt/venv
WORKDIR /app
COPY apps/api/alembic.ini /app/alembic.ini
COPY apps/api/alembic /app/alembic
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"
CMD ["uvicorn", "codeforge_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
