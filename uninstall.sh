#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
    cat <<'USAGE'
Usage: ./uninstall.sh [options]

Optional arguments:
      --compose-file FILE   Path to docker-compose file (default: callico/docker-compose.yml).
      --proxy-compose FILE  Path to the proxy docker-compose file (default: deployment/proxy/docker-compose.proxy.yml).
      --keep-certificates   Do not delete Let's Encrypt data (default: delete).
  -h, --help                Show this help and exit.
USAGE
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

require_command() {
    if ! command_exists "$1"; then
        echo "Error: required command '$1' is not installed or not in PATH." >&2
        exit 1
    fi
}

COMPOSE_FILE="callico/docker-compose.yml"
PROXY_COMPOSE="deployment/proxy/docker-compose.proxy.yml"
KEEP_CERTIFICATES=false

POSITIONAL=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --compose-file)
            COMPOSE_FILE="$2"
            shift 2
            ;;
        --proxy-compose)
            PROXY_COMPOSE="$2"
            shift 2
            ;;
        --keep-certificates)
            KEEP_CERTIFICATES=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        --*)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 1
            ;;
        *)
            POSITIONAL+=("$1")
            shift
            ;;
    esac
done

if [[ ${#POSITIONAL[@]} -gt 0 ]]; then
    echo "Unexpected arguments: ${POSITIONAL[*]}" >&2
    usage >&2
    exit 1
fi

require_command docker
if ! docker compose version >/dev/null 2>&1; then
    echo "Error: docker compose v2 is required." >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
resolve_path() {
    local path="$1"
    if [[ -f "$path" ]]; then
        echo "$path"
    elif [[ -f "${SCRIPT_DIR}/$path" ]]; then
        echo "${SCRIPT_DIR}/$path"
    else
        echo ""
    fi
}

COMPOSE_PATH=$(resolve_path "$COMPOSE_FILE")
PROXY_COMPOSE_PATH=$(resolve_path "$PROXY_COMPOSE")

if [[ -n "${PROXY_COMPOSE_PATH}" ]]; then
    PROXY_DIR="$(dirname "${PROXY_COMPOSE_PATH}")"
    echo "==> Shutting down Caddy reverse proxy"
    docker compose -f "${PROXY_COMPOSE_PATH}" --project-directory "${PROXY_DIR}" down --remove-orphans || true
    if [[ "${KEEP_CERTIFICATES}" == false ]]; then
        echo "==> Removing stored TLS certificates"
        rm -rf "${PROXY_DIR}/data" "${PROXY_DIR}/config"
    else
        echo "==> Preserving certificate data in ${PROXY_DIR}/data"
    fi
    if [[ -f "${PROXY_DIR}/Caddyfile" ]]; then
        rm -f "${PROXY_DIR}/Caddyfile"
    fi
fi

if [[ -n "${COMPOSE_PATH}" ]]; then
    PROJECT_DIR="$(dirname "${COMPOSE_PATH}")"
    echo "==> Shutting down Callico application"
    docker compose -f "${COMPOSE_PATH}" --project-directory "${PROJECT_DIR}" down || true
else
    echo "Warning: docker compose file '${COMPOSE_FILE}' not found, skipping application shutdown." >&2
fi

echo "Uninstallation complete."
