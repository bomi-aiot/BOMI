#!/usr/bin/env bash
# 문 센서 현관 이동부터 백엔드 START_CONVERSATION 음성 대화까지 함께 실행한다.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib/navigation_runtime.sh
source "$HERE/lib/navigation_runtime.sh"

: "${MQTT_PASSWORD:?먼저 MQTT_PASSWORD 환경변수를 설정하세요.}"

AI_CHAT_DIR=$(cd "$HERE/../ai_chat" && pwd)
AI_CHAT_PYTHON=${AI_CHAT_PYTHON:-$AI_CHAT_DIR/venv/bin/python}
AI_CHAT_ENV_FILE=${AI_CHAT_ENV_FILE:-$AI_CHAT_DIR/.env}
AI_CHAT_LOG=${AI_CHAT_LOG:-/tmp/bomi_ai_chat.log}
AI_CHAT_PID=""

homecoming_finish() {
    if [ -n "$AI_CHAT_PID" ]; then
        kill -INT "$AI_CHAT_PID" 2>/dev/null || true
        for _ in 1 2 3 4 5; do
            kill -0 "$AI_CHAT_PID" 2>/dev/null || break
            sleep 1
        done
        kill -TERM "$AI_CHAT_PID" 2>/dev/null || true
        wait "$AI_CHAT_PID" 2>/dev/null || true
    fi
    bomi_navigation_finish
}

trap 'echo; echo "종료하며 음성 대화와 로봇을 정지합니다."; homecoming_finish' EXIT
trap 'exit 130' INT TERM HUP

if [ ! -x "$AI_CHAT_PYTHON" ]; then
    echo "AI Chat 가상환경이 없습니다: $AI_CHAT_PYTHON" >&2
    echo "robot/ai_chat/README.md의 Jetson 설치 절차를 먼저 실행하세요." >&2
    exit 1
fi
if [ ! -f "$AI_CHAT_ENV_FILE" ]; then
    echo "AI Chat 환경설정 파일이 없습니다: $AI_CHAT_ENV_FILE" >&2
    echo "robot/ai_chat/.env.example을 복사하고 API 키와 오디오 장치를 설정하세요." >&2
    exit 1
fi

# dotenv는 이미 존재하는 환경변수를 덮지 않는다. 현관 시나리오 통합 시험에
# 반드시 필요한 MQTT 값만 현재 실행 환경에서 명시하고, API·오디오 값은 .env가
# 소유하게 한다.
export AI_CHAT_ENV_FILE
export MQTT_ENABLED=true
export MQTT_BROKER_URL="${MQTT_BROKER_URL:-mqtts://i15e102.p.ssafy.io:8883}"
export MQTT_USERNAME="${MQTT_USERNAME:-bomi-jetson}"
export ROBOT_DEVICE_ID="${ROBOT_DEVICE_ID:-bomi-AA001}"

echo "[사전 검사] AI Chat 설정과 오디오 구성 확인"
(
    cd "$AI_CHAT_DIR"
    "$AI_CHAT_PYTHON" -c \
        'from bomi_ai_chat.config import get_settings; s=get_settings(); s.validate_conversation(); s.validate_mqtt(); print("AI Chat 설정 OK")'
)

bomi_navigation_start

echo "[AI] 음성 대화 런타임 시작: 로그 $AI_CHAT_LOG"
(
    cd "$AI_CHAT_DIR"
    exec "$AI_CHAT_PYTHON" -m bomi_ai_chat -v
) >"$AI_CHAT_LOG" 2>&1 &
AI_CHAT_PID=$!

sleep 5
if ! kill -0 "$AI_CHAT_PID" 2>/dev/null; then
    echo "AI Chat이 시작 직후 종료됐습니다:" >&2
    tail -80 "$AI_CHAT_LOG" >&2 || true
    exit 1
fi

echo "현관 이동 및 음성 대화 대기 중 (종료: Ctrl+C)"
echo "AI 로그 확인: tail -f $AI_CHAT_LOG"
bomi_run_mqtt_bridge
