#!/usr/bin/env bash
# room_waypoints.yaml의 현재 순서대로 반복 순찰한다.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib/navigation_runtime.sh
source "$HERE/lib/navigation_runtime.sh"

trap 'echo; echo "종료하며 로봇을 정지합니다."; bomi_navigation_finish' EXIT
trap 'exit 130' INT TERM HUP

bomi_navigation_start

echo "웨이포인트 순찰 시작 (종료: Ctrl+C)"
ros2 run core nav2_waypoint_patrol --ros-args \
    -p waypoint_file:="$BOMI_WAYPOINTS"
