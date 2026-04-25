.PHONY: help install backend frontend dev clean

help:
	@echo "Targets:"
	@echo "  install    install Python + Node deps"
	@echo "  backend    run uvicorn on :8000 (activate venv first)"
	@echo "  frontend   run vite on :5173"
	@echo "  dev        run backend and frontend in parallel"
	@echo "  clean      remove __pycache__ and node_modules"

install:
	pip install -r requirements.txt
	cd frontend && npm install

backend:
	uvicorn backend.main:app --reload --port 8000 --host 127.0.0.1

frontend:
	cd frontend && npm run dev

# Run both in parallel; Ctrl-C stops both. Requires GNU make.
dev:
	@$(MAKE) -j2 backend frontend

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf frontend/node_modules frontend/dist
