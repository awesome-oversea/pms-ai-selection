# Repository Guidelines

## Project Structure & Module Organization
- `src/`: core application code. Key areas: `api/v1/endpoints/` (FastAPI routes), `services/` (business logic), `repositories/` (DB access), `models/` (ORM + schemas), `infrastructure/` (DB/Redis/Qdrant/LLM integrations), `workers/` (background workers).
- `tests/`: pytest suite. Main regression coverage lives in `test_api_integration.py` and `test_minimal_trusted_phase34.py`.
- `docs/`, `tasks/`, `验收标准/`: architecture, planning, and acceptance artifacts.
- `alembic/`: migration scaffold. `k8s/`, `scripts/`, `web/` contain deployment helpers and UI assets.

## Build, Test, and Development Commands
- `python scripts/install_python_deps.py --run-check` — create/update `.venv`, install dev deps, and verify the local Python runtime.
- `python scripts/start_local_services.py` — start the local dependency services with Docker Compose.
- `docker compose -f docker-compose.yml up -d --build --no-deps app` — start the backend container locally after dependencies are ready.
- `python -m pytest tests/test_api_integration.py tests/test_minimal_trusted_phase34.py -q` — run the current trusted regression suite.
- `python -m pytest -q` — run all tests.
- `python -m py_compile src/main.py` — quick syntax check for edited files.
- `ruff check src tests` — lint Python code.
- `mypy src` — run strict type checks.

## Coding Style & Naming Conventions
- Python 3.11+, 4-space indentation, UTF-8 files.
- Follow `ruff` + `mypy --strict` expectations from `pyproject.toml`.
- Modules/functions/variables: `snake_case`; classes: `PascalCase`; constants: `UPPER_SNAKE_CASE`.
- Keep endpoint layers thin; put business logic in `services/` and persistence in `repositories/`.
- Prefer precise edits over broad rewrites.

## Testing Guidelines
- Framework: `pytest` with `pytest-asyncio` (`asyncio_mode = auto`).
- Test files: `test_*.py`; test functions: `test_*`.
- Add or update tests for every behavior change, especially around selection, knowledge, LLM, worker, tenant, and audit flows.
- Prefer small focused regressions plus the trusted full run above.

## Commit & Pull Request Guidelines
- Use short, scoped commit messages, e.g. `T6.4: add tenant quota enforcement for llm route`.
- Reference task/phase IDs when applicable (`T6.3`, `P6-A07`).
- PRs should include: summary, affected modules, test evidence, config/migration impact, and screenshots only for UI changes.

## Security & Configuration Tips
- Do not commit secrets. Use `.env` / environment variables such as `DB_URL`, `SEC_SECRET_KEY`, `QDRANT_*`, `LLM_*`.
- Keep tenant isolation, audit logging, and request/trace propagation intact when changing APIs or services.
