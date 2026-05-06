# Public Environment Example

This file describes safe placeholder environment variables for a public GitHub MVP. Do not publish real `.env` values.

## Backend Example

```env
APP_ENV=local
APP_NAME=fms-ai-selection-pms
API_HOST=0.0.0.0
API_PORT=8000

DB_URL=postgresql+asyncpg://fms_user:fms_password@localhost:5432/fms
REDIS_URL=redis://localhost:6379/0
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=

SEC_SECRET_KEY=replace-with-local-dev-secret
ACCESS_TOKEN_EXPIRE_MINUTES=1440

LLM_PROVIDER=mock
LLM_API_KEY=
LLM_BASE_URL=
LLM_MODEL=

GDELT_ENABLED=true
GDELT_MODE=auto

AMAZON_SP_API_ENABLED=false
AMAZON_SP_API_CLIENT_ID=
AMAZON_SP_API_CLIENT_SECRET=
AMAZON_SP_API_REFRESH_TOKEN=

TIKTOK_BUSINESS_API_ENABLED=false
TIKTOK_BUSINESS_API_TOKEN=

ALI1688_OPEN_API_ENABLED=false
ALI1688_APP_KEY=
ALI1688_APP_SECRET=
```

## Frontend Example

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_APP_NAME=AI Product Selection PMS
```

## Public Demo Notes

- Set `LLM_PROVIDER=mock` for a safe public demo unless you intentionally configure a paid model provider locally.
- Keep GDELT enabled because it uses a public signal source and has already been validated locally.
- Keep Amazon, TikTok and 1688 disabled in public examples unless you have valid sandbox credentials.
- Never commit `.env`; commit only `.env.example` with placeholders.

## Local Startup Reference

```powershell
python scripts/install_python_deps.py --run-check
python scripts/start_local_services.py
docker compose -f docker-compose.yml up -d --build --no-deps app
cd frontend
npm install
npm run dev
```

If Docker dependencies are unavailable, run the backend in the documented local fallback mode and present the frontend with sanitized fixture data.
