.PHONY: backup build compose-config demo lint migrate restore run test validate worker

run:
	uvicorn app.main:app --reload --port 8080

worker:
	python -m app.worker

migrate:
	alembic upgrade head

test:
	pytest -q

lint:
	ruff check .

validate:
	pytest -q
	ruff check .
	python -m compileall -q app connectors migrations mcp_server.py

build:
	docker compose build

compose-config:
	docker compose config

demo:
	docker compose up --build

backup:
	python -m app.operations backup --output backups/manual

restore:
	@echo "Run: python -m app.operations restore --source <backup-directory> --force"
