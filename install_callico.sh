#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
DEPLOY_DIR="$REPO_ROOT/callico/deployment"
COMPOSE_FILE="$DEPLOY_DIR/docker-compose.yml"
ENV_FILE="$DEPLOY_DIR/.callico-domains.env"
LETSENCRYPT_PRODUCTION_CA="https://acme-v02.api.letsencrypt.org/directory"
LETSENCRYPT_STAGING_CA="https://acme-staging-v02.api.letsencrypt.org/directory"

DEFAULT_CALICO_DOMAIN="callico.company.com"
DEFAULT_MINIO_DOMAIN="minio-callico.company.com"
DEFAULT_MINIO_CONSOLE_DOMAIN="minio-console-callico.company.com"
DEFAULT_BASE_DOMAIN="company.com"
DEFAULT_DB_USER="callico"
DEFAULT_SHARED_PASSWORD="changeme"
DEFAULT_MINIO_ROOT_USER="callico-app"
DEFAULT_STORAGE_ACCESS_KEY="callico-app"
DEFAULT_ADMIN_USERNAME="admin"

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

normalize_boolean() {
  local value="${1:-}"
  local lowered="${value,,}"
  case "$lowered" in
    y|yes|true|1)
      printf 'true'
      ;;
    n|no|false|0|'')
      printf 'false'
      ;;
    *)
      return 1
      ;;
  esac
}

if ! find_compose_command; then
  echo "Error: neither 'docker compose' nor 'docker-compose' is available." >&2
  exit 1
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Error: docker compose file '$COMPOSE_FILE' not found." >&2
  exit 1
fi

load_env_value() {
  local key="$1"
  [[ -f "$ENV_FILE" ]] || return 1
  local line
  line="$(grep -E "^${key}=" "$ENV_FILE" | tail -n1 || true)"
  [[ -n "$line" ]] || return 1
  printf '%s' "${line#*=}"
}

prompt_for_value() {
  local prompt="$1"
  local default_value="$2"
  local input=""
  if [[ -t 0 ]]; then
    read -r -p "$prompt" input || true
  fi
  input="${input:-$default_value}"
  if command -v xargs >/dev/null 2>&1; then
    input="$(printf '%s' "$input" | xargs)"
  fi
  printf '%s' "$input"
}

write_env_file() {
  cat >"$ENV_FILE" <<EOF
BASE_DOMAIN=$1
CALICO_DOMAIN=$2
MINIO_DOMAIN=$3
MINIO_CONSOLE_DOMAIN=$4
LETSENCRYPT_EMAIL=$5
LETSENCRYPT_USE_STAGING=$6
CALICO_DB_USER=$7
CALICO_DB_PASSWORD=$8
MINIO_ROOT_USER=$9
MINIO_ROOT_PASSWORD=${10}
CALICO_STORAGE_ACCESS_KEY=${11}
CALICO_STORAGE_SECRET_KEY=${12}
CALICO_ADMIN_USERNAME=${13}
CALICO_ADMIN_EMAIL=${14}
CALICO_ADMIN_PASSWORD=${15}
EOF
}

load_domain_configuration() {
  local base_domain_input="${BASE_DOMAIN:-}" calico_domain_input="${CALICO_DOMAIN:-}" minio_domain_input="${MINIO_DOMAIN:-}" minio_console_domain_input="${MINIO_CONSOLE_DOMAIN:-}"
  local letsencrypt_email_input="${LETSENCRYPT_EMAIL:-}" letsencrypt_staging_input="${LETSENCRYPT_USE_STAGING:-}"
  local db_user_input="${CALICO_DB_USER:-}"
  local minio_root_user_input="${MINIO_ROOT_USER:-}"
  local storage_access_key_input="${CALICO_STORAGE_ACCESS_KEY:-}"
  local shared_password_input="${CALICO_INSTALL_PASSWORD:-}"
  local admin_username_input="${CALICO_ADMIN_USERNAME:-}"
  local admin_email_input="${CALICO_ADMIN_EMAIL:-}"
  local admin_password_input="${CALICO_ADMIN_PASSWORD:-}"
  local reconfigure=0

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --base-domain)
        if [[ $# -lt 2 ]]; then
          echo "Error: --base-domain requires a value." >&2
          exit 1
        fi
        shift
        base_domain_input="$1"
        ;;
      --callico-domain)
        if [[ $# -lt 2 ]]; then
          echo "Error: --callico-domain requires a value." >&2
          exit 1
        fi
        shift
        calico_domain_input="$1"
        ;;
      --minio-domain)
        if [[ $# -lt 2 ]]; then
          echo "Error: --minio-domain requires a value." >&2
          exit 1
        fi
        shift
        minio_domain_input="$1"
        ;;
      --minio-console-domain)
        if [[ $# -lt 2 ]]; then
          echo "Error: --minio-console-domain requires a value." >&2
          exit 1
        fi
        shift
        minio_console_domain_input="$1"
        ;;
      --letsencrypt-email)
        if [[ $# -lt 2 ]]; then
          echo "Error: --letsencrypt-email requires a value." >&2
          exit 1
        fi
        shift
        letsencrypt_email_input="$1"
        ;;
      --letsencrypt-staging)
        letsencrypt_staging_input="true"
        ;;
      --letsencrypt-production)
        letsencrypt_staging_input="false"
        ;;
      --db-user)
        if [[ $# -lt 2 ]]; then
          echo "Error: --db-user requires a value." >&2
          exit 1
        fi
        shift
        db_user_input="$1"
        ;;
      --minio-root-user)
        if [[ $# -lt 2 ]]; then
          echo "Error: --minio-root-user requires a value." >&2
          exit 1
        fi
        shift
        minio_root_user_input="$1"
        ;;
      --storage-access-key)
        if [[ $# -lt 2 ]]; then
          echo "Error: --storage-access-key requires a value." >&2
          exit 1
        fi
        shift
        storage_access_key_input="$1"
        ;;
      --admin-username)
        if [[ $# -lt 2 ]]; then
          echo "Error: --admin-username requires a value." >&2
          exit 1
        fi
        shift
        admin_username_input="$1"
        ;;
      --admin-email)
        if [[ $# -lt 2 ]]; then
          echo "Error: --admin-email requires a value." >&2
          exit 1
        fi
        shift
        admin_email_input="$1"
        ;;
      --admin-password)
        if [[ $# -lt 2 ]]; then
          echo "Error: --admin-password requires a value." >&2
          exit 1
        fi
        shift
        admin_password_input="$1"
        ;;
      --password)
        if [[ $# -lt 2 ]]; then
          echo "Error: --password requires a value." >&2
          exit 1
        fi
        shift
        shared_password_input="$1"
        ;;
      --reconfigure)
        reconfigure=1
        ;;
      -h|--help)
        cat <<USAGE
Usage: $(basename "$0") [options]

Options:
  --base-domain DOMAIN            Set the root domain (default: company.com)
  --callico-domain DOMAIN         Set the public domain for the Callico web application (default: callico.<root-domain>)
  --minio-domain DOMAIN           Set the public domain for MinIO S3 endpoint (default: minio-callico.<root-domain>)
  --minio-console-domain DOMAIN   Set the public domain for the MinIO Console (default: minio-console-callico.<root-domain>)
  --letsencrypt-email EMAIL       Email used for Let's Encrypt certificate notifications (default: admin@<callico-domain>)
  --letsencrypt-staging           Use Let's Encrypt staging environment for certificate requests
  --letsencrypt-production        Use Let's Encrypt production environment for certificate requests (default)
  --db-user USER                  Database login for the Callico Postgres instance (default: callico)
  --minio-root-user USER          MinIO root user (default: callico-app)
  --storage-access-key KEY        Access key ID used by Callico to reach MinIO (default: callico-app)
  --admin-username USER           Username for the initial Callico administrator (default: admin)
  --admin-email EMAIL             Email for the initial Callico administrator (default: admin@<callico-domain>)
  --admin-password PASSWORD       Password for the initial Callico administrator (default: shared password)
  --password PASSWORD             Shared password applied to the database, MinIO root, storage secret, and admin (unless overridden)
  --reconfigure                   Prompt again for domain values even if a saved configuration exists
  -h, --help                      Show this help message
USAGE
        exit 0
        ;;
      *)
        echo "Error: unknown option '$1'" >&2
        exit 1
        ;;
    esac
    shift
  done

  if [[ -n "$base_domain_input" || -n "$calico_domain_input" || -n "$minio_domain_input" || -n "$minio_console_domain_input" || -n "$letsencrypt_email_input" || -n "$letsencrypt_staging_input" || -n "$db_user_input" || -n "$minio_root_user_input" || -n "$storage_access_key_input" || -n "$shared_password_input" || -n "$admin_username_input" || -n "$admin_email_input" || -n "$admin_password_input" ]]; then
    reconfigure=1
  fi

  local current_calico current_minio current_minio_console current_le_email current_le_staging
  current_calico="$(load_env_value CALICO_DOMAIN || true)"
  current_minio="$(load_env_value MINIO_DOMAIN || true)"
  current_minio_console="$(load_env_value MINIO_CONSOLE_DOMAIN || true)"
  current_le_email="$(load_env_value LETSENCRYPT_EMAIL || true)"
  current_le_staging="$(load_env_value LETSENCRYPT_USE_STAGING || true)"
  current_base="$(load_env_value BASE_DOMAIN || true)"
  local current_db_user current_db_password current_minio_root_user current_minio_root_password current_storage_access_key current_storage_secret_key
  local current_admin_username current_admin_email current_admin_password
  current_db_user="$(load_env_value CALICO_DB_USER || true)"
  current_db_password="$(load_env_value CALICO_DB_PASSWORD || true)"
  current_minio_root_user="$(load_env_value MINIO_ROOT_USER || true)"
  current_minio_root_password="$(load_env_value MINIO_ROOT_PASSWORD || true)"
  current_storage_access_key="$(load_env_value CALICO_STORAGE_ACCESS_KEY || true)"
  current_storage_secret_key="$(load_env_value CALICO_STORAGE_SECRET_KEY || true)"
  current_admin_username="$(load_env_value CALICO_ADMIN_USERNAME || true)"
  current_admin_email="$(load_env_value CALICO_ADMIN_EMAIL || true)"
  current_admin_password="$(load_env_value CALICO_ADMIN_PASSWORD || true)"

  local secrets_available=1
  if [[ -z "${current_db_password:-}" || -z "${current_minio_root_password:-}" || -z "${current_storage_secret_key:-}" || -z "${current_admin_password:-}" ]]; then
    secrets_available=0
  fi

  local db_login_available=1
  if [[ -z "${current_db_user:-}" ]]; then
    db_login_available=0
  fi

  if [[ -f "$ENV_FILE" && $reconfigure -eq 0 && -z "$calico_domain_input" && -z "$minio_domain_input" && -z "$minio_console_domain_input" && -z "$letsencrypt_email_input" && -z "$letsencrypt_staging_input" && -z "$db_user_input" && -z "$minio_root_user_input" && -z "$storage_access_key_input" && -z "$shared_password_input" && -z "$admin_username_input" && -z "$admin_email_input" && -z "$admin_password_input" && $secrets_available -eq 1 && $db_login_available -eq 1 ]]; then
    echo "Using existing domain configuration from '$ENV_FILE'."
    export CALICO_DOMAIN="${current_calico:-$DEFAULT_CALICO_DOMAIN}"
    export MINIO_DOMAIN="${current_minio:-$DEFAULT_MINIO_DOMAIN}"
    export MINIO_CONSOLE_DOMAIN="${current_minio_console:-$DEFAULT_MINIO_CONSOLE_DOMAIN}"
    local fallback_email="admin@${CALICO_DOMAIN}"
    export LETSENCRYPT_EMAIL="${current_le_email:-$fallback_email}"
    export LETSENCRYPT_USE_STAGING="${current_le_staging:-false}"
    if [[ -n "${current_base:-}" ]]; then
      export BASE_DOMAIN="$current_base"
    elif [[ "$CALICO_DOMAIN" == callico.* ]]; then
      export BASE_DOMAIN="${CALICO_DOMAIN#callico.}"
    fi
    export CALICO_DB_USER="${current_db_user:-$DEFAULT_DB_USER}"
    export CALICO_DB_PASSWORD="${current_db_password:-$DEFAULT_SHARED_PASSWORD}"
    export MINIO_ROOT_USER="${current_minio_root_user:-$DEFAULT_MINIO_ROOT_USER}"
    export MINIO_ROOT_PASSWORD="${current_minio_root_password:-$DEFAULT_SHARED_PASSWORD}"
    export CALICO_STORAGE_ACCESS_KEY="${current_storage_access_key:-$DEFAULT_STORAGE_ACCESS_KEY}"
    export CALICO_STORAGE_SECRET_KEY="${current_storage_secret_key:-$DEFAULT_SHARED_PASSWORD}"
    export CALICO_ADMIN_USERNAME="${current_admin_username:-$DEFAULT_ADMIN_USERNAME}"
    local default_admin_email="admin@${CALICO_DOMAIN}"
    export CALICO_ADMIN_EMAIL="${current_admin_email:-$default_admin_email}"
    export CALICO_ADMIN_PASSWORD="${current_admin_password:-$DEFAULT_SHARED_PASSWORD}"
    return
  fi

  if [[ -f "$ENV_FILE" ]]; then
    if [[ $secrets_available -eq 0 ]]; then
      echo "Existing configuration is missing Callico service or administrator passwords. Re-entering setup prompts." >&2
    fi
    if [[ $db_login_available -eq 0 ]]; then
      echo "Existing configuration is missing the Callico database login. Re-entering setup prompts." >&2
    fi
  fi

  local base_domain calico_domain minio_domain minio_console_domain letsencrypt_email letsencrypt_use_staging
  local calico_db_user minio_root_user storage_access_key storage_secret_key shared_password
  local admin_username admin_email admin_password
  if [[ -n "$base_domain_input" ]]; then
    base_domain="$base_domain_input"
  elif [[ -n "${current_base:-}" ]]; then
    base_domain="$current_base"
  elif [[ -n "$calico_domain_input" && "$calico_domain_input" == callico.* ]]; then
    base_domain="${calico_domain_input#callico.}"
  elif [[ -n "${current_calico:-}" && "${current_calico}" == callico.* ]]; then
    base_domain="${current_calico#callico.}"
  else
    base_domain="$DEFAULT_BASE_DOMAIN"
  fi

  calico_domain="${calico_domain_input:-${current_calico:-callico.${base_domain}}}"
  minio_domain="${minio_domain_input:-${current_minio:-minio-callico.${base_domain}}}"
  minio_console_domain="${minio_console_domain_input:-${current_minio_console:-minio-console-callico.${base_domain}}}"
  letsencrypt_email="${letsencrypt_email_input:-${current_le_email:-admin@${calico_domain}}}"
  calico_db_user="${db_user_input:-${current_db_user:-$DEFAULT_DB_USER}}"
  minio_root_user="${minio_root_user_input:-${current_minio_root_user:-$DEFAULT_MINIO_ROOT_USER}}"
  storage_access_key="${storage_access_key_input:-${current_storage_access_key:-$DEFAULT_STORAGE_ACCESS_KEY}}"

  if [[ -n "$shared_password_input" ]]; then
    shared_password="$shared_password_input"
  elif [[ -n "${current_db_password:-}" ]]; then
    shared_password="$current_db_password"
  elif [[ -n "${current_minio_root_password:-}" ]]; then
    shared_password="$current_minio_root_password"
  elif [[ -n "${current_storage_secret_key:-}" ]]; then
    shared_password="$current_storage_secret_key"
  else
    shared_password="$DEFAULT_SHARED_PASSWORD"
  fi

  if [[ -n "$letsencrypt_staging_input" ]]; then
    if ! letsencrypt_use_staging="$(normalize_boolean "$letsencrypt_staging_input")"; then
      echo "Error: invalid value for Let's Encrypt environment: '$letsencrypt_staging_input'. Use true/false." >&2
      exit 1
    fi
  else
    letsencrypt_use_staging="${current_le_staging:-false}"
  fi

  if [[ -z "$base_domain_input" ]]; then
    base_domain="$(prompt_for_value "Root domain [$base_domain]: " "$base_domain")"
  fi

  if [[ -z "$calico_domain_input" ]]; then
    calico_domain="callico.${base_domain}"
    calico_domain="$(prompt_for_value "Callico domain [$calico_domain]: " "$calico_domain")"
  fi

  if [[ -z "$minio_domain_input" && ( -z "$current_minio" || $reconfigure -eq 1 ) ]]; then
    minio_domain="minio-callico.${base_domain}"
  fi
  if [[ -z "$minio_domain_input" ]]; then
    minio_domain="$(prompt_for_value "MinIO domain [$minio_domain]: " "$minio_domain")"
  fi

  if [[ -z "$minio_console_domain_input" && ( -z "$current_minio_console" || $reconfigure -eq 1 ) ]]; then
    minio_console_domain="minio-console-callico.${base_domain}"
  fi
  if [[ -z "$minio_console_domain_input" ]]; then
    minio_console_domain="$(prompt_for_value "MinIO console domain [$minio_console_domain]: " "$minio_console_domain")"
  fi

  if [[ -z "$letsencrypt_email_input" ]]; then
    letsencrypt_email="$(prompt_for_value "Let's Encrypt email [$letsencrypt_email]: " "$letsencrypt_email")"
  fi

  if [[ -z "$db_user_input" ]]; then
    calico_db_user="$(prompt_for_value "Database login [$calico_db_user]: " "$calico_db_user")"
  fi

  if [[ -z "$shared_password_input" ]]; then
    shared_password="$(prompt_for_value "Password for Callico services [$shared_password]: " "$shared_password")"
  fi

  local calico_db_password="$shared_password"
  local minio_root_password="$shared_password"
  local storage_secret_key="$shared_password"

  if [[ -n "$admin_username_input" ]]; then
    admin_username="$admin_username_input"
  elif [[ -n "${current_admin_username:-}" ]]; then
    admin_username="$current_admin_username"
  else
    admin_username="$DEFAULT_ADMIN_USERNAME"
  fi

  local default_admin_email="admin@${calico_domain}"
  if [[ -n "$admin_email_input" ]]; then
    admin_email="$admin_email_input"
  elif [[ -n "${current_admin_email:-}" ]]; then
    admin_email="$current_admin_email"
  else
    admin_email="$default_admin_email"
  fi

  if [[ -n "$admin_password_input" ]]; then
    admin_password="$admin_password_input"
  elif [[ -n "${current_admin_password:-}" ]]; then
    admin_password="$current_admin_password"
  else
    admin_password="$shared_password"
  fi

  if [[ -z "$admin_username_input" ]]; then
    admin_username="$(prompt_for_value "Admin username [$admin_username]: " "$admin_username")"
  fi

  if [[ -z "$admin_email_input" ]]; then
    admin_email="$(prompt_for_value "Admin email [$admin_email]: " "$admin_email")"
  fi

  if [[ -z "$admin_password_input" ]]; then
    admin_password="$(prompt_for_value "Admin password [$admin_password]: " "$admin_password")"
  fi

  if [[ -z "$letsencrypt_staging_input" ]]; then
    if ! letsencrypt_use_staging="$(normalize_boolean "$letsencrypt_use_staging")"; then
      echo "Error: invalid stored value for Let's Encrypt staging selection: '$letsencrypt_use_staging'." >&2
      exit 1
    fi
  fi

  if [[ -z "$base_domain" ]]; then
    echo "Error: root domain cannot be empty." >&2
    exit 1
  fi

  for value in "$base_domain" "$calico_domain" "$minio_domain" "$minio_console_domain" "$calico_db_user" "$minio_root_user" "$storage_access_key" "$admin_username"; do
    if [[ -z "$value" ]]; then
      echo "Error: configuration values cannot be empty." >&2
      exit 1
    fi
    if [[ "$value" =~ [[:space:]] ]]; then
      echo "Error: configuration values cannot contain whitespace: '$value'" >&2
      exit 1
    fi
  done

  for value in "$calico_db_password" "$minio_root_password" "$storage_secret_key" "$admin_password"; do
    if [[ -z "$value" ]]; then
      echo "Error: secret values cannot be empty." >&2
      exit 1
    fi
    if [[ "$value" =~ [[:space:]] ]]; then
      echo "Error: secret values cannot contain whitespace: '$value'" >&2
      exit 1
    fi
  done

  if [[ -z "$letsencrypt_email" ]]; then
    echo "Error: Let's Encrypt email cannot be empty." >&2
    exit 1
  fi
  if [[ "$letsencrypt_email" != *"@"* ]]; then
    echo "Error: Let's Encrypt email must contain '@': '$letsencrypt_email'" >&2
    exit 1
  fi

  if [[ -z "$admin_email" || "$admin_email" != *"@"* ]]; then
    echo "Error: admin email must contain '@': '$admin_email'" >&2
    exit 1
  fi

  write_env_file "$base_domain" "$calico_domain" "$minio_domain" "$minio_console_domain" "$letsencrypt_email" "$letsencrypt_use_staging" "$calico_db_user" "$calico_db_password" "$minio_root_user" "$minio_root_password" "$storage_access_key" "$storage_secret_key" "$admin_username" "$admin_email" "$admin_password"

  export BASE_DOMAIN="$base_domain"
  export CALICO_DOMAIN="$calico_domain"
  export MINIO_DOMAIN="$minio_domain"
  export MINIO_CONSOLE_DOMAIN="$minio_console_domain"
  export LETSENCRYPT_EMAIL="$letsencrypt_email"
  export LETSENCRYPT_USE_STAGING="$letsencrypt_use_staging"
  export CALICO_DB_USER="$calico_db_user"
  export CALICO_DB_PASSWORD="$calico_db_password"
  export MINIO_ROOT_USER="$minio_root_user"
  export MINIO_ROOT_PASSWORD="$minio_root_password"
  export CALICO_STORAGE_ACCESS_KEY="$storage_access_key"
  export CALICO_STORAGE_SECRET_KEY="$storage_secret_key"
  export CALICO_ADMIN_USERNAME="$admin_username"
  export CALICO_ADMIN_EMAIL="$admin_email"
  export CALICO_ADMIN_PASSWORD="$admin_password"

  echo "Saved domain configuration to '$ENV_FILE'."
}

load_env_variables() {
  if [[ -f "$ENV_FILE" ]]; then
    while IFS='=' read -r key value; do
      [[ -z "$key" || "$key" =~ ^# ]] && continue
      export "$key"="$value"
    done <"$ENV_FILE"
  fi
}

load_domain_configuration "$@"
load_env_variables

ensure_letsencrypt_runtime() {
  if [[ -z "${LETSENCRYPT_EMAIL:-}" ]]; then
    echo "Error: Let's Encrypt email is not configured. Re-run with --letsencrypt-email or --reconfigure." >&2
    exit 1
  fi

  if [[ "$LETSENCRYPT_EMAIL" != *"@"* ]]; then
    echo "Error: Let's Encrypt email must contain '@': '$LETSENCRYPT_EMAIL'" >&2
    exit 1
  fi

  local normalized_staging
  if ! normalized_staging="$(normalize_boolean "${LETSENCRYPT_USE_STAGING:-false}")"; then
    echo "Error: invalid value for LETSENCRYPT_USE_STAGING: '${LETSENCRYPT_USE_STAGING:-}'." >&2
    exit 1
  fi
  export LETSENCRYPT_USE_STAGING="$normalized_staging"

  if [[ "$normalized_staging" == "true" ]]; then
    export LETSENCRYPT_CA_SERVER="$LETSENCRYPT_STAGING_CA"
  else
    export LETSENCRYPT_CA_SERVER="$LETSENCRYPT_PRODUCTION_CA"
  fi

  local storage_dir="$DEPLOY_DIR/letsencrypt"
  local acme_file="$storage_dir/acme.json"
  mkdir -p "$storage_dir"
  if [[ ! -f "$acme_file" ]]; then
    touch "$acme_file"
  fi
  chmod 600 "$acme_file"
}

ensure_letsencrypt_runtime

echo "Starting Callico deployment using ${COMPOSE_CMD[*]} with domains: Callico='$CALICO_DOMAIN', MinIO='$MINIO_DOMAIN', Console='$MINIO_CONSOLE_DOMAIN'."
if [[ "$LETSENCRYPT_USE_STAGING" == "true" ]]; then
  echo "Let's Encrypt will use the staging environment with email '$LETSENCRYPT_EMAIL'."
else
  echo "Requesting trusted TLS certificates from Let's Encrypt production with email '$LETSENCRYPT_EMAIL'."
fi

compose_in_deploy() {
  pushd "$DEPLOY_DIR" >/dev/null
  "${COMPOSE_CMD[@]}" "$@"
  local status=$?
  popd >/dev/null
  return $status
}

compose_in_deploy up -d

echo "Callico deployment started."

wait_for_postgres() {
  echo "Waiting for PostgreSQL to become ready..."
  local attempts=0
  local max_attempts=30
  while (( attempts < max_attempts )); do
    if compose_in_deploy exec -T postgres pg_isready -U "$CALICO_DB_USER" -d callico >/dev/null 2>&1; then
      echo "PostgreSQL is ready."
      return 0
    fi
    sleep 2
    attempts=$((attempts + 1))
  done
  echo "Error: PostgreSQL did not become ready in time." >&2
  exit 1
}

run_django_admin() {
  compose_in_deploy run --rm "$@"
}

run_database_migrations() {
  echo "Applying database migrations..."
  run_django_admin callico django-admin migrate
  echo "Database migrations completed."
}

ensure_admin_account() {
  echo "Ensuring administrator account '${CALICO_ADMIN_USERNAME}' exists..."
  compose_in_deploy run --rm \
    -e DJANGO_SETTINGS_MODULE=callico.base.settings \
    -e CALICO_ADMIN_USERNAME \
    -e CALICO_ADMIN_EMAIL \
    -e CALICO_ADMIN_PASSWORD \
    callico \
    python - <<'PY'
import os
import django

django.setup()

from django.contrib.auth import get_user_model

username = os.environ["CALICO_ADMIN_USERNAME"]
email = os.environ["CALICO_ADMIN_EMAIL"]
password = os.environ["CALICO_ADMIN_PASSWORD"]

User = get_user_model()
user, created = User.objects.get_or_create(
    username=username,
    defaults={"email": email, "is_superuser": True, "is_staff": True},
)

if not created:
    updated = False
    if user.email != email:
        user.email = email
        updated = True
    if not user.is_superuser:
        user.is_superuser = True
        updated = True
    if not user.is_staff:
        user.is_staff = True
        updated = True
    if updated:
        user.save(update_fields=["email", "is_superuser", "is_staff"])

user.set_password(password)
user.save()

message = "Created" if created else "Updated"
print(f"{message} administrator '{username}' with email '{email}'.")
PY
  echo "Administrator account ensured."
}

wait_for_postgres
run_database_migrations
ensure_admin_account

echo "Callico installation finished. You can now log in as '${CALICO_ADMIN_USERNAME}'."
