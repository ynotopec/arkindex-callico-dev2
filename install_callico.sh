#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://gitlab.teklia.com/callico/callico.git"
PROJECT_DIR="${1:-callico}"

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Error: required command '$1' not found in PATH." >&2
        exit 1
    fi
}

require_command git
require_command docker

if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD=(docker-compose)
else
    echo "Error: docker compose plugin or docker-compose binary is required." >&2
    exit 1
fi

if [ ! -d "$PROJECT_DIR/.git" ]; then
    echo "Cloning Callico repository into '$PROJECT_DIR'."
    git clone "$REPO_URL" "$PROJECT_DIR"
else
    echo "Callico repository already present in '$PROJECT_DIR'. Updating it."
    git -C "$PROJECT_DIR" fetch --all --prune
    git -C "$PROJECT_DIR" pull --ff-only
fi

pushd "$PROJECT_DIR" >/dev/null

COMPOSE_FILE=()
if [ -f docker-compose.yml ]; then
    COMPOSE_FILE=("-f" "docker-compose.yml")
elif [ -f compose.yml ]; then
    COMPOSE_FILE=("-f" "compose.yml")
fi

"${COMPOSE_CMD[@]}" "${COMPOSE_FILE[@]}" pull
"${COMPOSE_CMD[@]}" "${COMPOSE_FILE[@]}" up -d
"${COMPOSE_CMD[@]}" "${COMPOSE_FILE[@]}" run --rm callico django-admin migrate

SUPERUSER="${DJANGO_SUPERUSER_USERNAME:-admin}"
EMAIL="${DJANGO_SUPERUSER_EMAIL:-admin@example.com}"
PASSWORD="${DJANGO_SUPERUSER_PASSWORD:-}"

if [ -z "$PASSWORD" ]; then
    read -rsp "Password for Django superuser '$SUPERUSER': " PASSWORD
    echo
fi

export DJANGO_SUPERUSER_USERNAME="$SUPERUSER"
export DJANGO_SUPERUSER_EMAIL="$EMAIL"
export DJANGO_SUPERUSER_PASSWORD="$PASSWORD"

"${COMPOSE_CMD[@]}" "${COMPOSE_FILE[@]}" run --rm \
    -e DJANGO_SUPERUSER_USERNAME \
    -e DJANGO_SUPERUSER_EMAIL \
    -e DJANGO_SUPERUSER_PASSWORD \
    callico python - <<'PY'
import os
import django
from django.contrib.auth import get_user_model

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "callico.settings")
django.setup()
User = get_user_model()
username_field = getattr(User, "USERNAME_FIELD", "username")
identifier_env = f"DJANGO_SUPERUSER_{username_field.upper()}"
identifier = os.environ.get(identifier_env)

if not identifier:
    if username_field == "username":
        identifier = os.environ["DJANGO_SUPERUSER_USERNAME"]
    elif username_field == "email":
        identifier = os.environ["DJANGO_SUPERUSER_EMAIL"]
    else:
        raise RuntimeError(
            "Cannot determine superuser identifier. Set the environment variable "
            f"{identifier_env}."
        )

email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "")
password = os.environ["DJANGO_SUPERUSER_PASSWORD"]

lookup = {username_field: identifier}

if User.objects.filter(**lookup).exists():
    print(
        f"Superuser with {username_field!r} '{identifier}' already exists, skipping creation."
    )
else:
    create_kwargs = {**lookup, "password": password}
    if username_field != "email" and email:
        create_kwargs["email"] = email
    User.objects.create_superuser(**create_kwargs)
    print(f"Superuser with {username_field!r} '{identifier}' created.")
PY

popd >/dev/null

echo "Callico environment ready in '$PROJECT_DIR'."
