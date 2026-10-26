# CodeForge developer workflow. Run `make help` for the list.
SHELL := /bin/bash
COMPOSE ?= docker compose
PY ?= python3
WORKERS ?= 2
API_URL ?= http://localhost:8000

.DEFAULT_GOAL := help
.PHONY: help up down build logs ps migrate seed worker scale test test-backend test-web test-e2e loadtest dev-install dev-api dev-worker dev-web sandbox-image clean

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[32m%-14s\033[0m %s\n", $$1, $$2}'

up: ## Build and start the whole stack (http://localhost:3000)
	$(COMPOSE) up --build -d
	@echo "web  http://localhost:3000   api  $(API_URL)/docs   metrics  $(API_URL)/metrics"

down: ## Stop the stack (keeps data volumes)
	$(COMPOSE) down

build: ## Build all images (including the sandbox image)
	$(COMPOSE) build

logs: ## Tail logs from api and workers
	$(COMPOSE) logs -f --tail=100 api worker

ps: ## Show service status
	$(COMPOSE) ps

migrate: ## Apply database migrations
	$(COMPOSE) run --rm migrate alembic upgrade head

seed: ## (Re)seed problems and tests (idempotent)
	$(COMPOSE) run --rm migrate python -m codeforge_api.seed

worker: ## Scale the worker pool: make worker WORKERS=4
	$(COMPOSE) up -d --no-deps --scale worker=$(WORKERS) worker

test: test-backend test-web ## Run backend + frontend test suites

test-backend: ## pytest: core, API, worker, sandbox (needs local Postgres/Redis/Docker, see README)
	$(PY) -m pytest

test-web: ## vitest component and reducer tests
	cd apps/web && npm test

test-e2e: ## Judge real programs through a running stack (API_URL=...)
	CODEFORGE_API_URL=$(API_URL) $(PY) -m pytest tests/integration -q -p no:cacheprovider

loadtest: ## Headless Locust run against API_URL; results saved under tests/load/results
	./tests/load/run.sh $(API_URL)

dev-install: ## Install Python packages (editable) and web deps for local development
	$(PY) -m pip install -e packages/core -e "apps/api[test]" -e "apps/worker[test]" locust
	cd apps/web && npm install

dev-api: ## Run the API locally with autoreload
	uvicorn codeforge_api.main:app --reload --port 8000

dev-worker: ## Run a worker locally (uses the host Docker daemon)
	$(PY) -m codeforge_worker.main

dev-web: ## Run the Next.js dev server
	cd apps/web && npm run dev

sandbox-image: ## Build only the sandbox image
	docker build -t codeforge-sandbox:latest infrastructure/sandbox

clean: ## Stop everything, delete volumes and leftover sandbox containers
	$(COMPOSE) down -v --remove-orphans
	-docker ps -aq --filter label=codeforge.sandbox=1 | xargs -r docker rm -f
