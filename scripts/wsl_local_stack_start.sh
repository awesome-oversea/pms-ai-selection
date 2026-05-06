#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.wsl-local.yml"

printf 'Starting WSL local infra stack using %s\n' "$COMPOSE_FILE"

docker compose -f "$COMPOSE_FILE" up -d kong-database opensearch neo4j
docker compose -f "$COMPOSE_FILE" up -d kong-migrations
docker compose -f "$COMPOSE_FILE" up -d kong-gateway

echo "\nChecking stack status..."
docker compose -f "$COMPOSE_FILE" ps

echo "\nRecommended next checks:"
echo "  curl http://localhost:8001/status"
echo "  curl http://localhost:19200"
echo "  docker exec pms-neo4j-local /var/lib/neo4j/bin/cypher-shell -a bolt://127.0.0.1:7687 -u neo4j -p pms_graph_dev 'RETURN 1;'"
