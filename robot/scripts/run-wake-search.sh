#!/usr/bin/env bash
# "보미야" 웨이크워드 → 방향 탐색 → 추종 실기 실행 원클릭 스크립트.
#
# 이전 실행이 완전히 안 죽고 pico/lidar 시리얼 포트를 붙잡고 있으면 이번
# 실행이 조용히 실패한다(2026-08-09 실기, pico_driver가 포트 응답 없음으로
# 죽어 로봇이 아예 안 움직였다) — 시작 전에 항상 정리한다.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib/cleanup.sh
source "$HERE/lib/cleanup.sh"
# shellcheck source=lib/health.sh
source "$HERE/lib/health.sh"

BOMI_WS=$(cd "$HERE/../ros2_ws" && pwd)
AI_CHAT_DIR=$(cd "$HERE/../ai_chat" && pwd)
AI_CHAT_PYTHON=${AI_CHAT_PYTHON:-$AI_CHAT_DIR/.venv/bin/python}
WAKE_LOG=${WAKE_LOG:-/tmp/bomi_wake_search.log}
WAKE_PGID=""

wake_search_finish() {
    if [ -n "$WAKE_PGID" ]; then
        kill -INT -- "-$WAKE_PGID" 2>/dev/null || true
        sleep 3
        kill -9 -- "-$WAKE_PGID" 2>/dev/null || true
    fi
    bomi_cleanup
}

trap 'echo; echo "종료하며 로봇을 정지합니다. 로그: $WAKE_LOG"; wake_search_finish' EXIT
trap 'exit 130' INT TERM HUP

if [ ! -x "$AI_CHAT_PYTHON" ]; then
    echo "AI Chat 가상환경이 없습니다: $AI_CHAT_PYTHON" >&2
    exit 1
fi

set +u
source /opt/ros/humble/setup.bash
source "$BOMI_WS/install/setup.bash"
set -u
cd "$BOMI_WS"

echo "[1/3] 기존 프로세스·시리얼 포트 정리"
bomi_cleanup
leftovers=$(bomi_leftovers || true)
if [ -n "$leftovers" ]; then
    echo "정리되지 않은 프로세스가 있습니다:" >&2
    echo "$leftovers" >&2
    exit 1
fi

echo "[2/3] wake_search 스택 시작 (로그: $WAKE_LOG)"
setsid ros2 launch core bomi_wake_search.launch.py \
    ai_chat_python:="$AI_CHAT_PYTHON" >"$WAKE_LOG" 2>&1 &
WAKE_PGID=$!

bomi_require_pico "$WAKE_LOG"

echo "[3/3] 준비 완료 — '보미야'로 불러보세요 (종료: Ctrl+C)"
echo "로그 실시간 확인: tail -f $WAKE_LOG"
wait "$WAKE_PGID"
