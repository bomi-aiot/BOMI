#!/usr/bin/env bash
set -Eeuo pipefail

readonly BOMI_SOURCE_DIR="${BOMI_SOURCE_DIR:-$(git rev-parse --show-toplevel)}"
readonly BOMI_ENV_FILE="${BOMI_MQTT_ENV_FILE:-/home/ubuntu/bomi/secrets/mqtt.env}"
readonly BOMI_COMPOSE_FILE="${BOMI_MQTT_COMPOSE_FILE:-$BOMI_SOURCE_DIR/infra/compose.mqtt.prod.yml}"

compose() {
  docker compose --env-file "$BOMI_ENV_FILE" -f "$BOMI_COMPOSE_FILE" "$@"
}

[[ -r "$BOMI_ENV_FILE" ]] || {
  printf '[mqtt-verify] ERROR: environment file not readable: %s\n' "$BOMI_ENV_FILE" >&2
  exit 1
}

health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' bomi-mosquitto)"
[[ "$health" == healthy ]] || {
  printf '[mqtt-verify] ERROR: bomi-mosquitto is not healthy (state: %s)\n' "$health" >&2
  exit 1
}

compose --profile tools run --rm --no-deps mqtt-smoke-test
printf '[mqtt-verify] MQTT authentication, TLS, publish, and subscribe checks passed\n'
