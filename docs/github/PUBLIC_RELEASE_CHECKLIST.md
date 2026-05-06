# Public Release Checklist

## Repository Hygiene

- Remove `.env` and any local credential files.
- Remove `.venv`, `node_modules`, `.next`, caches and local runtime databases.
- Remove logs that may include tokens, request ids, tenant ids or internal endpoints.
- Keep `.env.example` only with placeholder values.
- Keep screenshots under `docs/github/screenshots` after confirming they contain no secrets.
- Keep acceptance evidence as summary Markdown unless JSON artifacts have been sanitized.

## Recommended Public Files

- Root `README.md` adapted from `docs/github/README.md`.
- `docs/github/MVP_SCOPE.md`.
- `docs/github/DEMO_SCRIPT.md`.
- `docs/github/ARCHITECTURE.md`.
- `docs/github/ACCEPTANCE_EVIDENCE.md`.
- `docs/github/SCREENSHOT_GUIDE.md`.
- `docs/github/ENV_EXAMPLE.md`.
- `docs/github/REPO_DESCRIPTION.md`.

## Files To Exclude Or Review Carefully

- `.env`.
- `logs/`.
- `storage/`.
- `.venv/`.
- `frontend/node_modules/`.
- `frontend/.next/`.
- `artifacts/runtime/`.
- Large raw `artifacts/` subfolders unless sanitized.
- Any document containing customer, supplier, account, credential or deployment secrets.

## GitHub Positioning

Use a direct, defensible positioning:

`Portfolio MVP for an AI-powered cross-border e-commerce product selection PMS, featuring multi-role workbench, human approval workflow, local ERP feedback loop and business acceptance evidence.`

Avoid overclaiming:

- Do not say all marketplace APIs are production-connected.
- Do not say it is production SaaS ready.
- Do not lead with monitoring, HA or Kubernetes.
- Do not present local mock data as real merchant data.

## Before First Push

1. Run the local verification commands in `ACCEPTANCE_EVIDENCE.md`.
2. Capture screenshots following `SCREENSHOT_GUIDE.md`.
3. Review the generated screenshots for secrets or private identifiers.
4. Copy the public README content to the root README or link to `docs/github/README.md`.
5. Confirm `.gitignore` excludes runtime output and dependency directories.
6. If this folder is published without code, add a note that code is available on request or in the main repository.

## Suggested GitHub Topics

- `ai-product-selection`
- `cross-border-ecommerce`
- `fastapi`
- `nextjs`
- `multi-agent`
- `human-in-the-loop`
- `business-workflow`
- `portfolio-project`

## Public Demo Options

- Best short-term option: GitHub repository with README, screenshots and demo GIF.
- Stronger option: Vercel frontend preview with backend data mocked through sanitized API fixtures.
- Full local option: Docker Compose backend plus Next.js frontend, documented as a developer demo.

## Release Decision

Current state is suitable for a public MVP portfolio release after sanitization. It is not yet suitable to market as a live commercial integration platform because several external APIs still require real credentials.
