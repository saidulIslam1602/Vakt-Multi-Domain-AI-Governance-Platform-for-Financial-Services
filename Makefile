# ─── Allergo Nordic — developer convenience targets ───────────────────────────
# Mirrors exactly what GitHub Actions CI runs, so 'make lint' is green iff
# CI would be green.  Run before every git push.
#
# Usage:
#   make up            # start the full stack (infra first, then services)
#   make down          # stop everything
#   make restart       # restart app services only (keeps postgres/azurite data)
#   make lint          # ruff + terraform fmt-check (fast, no deps needed)
#   make lint-fix      # ruff --fix + terraform fmt (auto-corrects everything)
#   make test          # run pytest for all services (requires Python 3.12)

SERVICES := ingest-service document-service chat-service processing-service search-service shared-lib

.PHONY: lint lint-fix test up down restart

# ── up: start full stack (infra first so services can connect) ────────────────
up:
	@echo "▶ Starting infrastructure (postgres, azurite, rabbitmq, elasticsearch)..."
	@docker compose up -d postgres azurite rabbitmq elasticsearch
	@echo "  Waiting for infra to be healthy..."
	@docker compose wait postgres azurite rabbitmq elasticsearch 2>/dev/null || sleep 15
	@echo "▶ Starting application services..."
	@docker compose up -d
	@echo "✅ Stack is up. Frontend: http://localhost:3001"

# ── down: stop everything ─────────────────────────────────────────────────────
down:
	@docker compose down

# ── restart: restart only app services (preserves infra & data volumes) ───────
restart:
	@docker compose restart ingest-service document-service chat-service processing-service search-service frontend

# ── lint: exactly what CI runs ────────────────────────────────────────────────
lint:
	@echo "▶ ruff check (all services)..."
	@FAILED=""; \
	for svc in $(SERVICES); do \
		result=$$(cd services/$$svc && ruff check src tests --output-format=concise 2>&1 | grep -v "^warning:" | grep -v "^  -"); \
		if echo "$$result" | grep -q "All checks passed"; then \
			echo "  ✅ $$svc"; \
		else \
			echo "  ❌ $$svc:"; echo "$$result"; FAILED="$$FAILED $$svc"; \
		fi; \
	done; \
	if [ -n "$$FAILED" ]; then exit 1; fi
	@echo "▶ terraform fmt -check..."
	@cd infra && terraform fmt -check && echo "  ✅ terraform fmt clean"
	@echo "✅ All lint checks passed."

# ── lint-fix: auto-correct everything before committing ──────────────────────
lint-fix:
	@echo "▶ ruff --fix (all services)..."
	@for svc in $(SERVICES); do \
		cd services/$$svc && ruff check src tests --fix --quiet 2>/dev/null; cd ../..; \
	done
	@echo "▶ terraform fmt..."
	@cd infra && terraform fmt
	@echo "✅ Auto-fix complete. Run 'make lint' to verify."

# ── test: run pytest for all Python services ─────────────────────────────────
test:
	@for svc in $(SERVICES); do \
		echo "▶ pytest $$svc..."; \
		cd services/$$svc && pytest --tb=short -q 2>&1 | tail -5; cd ../..; \
	done
