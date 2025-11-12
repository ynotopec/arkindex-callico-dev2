#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${1:-callico}"

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Error: required command '$1' not found in PATH." >&2
        exit 1
    fi
}

require_command docker

if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD=(docker-compose)
else
    echo "Error: docker compose plugin or docker-compose binary is required." >&2
    exit 1
fi

if [ ! -d "$PROJECT_DIR" ]; then
    echo "Project directory '$PROJECT_DIR' not found. Nothing to uninstall."
    exit 0
fi

pushd "$PROJECT_DIR" >/dev/null || exit 1

COMPOSE_FILE=()
if [ -f docker-compose.yml ]; then
    COMPOSE_FILE=("-f" "docker-compose.yml")
elif [ -f compose.yml ]; then
    COMPOSE_FILE=("-f" "compose.yml")
fi

if [ ${#COMPOSE_FILE[@]} -gt 0 ] || [ -f docker-compose.yml ] || [ -f compose.yml ]; then
    "${COMPOSE_CMD[@]}" "${COMPOSE_FILE[@]}" down -v || true
else
    echo "Warning: no compose file found, skipping container teardown." >&2
fi

popd >/dev/null

rm -rf "$PROJECT_DIR"

echo "Callico installation in '$PROJECT_DIR' removed."
