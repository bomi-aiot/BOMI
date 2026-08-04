#!/usr/bin/env bash
set -euo pipefail

DOOR_FRIENDLY_NAME="${1:-door_sensor}"
EXPECTED_SOURCE_ID="${2:-door_sensor}"
MQTT_CONTAINER="${MQTT_CONTAINER:-zigbee-mqtt}"
TRANSLATOR_CONTAINER="${TRANSLATOR_CONTAINER:-bomi-iot-translator}"
OUTPUT_FILE="$(mktemp)"
SUBSCRIBER_PID=""

cleanup() {
  if [[ -n "${SUBSCRIBER_PID}" ]]; then
    kill "${SUBSCRIBER_PID}" 2>/dev/null || true
  fi
  rm -f "${OUTPUT_FILE}"
}
trap cleanup EXIT

require_running() {
  local container="$1"
  local running
  running="$(docker inspect --format '{{.State.Running}}' "${container}" 2>/dev/null || true)"
  if [[ "${running}" != "true" ]]; then
    printf 'ERROR: 컨테이너가 실행 중이 아닙니다: %s\n' "${container}" >&2
    exit 1
  fi
}

require_running "${MQTT_CONTAINER}"
require_running "${TRANSLATOR_CONTAINER}"

docker exec "${MQTT_CONTAINER}" \
  mosquitto_sub -h localhost -t 'bomi/v1/iot/+/events' -v -C 1 -W 10 \
  >"${OUTPUT_FILE}" &
SUBSCRIBER_PID=$!

# 구독이 브로커에 반영된 후 닫힘 -> 열림 전이를 발생시킨다.
sleep 1

docker exec "${MQTT_CONTAINER}" \
  mosquitto_pub -h localhost \
  -t "zigbee2mqtt/${DOOR_FRIENDLY_NAME}" -m '{"contact":true}'
docker exec "${MQTT_CONTAINER}" \
  mosquitto_pub -h localhost \
  -t "zigbee2mqtt/${DOOR_FRIENDLY_NAME}" -m '{"contact":false}'

if ! wait "${SUBSCRIBER_PID}"; then
  printf 'ERROR: 10초 안에 BOMI 계약 이벤트를 수신하지 못했습니다.\n' >&2
  exit 1
fi
SUBSCRIBER_PID=""

if ! grep -Fq '"type": "DOOR_OPENED"' "${OUTPUT_FILE}"; then
  printf 'ERROR: DOOR_OPENED 이벤트가 아닙니다.\n' >&2
  cat "${OUTPUT_FILE}" >&2
  exit 1
fi

if ! grep -Fq "\"sourceId\": \"${EXPECTED_SOURCE_ID}\"" "${OUTPUT_FILE}"; then
  printf 'ERROR: sourceId가 예상값과 다릅니다: %s\n' "${EXPECTED_SOURCE_ID}" >&2
  cat "${OUTPUT_FILE}" >&2
  exit 1
fi

printf 'Smoke Test 통과: %s\n' "$(cat "${OUTPUT_FILE}")"
