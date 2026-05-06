# Runbook / Oncall / SLA / Change Process

> NOTE: local install/startup topology and dependency ordering are maintained under `D:/Project/fms/docs/local-runtime/`.
> This runbook remains the operational-process supplement and should not be used as the primary local deployment guide.

## 1. Scope

This runbook is for the **current repository baseline**, not the ideal target architecture. It is intended for non-core engineers who need to perform basic operational actions safely.

## 2. SLA / SLO

- API availability target: **99.5%** in normal business hours
- Critical recovery target (P0): **30 min**
- High severity recovery target (P1): **2 hours**
- Release gate requirement: `python scripts/release_quality_gates.py all` must pass before production change

## 3. Oncall Rules

### Severity
- **P0**: API unavailable, database unavailable, major auth failure
- **P1**: key feature degraded, worker backlog high, repeated 5xx
- **P2**: partial feature issue, single dependency unstable

### Escalation
1. Confirm alert and affected scope
2. Check `/health`, `/ready`, `/metrics`, `/api/v1/metrics-dashboard`
3. Check `/api/v1/migrations/status` before schema-related actions
4. If unresolved in 15 minutes, escalate to tech owner

## 4. Change Process

### Before change
- Confirm task / issue scope
- Run trusted baseline tests
- Run release gates:
  - `python scripts/release_quality_gates.py smoke`
  - `python scripts/release_quality_gates.py migration-smoke`
  - `python scripts/release_quality_gates.py all`

### During release
- Apply compatible change first
- For DB changes, use Alembic revision flow
- Prefer expand-contract strategy for schema evolution

### After release
- Verify `/health` and `/ready`
- Verify `/api/v1/metrics-dashboard`
- Verify key APIs: auth / selection / knowledge / llm
- Review audit logs

## 5. Rollback Rules

- App rollback: revert to previous stable image / commit
- Schema rollback: use previous compatible Alembic revision
- Destructive schema change requires two-step rollout and compatibility window

## 6. Basic Operations for Non-Core Engineers

### Health check
- `GET /health`
- `GET /ready`

### Release gate
- `python scripts/release_quality_gates.py all`

### Migration status
- `GET /api/v1/migrations/status`

### Metrics dashboard
- `GET /api/v1/metrics-dashboard`

### Audit logs
- `GET /api/v1/audit/logs`

### Worker check
- Run worker entrypoint: `python -m src.workers.selection_worker`

## 7. Required Evidence

For any production-affecting change, keep:
- executed commands
- gate result
- affected modules
- rollback path
- post-release verification result
