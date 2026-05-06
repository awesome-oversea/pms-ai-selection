#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.wsl-qdrant-cluster.yml"

printf 'Starting Qdrant HA cluster using %s\n' "$COMPOSE_FILE"

docker compose -f "$COMPOSE_FILE" up -d \
  qdrant-node-1 qdrant-node-2 qdrant-node-3

echo
echo "Current stack status:"
docker compose -f "$COMPOSE_FILE" ps

echo
echo "Recommended next checks:"
echo "  curl http://localhost:16333/cluster"
echo "  curl http://localhost:16433/cluster"
echo "  curl http://localhost:16533/cluster"
echo
echo "Suggested local env:"
echo "  QDRANT_CLUSTER_ENABLED=true"
echo "  QDRANT_URL=http://localhost:16333"
echo "  QDRANT_WRITE_URL=http://localhost:16333"
echo "  QDRANT_READ_URLS=http://localhost:16433,http://localhost:16533"
echo "  QDRANT_SHARD_NUMBER=2"
echo "  QDRANT_REPLICATION_FACTOR=2"
echo "  QDRANT_WRITE_CONSISTENCY_FACTOR=2"
