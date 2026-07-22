#!/usr/bin/env bash
set -Eeuo pipefail

readonly BOMI_SOURCE_DIR="${BOMI_SOURCE_DIR:-$(git rev-parse --show-toplevel)}"
readonly BOMI_ENV_FILE="${BOMI_MQTT_ENV_FILE:-/home/ubuntu/bomi/secrets/mqtt.env}"
readonly BOMI_RELEASE_BRANCH="${BOMI_RELEASE_BRANCH:-be-main}"
readonly BOMI_COMPOSE_FILE="${BOMI_MQTT_COMPOSE_FILE:-$BOMI_SOURCE_DIR/infra/compose.mqtt.prod.yml}"

compose() {
  docker compose --env-file "$BOMI_ENV_FILE" -f "$BOMI_COMPOSE_FILE" "$@"
}

deploy_log() {
  printf '[mqtt-deploy] %s\n' "$*"
}

deploy_fail() {
  printf '[mqtt-deploy] ERROR: %s\n' "$*" >&2
  exit 1
}

verify_release_commit() {
  local release_branch="$1" head_commit release_commit
  head_commit="$(git rev-parse HEAD)"
  release_commit="$(git rev-parse "refs/remotes/origin/$release_branch")" \
    || deploy_fail "origin/$release_branch is not available"
  [[ "$head_commit" == "$release_commit" ]] \
    || deploy_fail "HEAD is not the latest origin/$release_branch commit"
}

verify_container_health() {
  local container="$1" health
  health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container")"
  [[ "$health" == healthy ]] \
    || deploy_fail "$container is not healthy (state: $health)"
}

command -v git >/dev/null 2>&1 || deploy_fail 'git is not installed'
command -v docker >/dev/null 2>&1 || deploy_fail 'docker is not installed'
[[ -d "$BOMI_SOURCE_DIR/.git" ]] || deploy_fail "Git repository not found: $BOMI_SOURCE_DIR"
[[ -r "$BOMI_ENV_FILE" ]] || deploy_fail "Environment file not readable: $BOMI_ENV_FILE"
[[ -r "$BOMI_COMPOSE_FILE" ]] || deploy_fail "Compose file not readable: $BOMI_COMPOSE_FILE"
cd "$BOMI_SOURCE_DIR"
[[ -z "$(git status --porcelain)" ]] || deploy_fail 'Git working tree is not clean'
readonly GIT_SHA="$(git rev-parse --short=12 HEAD)"

verify_release_commit "$BOMI_RELEASE_BRANCH"
deploy_log "Deploying MQTT Broker commit $GIT_SHA from $BOMI_RELEASE_BRANCH"
compose --profile tools config --quiet
compose --profile tools pull mosquitto mosquitto-cert-sync mqtt-smoke-test
compose --profile tools run --rm --no-deps mosquitto-cert-sync
compose up -d --wait --wait-timeout 60 mosquitto
compose kill -s HUP mosquitto
sleep 1
verify_container_health bomi-mosquitto

BOMI_MQTT_ENV_FILE="$BOMI_ENV_FILE" \
BOMI_MQTT_COMPOSE_FILE="$BOMI_COMPOSE_FILE" \
  "$BOMI_SOURCE_DIR/scripts/deploy/verify-mqtt.sh"

deploy_log "MQTT Broker deployment completed successfully: $GIT_SHA"
