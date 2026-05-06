#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.wsl-postgres-ha.yml"

printf 'Starting PostgreSQL HA stack using %s\n' "$COMPOSE_FILE"

docker compose -f "$COMPOSE_FILE" up -d \
  pg-primary pg-standby-1 pg-standby-2 pgpool

echo
echo "Current stack status:"
docker compose -f "$COMPOSE_FILE" ps

echo
echo "Recommended next checks:"
echo "  docker exec pms-pg-primary-wsl repmgr cluster show"
echo "  docker exec pms-pg-primary-wsl psql -U pms -d pms_db -c \"select application_name,state,sync_state from pg_stat_replication;\""
echo "  docker exec pms-pg-standby-1-wsl psql -U pms -d pms_db -c \"select pg_is_in_recovery();\""
echo "  docker exec pms-pgpool-wsl psql -U pms -d pms_db -c \"show pool_nodes;\""
echo
echo "Suggested local env:"
echo "  DB_URL=postgresql+asyncpg://pms:pms_dev_2024@localhost:15432/pms_db"
echo "  DATABASE_URL=postgresql+asyncpg://pms:pms_dev_2024@localhost:15432/pms_db"
echo "  DB_WRITE_URL=postgresql+asyncpg://pms:pms_dev_2024@localhost:15432/pms_db"
echo "  DB_READ_URLS=postgresql+asyncpg://pms:pms_dev_2024@localhost:15436/pms_db,postgresql+asyncpg://pms:pms_dev_2024@localhost:15437/pms_db"
echo "  DB_READ_WRITE_SPLIT=true"
echo
echo "Suggested failover drill:"
echo "  docker stop pms-pg-primary-wsl"
echo "  docker exec pms-pg-standby-1-wsl repmgr cluster show"
echo "  docker exec pms-pgpool-wsl psql -U pms -d pms_db -c \"show pool_nodes;\""
