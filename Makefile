.PHONY: dev db-up db-down migrate seed test-backend install-backend install-frontend

# ── Local Dev ──────────────────────────────────────────────────────────────

dev:
	docker compose up --build

db-up:
	docker compose up -d db

db-down:
	docker compose down

# ── Backend ────────────────────────────────────────────────────────────────

install-backend:
	cd backend && pip install -r requirements.txt

migrate:
	cd backend && alembic upgrade head

seed:
	DATABASE_URL=postgresql://raguser:ragpassword@localhost:5432/ragdb python scripts/seed_demo.py

test-backend:
	cd backend && pytest tests/ -v

# ── Frontend ───────────────────────────────────────────────────────────────

install-frontend:
	cd frontend && npm install

dev-frontend:
	cd frontend && npm run dev

# ── DB shortcut ────────────────────────────────────────────────────────────

psql:
	psql postgresql://raguser:ragpassword@localhost:5432/ragdb

# ── Verify pgvector works ─────────────────────────────────────────────────

verify-pgvector:
	psql postgresql://raguser:ragpassword@localhost:5432/ragdb \
	  -c "SELECT '[1,2,3]'::vector <=> '[4,5,6]'::vector;"
