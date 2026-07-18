.PHONY: test test-worker test-api test-api-pg test-pg-up test-pg-down test-all

PG_CONTAINER ?= reenigne-pg
PG_PORT      ?= 55432
PG_URL       ?= postgresql+asyncpg://postgres:postgres@localhost:$(PG_PORT)/reenigne_test

test: test-worker test-api

test-worker:
	cd packages/worker && .venv/bin/pytest -q

test-api:
	cd apps/api && .venv/bin/pytest -q

## Run the API suite against a real Postgres.
## SQLite cannot catch uuid-vs-varchar mismatches or driver-level parameter
## encoding errors, because it has no distinct uuid type.
test-api-pg: test-pg-up
	cd apps/api && DATABASE_URL="$(PG_URL)" .venv/bin/pytest -q

test-pg-up:
	@docker inspect $(PG_CONTAINER) >/dev/null 2>&1 || \
		docker run -d --name $(PG_CONTAINER) \
			-e POSTGRES_PASSWORD=postgres \
			-e POSTGRES_DB=reenigne_test \
			-p $(PG_PORT):5432 postgres:16-alpine >/dev/null
	@docker start $(PG_CONTAINER) >/dev/null 2>&1 || true
	@printf 'waiting for postgres'; \
	for i in $$(seq 1 30); do \
		docker exec $(PG_CONTAINER) pg_isready -U postgres >/dev/null 2>&1 && break; \
		printf '.'; sleep 1; \
	done; echo ' ready'

test-pg-down:
	-docker rm -f $(PG_CONTAINER) >/dev/null 2>&1

## Everything, both backends. Run this before declaring a schema change done.
test-all: test-worker test-api test-api-pg
