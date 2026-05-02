.PHONY: up down logs-api logs-ingestor test fmt

up:
	docker compose up --build -d

down:
	docker compose down

logs-api:
	docker compose logs -f api

logs-ingestor:
	docker compose logs -f ingestor

test:
	python -m unittest discover -s tests -v
