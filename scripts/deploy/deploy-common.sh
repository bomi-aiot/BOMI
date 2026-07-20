#!/usr/bin/env bash

compose() {
  docker compose --env-file "$BOMI_ENV_FILE" -f "$BOMI_COMPOSE_FILE" "$@"
}

deploy_log() {
  printf '[deploy] %s\n' "$*"
}

deploy_fail() {
  printf '[deploy] ERROR: %s\n' "$*" >&2
  exit 1
}

read_env_value() {
  local key="$1"
  awk -F= -v key="$key" '$1 == key { sub(/^[^=]*=/, ""); print; exit }' "$BOMI_ENV_FILE"
}

set_env_value() {
  local key="$1" value="$2" temporary_file
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

verify_release_commit() {
  local release_branch="$1" head_commit release_commit
  head_commit="$(git rev-parse HEAD)"
  release_commit="$(git rev-parse "refs/remotes/origin/$release_branch")" \
    || deploy_fail "origin/$release_branch is not available"
  [[ "$head_commit" == "$release_commit" ]] \
    || deploy_fail "HEAD is not the latest origin/$release_branch commit"
}

initialize_deploy() {
  command -v git >/dev/null 2>&1 || deploy_fail 'git is not installed'
  command -v docker >/dev/null 2>&1 || deploy_fail 'docker is not installed'
  command -v curl >/dev/null 2>&1 || deploy_fail 'curl is not installed'
  [[ -d "$BOMI_SOURCE_DIR/.git" ]] || deploy_fail "Git repository not found: $BOMI_SOURCE_DIR"
  [[ -r "$BOMI_ENV_FILE" ]] || deploy_fail "Environment file not readable: $BOMI_ENV_FILE"
  cd "$BOMI_SOURCE_DIR"
  [[ -z "$(git status --porcelain)" ]] || deploy_fail 'Git working tree is not clean'
  BOMI_COMPOSE_FILE="$BOMI_SOURCE_DIR/infra/compose.prod.yml"
  [[ -r "$BOMI_COMPOSE_FILE" ]] || deploy_fail "Compose file not readable: $BOMI_COMPOSE_FILE"
  GIT_SHA="$(git rev-parse --short=12 HEAD)"
  BOMI_DOMAIN="$(read_env_value BOMI_DOMAIN)"
  [[ -n "$BOMI_DOMAIN" ]] || deploy_fail 'BOMI_DOMAIN is missing'
}

verify_container_health() {
  local container="$1" health
  health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container")"
  [[ "$health" == healthy ]] || deploy_fail "$container is not healthy (state: $health)"
}
