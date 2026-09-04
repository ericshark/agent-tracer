# Convenience targets for local development.

VENV ?= .venv
PY := $(VENV)/bin/python

.PHONY: install dev-api dev-web migrate seed test test-server test-sdk test-web lint up down demo

install:            ## Create venv, install server+sdk (editable) and web deps
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -e "server[dev]" -e "sdk[dev]"
	cd web && npm install

dev-api:            ## Run the API with hot reload (needs DATABASE_URL)
	cd server && ../$(PY) -m uvicorn app.main:app --reload

dev-web:            ## Run the Vite dev server (proxies /api to :8000)
	cd web && npm run dev

migrate:            ## Apply database migrations
	cd server && ../$(VENV)/bin/alembic upgrade head

seed:               ## Seed demo user/project/API key + example traces
	cd server && ../$(PY) -m app.seed

test: test-server test-sdk test-web  ## Run every test suite

test-server:
	cd server && ../$(PY) -m pytest -q

test-sdk:
	cd sdk && ../$(PY) -m pytest -q

test-web:
	cd web && npm run test

lint:
	$(VENV)/bin/ruff check server sdk

up:                 ## Build & start the full stack with Docker Compose
	docker compose up --build -d

down:
	docker compose down

demo:               ## Send a live demo trace (set AGENT_TRACER_API_KEY first)
	cd sdk && ../$(PY) examples/demo_agent.py --runs 2 --fail
