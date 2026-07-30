.PHONY: run test lint demo
run:
	uvicorn app.main:app --reload --port 8080

test:
	pytest -q

lint:
	ruff check .

demo:
	docker compose up --build
