#!/usr/bin/env bash
# BOMI 보미야 호출 시나리오 — 실행 전 자가진단
#
# 왜 필요한가
#   이 시나리오는 프로세스 8개가 함께 떠야 한다. 하나라도 준비가 안 되면
#   "보미야를 불렀는데 아무 일도 안 일어난다"로만 보이고, 어디가 문제인지
#   로그를 다 뒤져야 안다. 여기서 30초 만에 어느 칸이 비었는지 확인한다.
#
# 사용법
#   bash robot/scripts/preflight.sh
#   BOMI_ROOT=/path/to/repo bash robot/scripts/preflight.sh
#
# 종료 코드
#   0  모두 통과 (경고는 있을 수 있다)
#   1  하나 이상 실패 — 그대로 실행하면 시나리오가 동작하지 않는다

set -uo pipefail

BOMI_ROOT="${BOMI_ROOT:-/home/ssafy/S15P11E102}"
ROBOT="${BOMI_ROOT}/robot"
WS="${ROBOT}/ros2_ws"

PASS=0
FAIL=0
WARN=0

ok()   { printf '  \033[32m[ OK ]\033[0m %s\n' "$1"; PASS=$((PASS+1)); }
bad()  { printf '  \033[31m[FAIL]\033[0m %s\n' "$1"; FAIL=$((FAIL+1)); }
warn() { printf '  \033[33m[WARN]\033[0m %s\n' "$1"; WARN=$((WARN+1)); }
head_() { printf '\n\033[1m%s\033[0m\n' "$1"; }

printf '\033[1mBOMI 보미야 호출 시나리오 — 실행 전 점검\033[0m\n'
printf '저장소: %s\n' "${BOMI_ROOT}"

# ── 1. 장치 ──────────────────────────────────────────────────────────────────
head_ "1. USB 장치"

check_device() {
  local fixed="$1" fallback="$2" label="$3"
  if [[ -e "${fixed}" ]]; then
    ok "${label}: ${fixed} (udev 고정 이름)"
  elif [[ -e "${fallback}" ]]; then
    warn "${label}: ${fallback} 만 있음 — 재부팅하면 포트가 바뀔 수 있습니다."
    warn "      scripts/99-bomi-devices.rules 를 등록하면 이름이 고정됩니다."
  else
    bad "${label}: ${fixed} 도 ${fallback} 도 없습니다. 케이블을 확인하세요."
  fi
}

check_device /dev/bomi-pico  /dev/ttyACM0 "Pico H (바퀴)"
check_device /dev/bomi-lidar /dev/ttyUSB0 "YDLIDAR"

if ls /dev/video* >/dev/null 2>&1; then
  ok "카메라: $(ls /dev/video* | tr '\n' ' ')"
else
  bad "카메라(/dev/video*)를 찾을 수 없습니다."
fi

if id -nG "$USER" 2>/dev/null | tr ' ' '\n' | grep -qx dialout; then
  ok "시리얼 권한: ${USER} 가 dialout 그룹에 있습니다."
else
  warn "시리얼 권한: ${USER} 가 dialout 그룹에 없습니다."
  warn "      sudo usermod -aG dialout ${USER} 후 다시 로그인하세요."
fi

# ── 2. ROS 2 빌드 ────────────────────────────────────────────────────────────
head_ "2. ROS 2 워크스페이스"

if [[ -n "${ROS_DISTRO:-}" ]]; then
  ok "ROS_DISTRO=${ROS_DISTRO}"
else
  warn "ROS_DISTRO 가 비어 있습니다. source /opt/ros/humble/setup.bash 를 먼저 실행하세요."
fi

SHARE="${WS}/install/core/share/core"
for f in config/wake_search.yaml config/twist_mux.yaml launch/bomi_wake_search.launch.py; do
  if [[ -e "${SHARE}/${f}" ]]; then
    ok "설치본: ${f}"
  else
    bad "설치본에 ${f} 가 없습니다 — colcon build --symlink-install 을 실행하세요."
  fi
done

if [[ -x "${WS}/install/core/lib/core/wake_search" ]]; then
  ok "실행 파일: wake_search"
else
  bad "wake_search 실행 파일이 없습니다 — setup.py 의 console_scripts 등록과 재빌드를 확인하세요."
fi

# 회전 탐색은 twist_mux 없이는 /cmd_vel 에 닿지 못한다.
if [[ -n "${ROS_DISTRO:-}" ]] && [[ -d "/opt/ros/${ROS_DISTRO}/share/twist_mux" ]]; then
  ok "twist_mux 패키지 설치됨"
else
  bad "twist_mux 가 없습니다 — sudo apt install ros-\${ROS_DISTRO}-twist-mux"
fi

# ── 3. 파이썬 환경 (3개가 섞이면 안 된다) ────────────────────────────────────
head_ "3. 파이썬 환경"

paho_version() { "$1" -c 'import paho.mqtt as p; print(p.__version__)' 2>/dev/null; }

SYS_PAHO="$(paho_version python3)"
if [[ -z "${SYS_PAHO}" ]]; then
  bad "시스템 python3 에 paho-mqtt 가 없습니다 (ROS 2 bridge 가 씁니다)."
elif [[ "${SYS_PAHO}" == 2.* ]]; then
  ok "시스템 python3: paho-mqtt ${SYS_PAHO} (bridge 는 2.x 필요)"
else
  bad "시스템 python3: paho-mqtt ${SYS_PAHO} — bridge 는 2.x 가 필요합니다."
fi

CHAT_PY="${ROBOT}/ai_chat/venv/bin/python"
if [[ -x "${CHAT_PY}" ]]; then
  ok "ai_chat 가상환경: ${CHAT_PY}"
  CHAT_PAHO="$(paho_version "${CHAT_PY}")"
  if [[ -z "${CHAT_PAHO}" ]]; then
    bad "ai_chat: paho-mqtt 가 없습니다 — pip install -e \".[mqtt]\""
  elif [[ "${CHAT_PAHO}" == 1.* ]]; then
    ok "ai_chat: paho-mqtt ${CHAT_PAHO} (1.x 필요)"
  else
    bad "ai_chat: paho-mqtt ${CHAT_PAHO} — 1.x 가 필요합니다(2.x 면 웨이크워드 발행이 조용히 실패합니다)."
  fi
  if "${CHAT_PY}" -c 'import openwakeword' 2>/dev/null; then
    ok "ai_chat: openwakeword 사용 가능"
  else
    bad "ai_chat: openwakeword 를 불러올 수 없습니다."
  fi
else
  bad "ai_chat 가상환경이 없습니다: ${CHAT_PY}"
fi

VISION_PY="${ROBOT}/ai_vision/venv/bin/python"
if [[ -x "${VISION_PY}" ]]; then
  ok "ai_vision 가상환경: ${VISION_PY}"
  if "${VISION_PY}" -c 'import torch' 2>/dev/null; then
    CUDA="$("${VISION_PY}" -c 'import torch;print(torch.cuda.is_available())' 2>/dev/null)"
    if [[ "${CUDA}" == "True" ]]; then
      ok "ai_vision: torch + CUDA 사용 가능"
    else
      warn "ai_vision: torch 는 있으나 CUDA 를 못 씁니다 — 젯슨 전용 휠인지 확인하세요(CPU 추론은 매우 느립니다)."
    fi
  else
    bad "ai_vision: torch 를 불러올 수 없습니다 — 젯슨 전용 PyTorch 휠이 필요합니다."
  fi
  if "${VISION_PY}" -c 'import ultralytics' 2>/dev/null; then
    ok "ai_vision: ultralytics 사용 가능"
  else
    bad "ai_vision: ultralytics 를 불러올 수 없습니다."
  fi
else
  bad "ai_vision 가상환경이 없습니다: ${VISION_PY}"
fi

# ── 4. 모델과 설정 파일 ──────────────────────────────────────────────────────
head_ "4. 모델과 설정"

if [[ -f "${ROBOT}/ai_chat/models/bomiya.onnx" ]]; then
  ok "웨이크워드 모델: models/bomiya.onnx"
else
  bad "웨이크워드 모델이 없습니다: ai_chat/models/bomiya.onnx"
fi

if ls "${ROBOT}/ai_vision"/*.pt >/dev/null 2>&1; then
  ok "YOLO 모델: $(cd "${ROBOT}/ai_vision" && ls *.pt | tr '\n' ' ')"
else
  bad "YOLO 모델(*.pt)이 없습니다 — .gitignore 로 저장소에 포함되지 않으니 직접 복사하세요."
fi

ENV_FILE="${ROBOT}/ai_chat/.env"
if [[ -f "${ENV_FILE}" ]]; then
  ok ".env 존재"
  check_env() {
    local key="$1" hint="$2"
    local value
    value="$(grep -E "^${key}=" "${ENV_FILE}" | tail -1 | cut -d= -f2- | tr -d '[:space:]')"
    if [[ -z "${value}" ]]; then
      bad ".env: ${key} 가 비어 있습니다 — ${hint}"
    else
      ok ".env: ${key}=${value}"
    fi
  }
  check_env MQTT_ENABLED     "true 여야 백엔드에 웨이크워드가 전달됩니다"
  check_env MQTT_BROKER_URL  "mqtt(s)://host:port 형식"
  check_env ROBOT_DEVICE_ID  "deviceId 입니다(예: bomi-AA001). ROBOT_ID(UUID)와 다릅니다"
  check_env SEARCH_SIGNAL_ENABLED "1 이어야 로봇이 사람을 찾으러 돕니다"

  if grep -qE '^SEARCH_USE_BEAM_DIRECTION=1' "${ENV_FILE}"; then
    if grep -qE '^BEAM_FIX_ENABLED=1' "${ENV_FILE}"; then
      warn "빔이 정면에 고정돼 있어 소리 방향을 읽을 수 없습니다 — 전체 탐색으로 동작합니다."
    fi
    FRONT="$(grep -E '^BEAM_FRONT_AZIMUTH_DEG=' "${ENV_FILE}" | tail -1 | cut -d= -f2- | tr -d '[:space:]')"
    if [[ -z "${FRONT}" ]]; then
      warn "BEAM_FRONT_AZIMUTH_DEG 가 비어 있습니다 — tests/calibrate_beam.py 로 실측하세요."
    else
      ok ".env: BEAM_FRONT_AZIMUTH_DEG=${FRONT}"
    fi
  fi
else
  bad ".env 가 없습니다: ${ENV_FILE} (.env.example 을 복사해 값을 채우세요)"
fi

# ── 5. 포트 충돌 ─────────────────────────────────────────────────────────────
head_ "5. UDP 포트"

port_busy() {
  if command -v ss >/dev/null 2>&1; then
    ss -lun 2>/dev/null | grep -q ":$1 "
  else
    return 1
  fi
}

for entry in "5005:비전 결과 수신(vision_udp_bridge)" "5006:소리 방향 수신(wake_search)"; do
  port="${entry%%:*}"; label="${entry#*:}"
  if port_busy "${port}"; then
    warn "UDP ${port} (${label})를 이미 누가 쓰고 있습니다 — 이전 프로세스가 남아 있는지 확인하세요."
  else
    ok "UDP ${port} 사용 가능 (${label})"
  fi
done

# ── 정리 ─────────────────────────────────────────────────────────────────────
printf '\n\033[1m결과: 통과 %d, 경고 %d, 실패 %d\033[0m\n' "${PASS}" "${WARN}" "${FAIL}"
if [[ "${FAIL}" -gt 0 ]]; then
  printf '\033[31m실패 항목을 먼저 해결하세요. 그대로 실행하면 시나리오가 동작하지 않습니다.\033[0m\n'
  exit 1
fi
printf '\033[32m실행 준비 완료:\033[0m ros2 launch core bomi_wake_search.launch.py\n'
exit 0
