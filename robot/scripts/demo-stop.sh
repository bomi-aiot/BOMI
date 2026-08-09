#!/usr/bin/env bash
# 시연 스택을 통째로 내린다.
#
# lib/cleanup.sh 를 쓰되 두 가지를 더 한다.
#   - ai_chat 은 cleanup.sh 의 NODE_PATTERN 에 없다. 남겨두면 다음 기동의
#     ai_chat 과 마이크를 다투므로 여기서 따로 끊는다.
#   - 실행 스크립트를 -9 로 끊으면 trap 이 돌지 않아 lifecycle_manager 와
#     launch 부모가 고아로 남는다. 이름으로 한 번 더 정리한다.
#
# pkill 패턴을 스크립트 안에 두는 이유: ssh 인라인 명령으로 실행하면 원격 셸의
# 명령 문자열 자체가 패턴에 걸려 셸이 자기를 죽인다(ssh 가 255 로 끝난다).
set -uo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

pkill -9 -f 'run-homecoming' 2>/dev/null
pkill -f 'bomi_ai_chat' 2>/dev/null
pkill -f 'bomi_vision.udp_main' 2>/dev/null
pkill -f 'mosquitto_sub' 2>/dev/null
pkill -INT -f 'bomi_display.*/face_display|ros2 run bomi_display face_display' 2>/dev/null
sleep 3

# shellcheck source=lib/cleanup.sh
source "$HERE/lib/cleanup.sh"
bomi_cleanup
sleep 2

pkill -9 -f 'lifecycle_manager' 2>/dev/null
pkill -9 -f 'bomi_navigation_real' 2>/dev/null
sleep 2

leftovers=$(bomi_leftovers | head -8)
extra=$(pgrep -af 'bomi_ai_chat|bomi_vision|bomi_display.*/face_display' \
    | grep -v pgrep | head -3)
if [ -n "$leftovers$extra" ]; then
    echo "남은 프로세스:"
    [ -n "$leftovers" ] && echo "$leftovers"
    [ -n "$extra" ] && echo "$extra"
    exit 1
fi
echo "정리 완료 — 남은 프로세스 없음"
