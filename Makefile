.PHONY: help setup web web-noreload mcp dev verify verify-openai verify-supabase verify-phase9 health-llm schema

UV ?= uv
PY ?= $(UV) run python

# Optional: point the web server at a specific env file.
# Example: make web ENV=.env.local
ENV ?= .env

help:
	@echo "Targets:"
	@echo "  setup           Install/sync deps via uv"
	@echo "  web             Start FastAPI web UI (reload)"
	@echo "  web-noreload    Start FastAPI web UI (no reload)"
	@echo "  mcp             Start MCP stdio server"
	@echo "  dev             Run web + mcp together"
	@echo "  verify          Run overall system verification"
	@echo "  verify-openai   Verify LLM connectivity"
	@echo "  verify-supabase Verify Supabase connectivity"
	@echo "  verify-phase9   Run Phase 9 verification script"
	@echo "  health-llm      Call web /health/llm endpoint"
	@echo "  schema          Reminder: apply Supabase DDL"

setup:
	$(UV) sync

web:
	SCIJUDGE_ENV_PATH=$(ENV) SCIJUDGE_WEB_HOST=127.0.0.1 SCIJUDGE_WEB_PORT=8000 SCIJUDGE_WEB_RELOAD=1 $(PY) run_web.py

web-noreload:
	SCIJUDGE_ENV_PATH=$(ENV) SCIJUDGE_WEB_HOST=127.0.0.1 SCIJUDGE_WEB_PORT=8000 SCIJUDGE_WEB_RELOAD=0 $(PY) run_web.py

# MCP uses stdio transport (intended to be launched by an MCP client/inspector).
mcp:
	$(PY) -m scientific_judgment_mcp.server

# Convenience: run both long-lived processes in parallel.
dev:
	$(MAKE) -j2 web mcp

verify:
	$(PY) verify_system.py

verify-openai:
	$(PY) verify_openai.py

verify-supabase:
	$(PY) verify_supabase.py

verify-phase9:
	$(PY) verify_phase9.py

health-llm:
	$(PY) -c "import httpx; r=httpx.get('http://127.0.0.1:8000/health/llm', timeout=30); print(r.status_code); print(r.text[:500])"

schema:
	@echo "Apply Supabase schema updates by running supabase/schema.sql in the Supabase SQL editor."
	@echo "(Needed for durable review_jobs + review_job_events persistence.)"
