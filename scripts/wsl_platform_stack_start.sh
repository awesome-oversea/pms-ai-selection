#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.wsl-platform.yml"

printf 'Starting WSL platform stack using %s\n' "$COMPOSE_FILE"

docker compose -f "$COMPOSE_FILE" up -d \
  redis-master redis-replica-1 redis-replica-2 \
  redis-sentinel-1 redis-sentinel-2 redis-sentinel-3 \
  keycloak-db keycloak \
  flink-jobmanager flink-taskmanager

echo
echo "Current stack status:"
docker compose -f "$COMPOSE_FILE" ps

echo
echo "Recommended next checks:"
echo "  redis-cli -p 26379 SENTINEL get-master-addr-by-name mymaster"
echo "  curl http://localhost:19000/health/ready"
echo "  curl http://localhost:18082/realms/pms-dev/.well-known/openid-configuration"
echo "  curl http://localhost:18081/overview"
echo
echo "Suggested local env:"
echo "  REDIS_SENTINEL_ENABLED=true"
echo "  REDIS_SENTINEL_MASTER_NAME=mymaster"
echo "  REDIS_SENTINEL_NODES=localhost:26379,localhost:26380,localhost:26381"
echo "  SEC_OIDC_ENABLED=true"
echo "  SEC_OIDC_ISSUER_URL=http://localhost:18082/realms/pms-dev"
echo "  SEC_OIDC_CLIENT_ID=pms-web"
echo "  SEC_OIDC_CLIENT_SECRET=pms-secret"
