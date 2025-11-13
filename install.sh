#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
    cat <<'USAGE'
Usage: ./install.sh --domain <domain> --email <email> [options]

Required arguments:
  -d, --domain            Public domain name that should serve Callico.
  -e, --email             Email used for Let's Encrypt notifications.

Optional arguments:
      --compose-file FILE Path to docker-compose file (default: callico/docker-compose.yml).
      --service NAME      Django service name in the compose file (default: callico).
      --app-port PORT     Container port exposed by the Django service (default: 8000).
      --admin-user USER   Username for the Django superuser (default: admin).
      --admin-email MAIL  Email for the Django superuser (default: admin@<domain>).
      --admin-password PW Password for the Django superuser (default: auto-generated).
      --no-recreate       Skip recreating running containers when running docker compose up.
  -h, --help              Show this help and exit.
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

escape_sed() {
    printf '%s' "$1" | sed -e 's/[\/&]/\\&/g'
}

# Defaults
COMPOSE_FILE="callico/docker-compose.yml"
SERVICE_NAME="callico"
APP_PORT="8000"
ADMIN_USER="admin"
ADMIN_EMAIL=""
ADMIN_PASSWORD=""
NO_RECREATE=false
GENERATED_PASSWORD=false

# Parse arguments
POSITIONAL=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        -d|--domain)
            DOMAIN="$2"
            shift 2
            ;;
        -e|--email)
            LETSENCRYPT_EMAIL="$2"
            shift 2
            ;;
        --compose-file)
            COMPOSE_FILE="$2"
            shift 2
            ;;
        --service)
            SERVICE_NAME="$2"
            shift 2
            ;;
        --app-port)
            APP_PORT="$2"
            shift 2
            ;;
        --admin-user)
            ADMIN_USER="$2"
            shift 2
            ;;
        --admin-email)
            ADMIN_EMAIL="$2"
            shift 2
            ;;
        --admin-password)
            ADMIN_PASSWORD="$2"
            shift 2
            ;;
        --no-recreate)
            NO_RECREATE=true
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

if [[ -z "${DOMAIN:-}" || -z "${LETSENCRYPT_EMAIL:-}" ]]; then
    echo "Error: --domain and --email are required." >&2
    usage >&2
    exit 1
fi

if [[ -z "${ADMIN_EMAIL}" ]]; then
    ADMIN_EMAIL="admin@${DOMAIN}"
fi

if [[ -z "${ADMIN_PASSWORD}" ]]; then
    if command_exists openssl; then
        ADMIN_PASSWORD="$(openssl rand -base64 24 | tr -d '\n' | cut -c1-32)"
    else
        echo "Warning: openssl not available, using fallback password generator." >&2
        ADMIN_PASSWORD="$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 24)"
    fi
    GENERATED_PASSWORD=true
fi

require_command docker
if ! docker compose version >/dev/null 2>&1; then
    echo "Error: docker compose v2 is required." >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_PATH="${COMPOSE_FILE}"
if [[ ! -f "${COMPOSE_PATH}" ]]; then
    # Try relative to script directory
    COMPOSE_PATH="${SCRIPT_DIR}/${COMPOSE_FILE}"
fi
if [[ ! -f "${COMPOSE_PATH}" ]]; then
    echo "Error: docker compose file '${COMPOSE_FILE}' not found." >&2
    exit 1
fi

PROJECT_DIR="$(dirname "${COMPOSE_PATH}")"
if [[ ! -d "${PROJECT_DIR}" ]]; then
    echo "Error: project directory '${PROJECT_DIR}' does not exist." >&2
    exit 1
fi

COMPOSE_CMD=(docker compose -f "${COMPOSE_PATH}" --project-directory "${PROJECT_DIR}")

echo "\n==> Starting Callico application containers"
UP_FLAGS=(up -d)
if [[ "${NO_RECREATE}" == true ]]; then
    UP_FLAGS+=(--no-recreate)
fi
"${COMPOSE_CMD[@]}" "${UP_FLAGS[@]}"

echo "\n==> Applying database migrations"
"${COMPOSE_CMD[@]}" run --rm "${SERVICE_NAME}" django-admin migrate

echo "\n==> Ensuring Django superuser '${ADMIN_USER}' exists"
"${COMPOSE_CMD[@]}" run --rm \
    -e DJANGO_SUPERUSER_USERNAME="${ADMIN_USER}" \
    -e DJANGO_SUPERUSER_EMAIL="${ADMIN_EMAIL}" \
    -e DJANGO_SUPERUSER_PASSWORD="${ADMIN_PASSWORD}" \
    "${SERVICE_NAME}" python - <<'PY'
import os
import sys

def get_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None:
        raise SystemExit(f"Missing expected environment variable: {name}")
    return value

identifier_value = get_env("DJANGO_SUPERUSER_USERNAME")
email = get_env("DJANGO_SUPERUSER_EMAIL")
password = get_env("DJANGO_SUPERUSER_PASSWORD")

try:
    import django
    django.setup()
    from django.contrib.auth import get_user_model
    from django.core.exceptions import FieldDoesNotExist
except Exception as exc:  # pylint: disable=broad-except
    sys.stderr.write(f"Failed to initialise Django: {exc}\n")
    sys.exit(1)

User = get_user_model()
username_field = getattr(User, "USERNAME_FIELD", "username")

def model_has_field(model, field_name: str) -> bool:
    try:
        model._meta.get_field(field_name)
        return True
    except FieldDoesNotExist:
        return False

if username_field == "email":
    identifier_value = email

lookup = {username_field: identifier_value}
defaults = {}

if model_has_field(User, "email") and username_field != "email":
    defaults.setdefault("email", email)

if model_has_field(User, "display_name") and "display_name" != username_field:
    defaults.setdefault("display_name", identifier_value)

manager = User._default_manager  # type: ignore[attr-defined]

identifier_field_updated = False

try:
    user = manager.get(**lookup)
    created = False
except User.DoesNotExist:
    user = None
    if model_has_field(User, "email"):
        try:
            user = manager.get(email=email)
            created = False
            if getattr(user, username_field, None) != identifier_value:
                setattr(user, username_field, identifier_value)
                identifier_field_updated = True
        except User.DoesNotExist:
            user = None

    if user is None:
        user, created = manager.get_or_create(defaults=defaults, **lookup)

updated_fields = set()

if identifier_field_updated:
    updated_fields.add(username_field)

if not created and model_has_field(User, "email") and getattr(user, "email", None) != email:
    setattr(user, "email", email)
    updated_fields.add("email")

if model_has_field(User, "display_name") and getattr(user, "display_name", None) != identifier_value:
    setattr(user, "display_name", identifier_value)
    updated_fields.add("display_name")


super_flag_field = None
if model_has_field(User, "is_superuser"):
    super_flag_field = "is_superuser"
elif model_has_field(User, "is_admin"):
    super_flag_field = "is_admin"

if super_flag_field and not getattr(user, super_flag_field, False):
    setattr(user, super_flag_field, True)
    updated_fields.add(super_flag_field)

if not getattr(user, "is_staff", False):
    user.is_staff = True
    updated_fields.add("is_staff")

if hasattr(user, "is_active") and not getattr(user, "is_active"):
    user.is_active = True
    updated_fields.add("is_active")

if created:
    user.set_password(password)
    user.save()
    print(f"Superuser '{identifier_value}' created using field '{username_field}'.")
else:
    if updated_fields:
        user.save(update_fields=list(updated_fields))
    print(f"Superuser '{identifier_value}' already exists (field '{username_field}'), password unchanged.")
PY

echo "\n==> Determining published port for service '${SERVICE_NAME}'"
HOST_BINDING=$("${COMPOSE_CMD[@]}" port "${SERVICE_NAME}" "${APP_PORT}" | tail -n1 || true)
if [[ -z "${HOST_BINDING}" ]]; then
    echo "Error: could not determine published port for ${SERVICE_NAME}:${APP_PORT}." >&2
    exit 1
fi
HOST_IP="${HOST_BINDING%:*}"
HOST_PORT="${HOST_BINDING##*:}"
if [[ -z "${HOST_IP}" || "${HOST_IP}" == "0.0.0.0" || "${HOST_IP}" == "::" ]]; then
    UPSTREAM_HOST="127.0.0.1"
else
    UPSTREAM_HOST="${HOST_IP}"
fi
UPSTREAM_PORT="${HOST_PORT}"

PROXY_DIR="${SCRIPT_DIR}/deployment/proxy"
PROXY_COMPOSE_FILE="${PROXY_DIR}/docker-compose.proxy.yml"
PROXY_TEMPLATE="${PROXY_DIR}/Caddyfile.template"
PROXY_CADDYFILE="${PROXY_DIR}/Caddyfile"

if [[ ! -f "${PROXY_COMPOSE_FILE}" ]]; then
    echo "Error: proxy compose file '${PROXY_COMPOSE_FILE}' not found." >&2
    exit 1
fi
if [[ ! -f "${PROXY_TEMPLATE}" ]]; then
    echo "Error: Caddyfile template '${PROXY_TEMPLATE}' not found." >&2
    exit 1
fi

mkdir -p "${PROXY_DIR}/data" "${PROXY_DIR}/config"
sed \
    -e "s/__ACME_EMAIL__/$(escape_sed "${LETSENCRYPT_EMAIL}")/g" \
    -e "s/__DOMAIN__/$(escape_sed "${DOMAIN}")/g" \
    -e "s/__UPSTREAM_HOST__/$(escape_sed "${UPSTREAM_HOST}")/g" \
    -e "s/__UPSTREAM_PORT__/$(escape_sed "${UPSTREAM_PORT}")/g" \
    "${PROXY_TEMPLATE}" > "${PROXY_CADDYFILE}"

PROXY_COMPOSE_CMD=(docker compose -f "${PROXY_COMPOSE_FILE}" --project-directory "${PROXY_DIR}")

echo "\n==> Starting Caddy reverse proxy with automatic TLS"
"${PROXY_COMPOSE_CMD[@]}" up -d

cat <<INFO

Callico is now available at: https://${DOMAIN}
Let's Encrypt certificates will be stored under ${PROXY_DIR}/data.
INFO

if [[ "${GENERATED_PASSWORD:-false}" == true ]]; then
    cat <<PASS
Generated Django superuser credentials:
  Username: ${ADMIN_USER}
  Email:    ${ADMIN_EMAIL}
  Password: ${ADMIN_PASSWORD}
PASS
fi

