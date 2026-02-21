.PHONY: install run worker migrate generate-models test lint fmt db-create db-drop crawl seed

DB_NAME ?= agent_system

install:
	poetry install

run:
	poetry run flask --app app.factory:create_app run --port 8000 --reload

worker:
	poetry run celery -A app.worker:celery_app worker --loglevel=info --beat

migrate:
	@for f in $$(ls migrations/*.sql | sort); do \
		echo "Applying $$f ..."; \
		psql -d $(DB_NAME) -f $$f; \
	done

generate-models:
	poetry run python -m scripts.generate_models

test:
	poetry run pytest -v

lint:
	poetry run ruff check .

fmt:
	poetry run ruff format .

db-create:
	createdb $(DB_NAME)

db-drop:
	dropdb --if-exists $(DB_NAME)

crawl:
	poetry run celery -A app.worker:celery_app call run_full_crawl

seed:
	poetry run python -m scripts.seed_dev_data
