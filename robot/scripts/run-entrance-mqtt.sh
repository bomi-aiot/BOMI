#!/usr/bin/env bash
# EC2 MQTT 명령을 받아 ENTRANCE 등 백엔드 목적지로 이동한다.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib/navigation_runtime.sh
source "$HERE/lib/navigation_runtime.sh"

: "${MQTT_PASSWORD:?먼저 MQTT_PASSWORD 환경변수를 설정하세요.}"

trap 'echo; echo "종료하며 로봇을 정지합니다."; bomi_navigation_finish' EXIT
trap 'exit 130' INT TERM HUP

bomi_navigation_start

echo "문 센서 MQTT 자동 이동 대기 중 (종료: Ctrl+C)"
# launch 파일에서 name:=mqtt_bridge 전역 remap을 사용하면 이 프로세스가 내부에서
# 만드는 nav2_robot_driver까지 같은 이름으로 바뀐다. 직접 실행해 두 노드 이름과
# rosout publisher를 분리한다.
bomi_run_mqtt_bridge
