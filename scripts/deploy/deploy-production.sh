#!/usr/bin/env bash
set -Eeuo pipefail

readonly BOMI_SOURCE_DIR="${BOMI_SOURCE_DIR:-/home/ubuntu/bomi/deploy/source}"
readonly BOMI_ENV_FILE="${BOMI_ENV_FILE:-/home/ubuntu/bomi/secrets/production.env}"
readonly BOMI_COMPOSE_FILE="$BOMI_SOURCE_DIR/infra/compose.prod.yml"

compose() {
  docker compose --env-file "$BOMI_ENV_FILE" -f "$BOMI_COMPOSE_FILE" "$@"
}

log() {
  printf '[deploy] %s\n' "$*"
}

fail() {
  printf '[deploy] ERROR: %s\n' "$*" >&2
  exit 1
}

read_env_value() {
  local key="$1"
  awk -F= -v key="$key" '$1 == key { sub(/^[^=]*=/, ""); print; exit }' "$BOMI_ENV_FILE"
}

set_env_value() {
  local key="$1"
  local value="$2"
  local temporary_file

  temporary_file="$(mktemp "${BOMI_ENV_FILE}.tmp.XXXXXX")"
  chmod 600 "$temporary_file"
  awk -F= -v key="$key" -v value="$value" '
    BEGIN { updated = 0 }
    $1 == key { print key "=" value; updated = 1; next }
    { print }
    END { if (!updated) print key "=" value }
  ' "$BOMI_ENV_FILE" > "$temporary_file"
  mv "$temporary_file" "$BOMI_ENV_FILE"
}

on_error() {
  local exit_code=$?
  printf '[deploy] FAILED at line %s (exit code %s)\n' "$1" "$exit_code" >&2
  exit "$exit_code"
}

trap 'on_error "$LINENO"' ERR

command -v git >/dev/null 2>&1 || fail 'git is not installed'
command -v docker >/dev/null 2>&1 || fail 'docker is not installed'
command -v curl >/dev/null 2>&1 || fail 'curl is not installed'
[[ -d "$BOMI_SOURCE_DIR/.git" ]] || fail "Git repository not found: $BOMI_SOURCE_DIR"
[[ -r "$BOMI_ENV_FILE" ]] || fail "Environment file not readable: $BOMI_ENV_FILE"
[[ -r "$BOMI_COMPOSE_FILE" ]] || fail "Compose file not readable: $BOMI_COMPOSE_FILE"

cd "$BOMI_SOURCE_DIR"
[[ -z "$(git status --porcelain)" ]] \
  || fail 'Git working tree is not clean; commit or discard changes before deployment'

readonly GIT_SHA="$(git rev-parse --short=12 HEAD)"
readonly BOMI_DOMAIN="$(read_env_value BOMI_DOMAIN)"
[[ -n "$BOMI_DOMAIN" ]] || fail 'BOMI_DOMAIN is missing from the environment file'

log "Starting deployment for Git commit $GIT_SHA"
log 'Updating Backend and Frontend image tags'
set_env_value BACKEND_IMAGE_TAG "$GIT_SHA"
set_env_value OPERATOR_CONSOLE_IMAGE_TAG "$GIT_SHA"
set_env_value WAYPOINT_EDITOR_IMAGE_TAG "$GIT_SHA"
set_env_value DB_VIEWER_IMAGE_TAG "$GIT_SHA"
set_env_value FRONTEND_IMAGE_TAG "$GIT_SHA"

log 'Validating Docker Compose configuration'
compose config --quiet

log 'Ensuring PostgreSQL is healthy'
compose up -d --wait --wait-timeout 60 postgres

log 'Building Backend, operator tools and Frontend images'
compose build backend operator-console waypoint-editor db-viewer frontend

log 'Starting application containers'
compose up -d --wait --wait-timeout 120 backend operator-console waypoint-editor db-viewer frontend

log 'Recreating public Nginx with the current configuration'
compose up -d --force-recreate --wait --wait-timeout 60 nginx

log 'Verifying container health'
compose ps postgres backend operator-console waypoint-editor db-viewer frontend nginx
for container in bomi-postgres bomi-backend bomi-operator-console bomi-waypoint-editor bomi-db-viewer bomi-frontend bomi-nginx; do
  health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container")"
  [[ "$health" == 'healthy' ]] || fail "$container is not healthy (state: $health)"
done

log 'Verifying HTTPS endpoints'
curl --fail --silent --show-error --retry 5 --retry-delay 2 \
  "https://$BOMI_DOMAIN/" >/dev/null
curl --fail --silent --show-error --retry 5 --retry-delay 2 \
  "https://$BOMI_DOMAIN/api/health" >/dev/null
operator_console_status="$(curl --silent --output /dev/null --write-out '%{http_code}' \
  "https://$BOMI_DOMAIN/operator-console/")"
[[ "$operator_console_status" == 401 ]] \
  || fail "Operator Console must reject unauthenticated requests (HTTP $operator_console_status)"
waypoint_editor_status="$(curl --silent --output /dev/null --write-out '%{http_code}' \
  "https://$BOMI_DOMAIN/waypoint-editor/")"
[[ "$waypoint_editor_status" == 401 ]] \
  || fail "Waypoint Editor must reject unauthenticated requests (HTTP $waypoint_editor_status)"
db_viewer_status="$(curl --silent --output /dev/null --write-out '%{http_code}' \
  "https://$BOMI_DOMAIN/db-viewer/")"
[[ "$db_viewer_status" == 401 ]] \
  || fail "DB Viewer must reject unauthenticated requests (HTTP $db_viewer_status)"

log "Deployment completed successfully for Git commit $GIT_SHA"
