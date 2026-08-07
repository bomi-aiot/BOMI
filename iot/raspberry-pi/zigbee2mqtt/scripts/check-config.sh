#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
GATEWAY_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
REPO_DIR="$(git -C "${GATEWAY_DIR}" rev-parse --show-toplevel)"

ENV_FILE="${GATEWAY_DIR}/.env"
ZIGBEE_CONFIG="${GATEWAY_DIR}/data/configuration.yaml"
TRANSLATOR_CONFIG="${GATEWAY_DIR}/../translator/config/device.yaml"
BRIDGE_CONFIG="${GATEWAY_DIR}/mosquitto/config/conf.d/bridge.conf"

errors=0

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  errors=$((errors + 1))
}

require_file() {
  local path="$1"
  local setup_hint="$2"
  if [[ ! -f "${path}" ]]; then
    fail "${path} 파일이 없습니다. ${setup_hint}"
  fi
}

require_ignored() {
  local path="$1"
  if ! git -C "${REPO_DIR}" check-ignore --quiet "${path}"; then
    fail "${path} 파일이 Git 제외 대상이 아닙니다. 비밀정보를 커밋하지 마세요."
  fi
}

require_file "${ENV_FILE}" "cp .env.example .env"
require_file "${ZIGBEE_CONFIG}" \
  "기존 Raspberry Pi 설정을 유지하거나 configuration.example.yaml을 복사하세요."
require_file "${TRANSLATOR_CONFIG}" \
  "cp ../translator/config/device.example.yaml ../translator/config/device.yaml"
require_file "${BRIDGE_CONFIG}" \
  "mkdir -p mosquitto/config/conf.d && cp mosquitto/bridge.example.conf mosquitto/config/conf.d/bridge.conf"

if [[ -f "${ENV_FILE}" ]]; then
  device_path="$(sed -n 's/^[[:space:]]*ZIGBEE_DEVICE_PATH=//p' "${ENV_FILE}" | tail -n 1)"
  if [[ -z "${device_path}" || "${device_path}" == *'<'* || "${device_path}" == *'>'* ]]; then
    fail ".env의 ZIGBEE_DEVICE_PATH를 실제 /dev/serial/by-id/... 경로로 변경하세요."
  elif [[ ! -e "${device_path}" ]]; then
    fail "Zigbee 장치 경로가 존재하지 않습니다: ${device_path}"
  fi
fi

if [[ -f "${BRIDGE_CONFIG}" ]]; then
  if grep -q 'REPLACE_WITH_DEVICE_LOCAL_PASSWORD' "${BRIDGE_CONFIG}"; then
    fail "bridge.conf의 remote_password를 실제 장치 로컬 비밀번호로 변경하세요."
  fi
  if ! grep -q '^remote_username[[:space:]]\+bomi-iot-gateway[[:space:]]*$' \
    "${BRIDGE_CONFIG}"; then
    fail "bridge.conf의 remote_username은 bomi-iot-gateway여야 합니다."
  fi
fi

require_ignored "${ENV_FILE}"
require_ignored "${ZIGBEE_CONFIG}"
require_ignored "${TRANSLATOR_CONFIG}"
require_ignored "${BRIDGE_CONFIG}"

if ((errors > 0)); then
  printf '\n설정 검사 실패: %d개 항목을 수정하세요.\n' "${errors}" >&2
  exit 1
fi

if command -v docker >/dev/null 2>&1; then
  docker compose --project-directory "${GATEWAY_DIR}" \
    --file "${GATEWAY_DIR}/compose.yaml" config --quiet
else
  printf 'WARN: docker 명령이 없어 Compose 검사를 건너뜁니다.\n' >&2
fi

printf '설정 검사를 통과했습니다.\n'
