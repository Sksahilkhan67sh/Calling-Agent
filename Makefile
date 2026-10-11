.PHONY: install lock up down logs migrate test cov lint format typecheck check-deploy security shell contract
SHELL := /bin/bash
COMPOSE = docker compose --env-file .env -f docker/compose.dev.yml
BACKEND = cd backend &&

install:
	python -m venv .venv && . .venv/bin/activate && pip install --require-hashes -r backend/requirements/dev.txt

lock:
	$(BACKEND) pip-compile --generate-hashes --strip-extras --allow-unsafe -o requirements/base.txt requirements/base.in
	$(BACKEND) pip-compile --generate-hashes --strip-extras --allow-unsafe -o requirements/prod.txt requirements/prod.in
	$(BACKEND) pip-compile --generate-hashes --strip-extras --allow-unsafe -o requirements/dev.txt requirements/dev.in
	@echo "Check new pins are at least 14 days old (docs/phase-1/DECISIONS.md D-02)."

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=100

migrate:
	$(COMPOSE) run --rm migrate

test:
	$(BACKEND) python -m pytest -q

cov:
	$(BACKEND) python -m pytest -q --cov --cov-fail-under=90

lint:
	$(BACKEND) ruff check . && ruff format --check .

format:
	$(BACKEND) ruff format . && ruff check . --fix

typecheck:
	$(BACKEND) mypy .

check-deploy:
	$(BACKEND) set -a && eval "$$(python scripts/gen_throwaway_env.py)" && set +a && \
	  DJANGO_SETTINGS_MODULE=config.settings.prod python manage.py check --deploy --fail-level WARNING

security:
	$(BACKEND) bandit -q -r apps config -ll
	$(BACKEND) pip-audit -r requirements/prod.txt -r requirements/dev.txt --require-hashes

contract:
	$(BACKEND) python scripts/check_api_contract.py

shell:
	$(COMPOSE) exec api python manage.py shell
