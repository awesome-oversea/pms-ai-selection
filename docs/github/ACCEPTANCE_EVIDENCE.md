# Acceptance Evidence

This file summarizes local verification evidence that can be cited in a public GitHub README or portfolio post. Keep the detailed JSON artifacts private or sanitized before publishing.

## Latest Verified Business Evidence

| Area | Date | Status | Evidence |
| --- | --- | --- | --- |
| Business scenario runtime | 2026-04-22 | Passed | `artifacts/ops/business_scenario_runtime_acceptance.json` |
| GDELT public signal | 2026-04-22 | Passed | `artifacts/ops/gdelt_signal_validation.json` |
| External collection readiness | 2026-04-22 | Passed | `artifacts/ops/local_external_collection_readiness_latest.json` |
| Selection main chain | 2026-04-22 | Passed | `artifacts/local_main_chain/20260422T080638Z/summary.json` |
| Selection close loop | 2026-04-22 | Passed | `artifacts/local_close_loop/20260422T080638Z/summary.json` |
| Multi-role workbench | 2026-04-22 | Passed | `artifacts/local_multi_role_workbench/20260422T023959Z/summary.json` |

## Business Scenario Runtime

- Accepted: `true`.
- Cases: `11 / 11` accepted.
- Runtime source: real local Kafka path, not memory fallback.
- Business raw topics verified: `raw_amazon`, `raw_tiktok`, `raw_trends`, `raw_1688`, `raw_news`.

## GDELT Public Signal

- Accepted: `true`.
- Real result source: `live`.
- Real article count: `5`.
- Business meaning: public global news/event signal can be classified and associated with product categories.
- Kafka path: validated through `raw_news` inbound topic.

## External Collection Readiness

- Accepted: `true`.
- Checks passed: config matrix, credential gap disclosure, runtime source probes, fallback semantics, degradation contracts, GDELT live probe and latest summary sync.
- Public wording: formal external marketplace APIs are credential-bound; local validation sources are available for MVP demonstration.

## Selection Main Chain

Artifact: `artifacts/local_main_chain/20260422T080638Z/summary.json`

Passed checks:

- Task created and dispatched.
- Local task execution completed.
- Multi-stage approval chain completed.
- Manual intervention recorded.
- Adoption execution completed.
- Final task detail consistent.
- Audit logs captured.

## Selection Close Loop

Artifact: `artifacts/local_close_loop/20260422T080638Z/summary.json`

Passed checks:

- Adoption execution completed.
- Execution feedback synced.
- Rescore persisted to task.
- Feature asset ready.
- Feedback loop status ready.
- Profit trace ready.
- Audit logs captured.

Key sample metrics:

- Rescore score: `85.8`.
- Decision: `GO`.
- 7-day sales: `12`.
- Review rating: `4.6`.
- Review count: `13`.
- Gross profit: `139.0`.
- Margin rate: `28.5%`.
- Available inventory: `18`.

## Multi-Role Workbench

Artifact: `artifacts/local_multi_role_workbench/20260422T023959Z/summary.json`

Passed checks:

- Selection workbench exposes business signal.
- Manager overview covers pending approval and closed loop.
- Procurement workbench tracks execution chain.
- Finance workbench has profit and daily KPI.
- Operations workbench has governance and audit.
- Scenario manifest and artifacts complete.
- Audit logs capture multi-role chain.

Roles covered:

- `operator-1`: create task and confirm recommendation.
- `manager-1`: final approval and business overview.
- `procurement-1`: adoption and SCM / WMS / OMS execution.
- `finance-1`: profit and KPI verification.
- `ops-admin-1`: governance and audit verification.

## Verification Commands

Use these commands locally before publishing a release snapshot:

```powershell
python -m py_compile src/infrastructure/kafka.py scripts/bootstrap_local_gdelt_signal.py src/services/local_external_collection_readiness_service.py
python -m pytest tests/test_kafka_runtime.py tests/test_gdelt_signal_acceptance.py -q
python scripts/bootstrap_business_scenario_runtime.py
python scripts/bootstrap_local_gdelt_signal.py
python scripts/run_local_external_collection_readiness.py
python scripts/run_local_selection_main_chain_acceptance.py
python scripts/run_local_selection_close_loop_acceptance.py
```

Latest known result:

- `tests/test_kafka_runtime.py tests/test_gdelt_signal_acceptance.py`: `6 passed`.
- Business scenario runtime acceptance: `11 / 11` accepted.
- GDELT signal validation: accepted, live source, 5 articles.
- Main chain acceptance: accepted.
- Close loop acceptance: accepted.

## Public Evidence Policy

- Publish summaries and selected screenshots.
- Do not publish raw `.env`, private logs, runtime databases or credentials.
- If publishing JSON artifacts, sanitize tenant ids, trace ids, request ids, supplier names and any commercially sensitive terms.
