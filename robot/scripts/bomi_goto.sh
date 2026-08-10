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
# shellcheck source=lib/health.sh
source "$HERE/lib/health.sh"
source /opt/ros/humble/setup.bash
source "$WS/install/setup.bash"
cd "$WS" || exit 1

# 상태 파일은 1단계가 2단계에게 남기는 쪽지다(쓸 지도 이름과 출발 좌표).
# 젯슨 홈에만 있는 런타임 산출물이라 재부팅·브랜치 전환·홈 초기화로 사라지고,
# 사라지면 2단계가 여기서 멈춘다. 2026-08-07 에 실제로 그래서 손으로 복원했다.
#
# 같은 출발 좌표가 이미 저장소에 있다 — charging(=DEFAULT, 대기 위치)을
# bomi_map.sh 가 출발 지점으로 갱신하기 때문이다. 그래서 쪽지가 없으면
# 저장소에서 읽어 진행한다. 좌표를 두 곳에 적어 동기화하는 대신 저장소를
# 단일 출처로 두고, 상태 파일은 캐시로만 쓴다.
if [ -f "$STATE" ]; then
    # shellcheck source=/dev/null
    source "$STATE"
else
    echo "⚠ $STATE 가 없습니다 — 저장소 기본값으로 진행합니다."
    # shellcheck source=demo_defaults.sh
    source "$HERE/demo_defaults.sh"
    START=$(python3 "$HERE/lib/read_waypoint.py" "$WAYPOINTS" "$FALLBACK_START_WAYPOINT") || {
        echo "❌ 저장소에서도 출발 좌표를 읽지 못했습니다."
        echo "   bomi_map.sh 를 먼저 실행하세요."
        exit 1
    }
    echo "  지도=$MAP 출발=$START (웨이포인트 '$FALLBACK_START_WAYPOINT')"
    echo "  ⚠ 로봇이 실제로 그 자리에 있어야 합니다 — 아니면 AMCL 이 어긋난 채 출발합니다."
fi

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

# AMCL 이 active 가 될 때까지 기다린다. 아래 bt_navigator 확인과 같은 방식이다.
#
# `ros2 service list | grep /amcl/get_state` 는 두 가지 이유로 못 쓴다.
# 첫째, ROS 데몬이 캐시한 그래프를 보므로 방금 뜬 노드를 한동안 못 본다.
# 둘째, 찾은 뒤 판정을 위해 한 번 더 호출하면 그 호출이 일시적으로 실패할 때
# 멀쩡한 스택을 실패로 처리한다. 2026-08-07 실기에서 실제로 그랬다 —
# 로그에는 "Server amcl connected with bond / Managed nodes are active" 가
# 남았는데 스크립트만 "AMCL 이 뜨지 않았습니다"로 멈췄다.
#
# `ros2 lifecycle get` 은 데몬 캐시가 아니라 서비스를 직접 부르고, 결과를
# 플래그에 담아 두 번 묻지 않는다.
AMCL_ACTIVE=no
for _ in $(seq 1 40); do
    case "$(timeout 8 ros2 lifecycle get /amcl 2>&1)" in
        *"active "*) AMCL_ACTIVE=yes; break;;
    esac
    sleep 3
done
if [ "$AMCL_ACTIVE" != yes ]; then
    echo "❌ AMCL 이 active 가 되지 않았습니다. $LOG 를 확인하세요."
    finish; exit 1
fi
echo "  amcl active"
sleep 3

# 모터 드라이버가 없으면 Nav2 는 경로까지 잘 뽑고 로봇만 제자리에 선다.
# 그 상태의 실패는 "주행 실패"로만 보여서 원인을 찾는 데 오래 걸린다.
bomi_require_pico "$LOG" || { finish; exit 1; }

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
