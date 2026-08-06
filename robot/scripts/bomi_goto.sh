#!/usr/bin/env bash
# 시연 2단계 — 저장된 지도로 Nav2 를 올려 현관까지 자율주행한다. (로봇에서 실행)
#
#   bomi_goto.sh [지도이름]      기본값: bomi_map.sh 가 남긴 이름
#
# 사람이 할 일은 없다. 목표를 보내기 전에 경로 존재를 확인하고, 없으면
# 보내지 않고 이유를 알려준다.
set -o pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WS=$(cd "$HERE/../ros2_ws" && pwd)
WAYPOINTS=$WS/src/core/config/room_waypoints.yaml
STATE=$HOME/.bomi_demo_state
LOG=/tmp/bomi_goto.log

# shellcheck source=lib/cleanup.sh
source "$HERE/lib/cleanup.sh"
source /opt/ros/humble/setup.bash
source "$WS/install/setup.bash"
cd "$WS" || exit 1

if [ ! -f "$STATE" ]; then
    echo "❌ $STATE 가 없습니다. bomi_map.sh 를 먼저 실행하세요."
    exit 1
fi
# shellcheck source=/dev/null
source "$STATE"
MAP=${1:-$MAP}
read -r SX SY SYAW <<<"$START"
if [ -z "$SYAW" ]; then
    echo "❌ 출발 좌표를 읽지 못했습니다. bomi_map.sh 를 다시 실행하세요."
    exit 1
fi
if [ ! -f "$WS/src/mapping/maps/$MAP.yaml" ]; then
    echo "❌ 지도가 없습니다: src/mapping/maps/$MAP.yaml"
    exit 1
fi

LAUNCH_PGID=""
finish() {
    if [ -n "$LAUNCH_PGID" ]; then
        kill -INT -- "-$LAUNCH_PGID" 2>/dev/null
        sleep 3
        kill -9 -- "-$LAUNCH_PGID" 2>/dev/null
    fi
    bomi_cleanup
}
trap 'echo; echo "중단 — 정리합니다"; finish; exit 130' INT TERM HUP

echo "▶ 0/5 기존 프로세스 정리"
bomi_cleanup
LEFT=$(bomi_leftovers)
if [ -n "$LEFT" ]; then
    echo "❌ 정리되지 않은 프로세스가 있습니다:"; echo "$LEFT"; exit 1
fi
echo "  깨끗함 (지도 $MAP, 출발 $SX $SY $SYAW)"

echo "▶ 1/5 Nav2 실행 — 로그 $LOG"
setsid ros2 launch core bomi_navigation_real.launch.py \
    map:="$WS/src/mapping/maps/$MAP.yaml" \
    pico_port:=/dev/ttyACM0 lidar_port:=/dev/ttyUSB0 > "$LOG" 2>&1 &
LAUNCH_PGID=$!

for _ in $(seq 1 40); do
    ros2 service list 2>/dev/null | grep -q /amcl/get_state && break
    sleep 3
done
if ! ros2 service list 2>/dev/null | grep -q /amcl/get_state; then
    echo "❌ AMCL 이 뜨지 않았습니다. $LOG 를 확인하세요."; finish; exit 1
fi
sleep 3

echo "▶ 2/5 초기 위치 입력"
timeout 40 python3 "$HERE/lib/set_initpose.py" "$SX" "$SY" "$SYAW" || {
    echo "❌ 초기 위치 설정 실패"; finish; exit 1; }

echo "▶ 3/5 Nav2 활성화 대기"
ACTIVE=no
for _ in $(seq 1 25); do
    case "$(timeout 8 ros2 lifecycle get /bt_navigator 2>&1)" in
        *"active "*) ACTIVE=yes; break;;
    esac
    sleep 3
done
if [ "$ACTIVE" != yes ]; then
    echo "❌ bt_navigator 가 active 가 되지 않았습니다. $LOG 확인."
    finish; exit 1
fi
echo "  bt_navigator active"

echo "▶ 4/5 경로 사전 검증"
if ! timeout 60 python3 "$HERE/lib/precheck_path.py" "$WAYPOINTS"; then
    echo
    echo "❌ 이동 명령을 보내지 않았습니다(위 사유 참고)."
    echo "   Nav2 는 계속 떠 있으니, 로봇을 옮긴 뒤 이 스크립트를 다시 실행하세요."
    exit 2
fi

echo "▶ 5/5 현관으로 이동"
timeout 200 ros2 run core goto_waypoint --ros-args \
    -p waypoint_name:=entrance \
    -p waypoint_file:="$WAYPOINTS"
RESULT=$?

FINAL=$(timeout 40 python3 "$HERE/lib/read_pose.py" 2>/dev/null)
echo
if [ "$RESULT" -eq 0 ]; then
    echo "✅ 2단계 완료 — 최종 위치: ${FINAL:-읽기 실패}"
else
    echo "❌ 주행 실패 — 최종 위치: ${FINAL:-읽기 실패}"
    echo "   원인은 $LOG 의 planner_server / controller_server 줄을 보세요."
fi
exit $RESULT
