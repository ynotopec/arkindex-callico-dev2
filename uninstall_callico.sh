#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
DEPLOY_DIR="$REPO_ROOT/deployment"
COMPOSE_FILE="$DEPLOY_DIR/docker-compose.yml"
ENV_FILE="$DEPLOY_DIR/.callico-domains.env"

if [[ ! -d "$DEPLOY_DIR" ]]; then
  echo "Error: deployment directory '$DEPLOY_DIR' not found." >&2
  exit 1
fi

find_compose_command() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
    return 0
  fi

  if command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD=(docker-compose)
    return 0
  fi

  return 1
}

if ! find_compose_command; then
  echo "Error: neither 'docker compose' nor 'docker-compose' is available." >&2
  exit 1
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Error: docker compose file '$COMPOSE_FILE' not found." >&2
  exit 1
fi

if [[ -f "$ENV_FILE" ]]; then
  while IFS='=' read -r key value; do
    [[ -z "$key" || "$key" =~ ^# ]] && continue
    export "$key"="$value"
  done <"$ENV_FILE"
  echo "Loaded domain configuration from '$ENV_FILE'."
  echo "Using domains: Callico='${CALICO_DOMAIN:-}', MinIO='${MINIO_DOMAIN:-}', Console='${MINIO_CONSOLE_DOMAIN:-}'."
else
  echo "Warning: domain configuration file '$ENV_FILE' not found. Using default domains." >&2
fi

echo "Stopping Callico deployment using ${COMPOSE_CMD[*]}..."

pushd "$DEPLOY_DIR" >/dev/null
"${COMPOSE_CMD[@]}" down -v
popd >/dev/null

echo "Callico deployment stopped and resources removed."
