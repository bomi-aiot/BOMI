#!/usr/bin/env bash
# Nav2 기반 실기 실행 스크립트가 공통으로 사용하는 시작·종료 절차.

set -euo pipefail

BOMI_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
BOMI_WS=$(cd "$BOMI_SCRIPT_DIR/../ros2_ws" && pwd)
BOMI_WAYPOINTS="$BOMI_WS/src/core/config/room_waypoints.yaml"
BOMI_STATE=${BOMI_STATE:-$HOME/.bomi_demo_state}
BOMI_NAV_LOG=${BOMI_NAV_LOG:-/tmp/bomi_navigation.log}
BOMI_NAV_PGID=""

# shellcheck source=cleanup.sh
source "$BOMI_SCRIPT_DIR/lib/cleanup.sh"
# shellcheck source=health.sh
source "$BOMI_SCRIPT_DIR/lib/health.sh"

bomi_navigation_finish() {
    if [ -n "$BOMI_NAV_PGID" ]; then
        kill -INT -- "-$BOMI_NAV_PGID" 2>/dev/null || true
        sleep 3
        kill -9 -- "-$BOMI_NAV_PGID" 2>/dev/null || true
    fi
    bomi_cleanup
}

bomi_navigation_load_state() {
    if [ -f "$BOMI_STATE" ]; then
        # shellcheck source=/dev/null
        source "$BOMI_STATE"
    else
        # shellcheck source=../demo_defaults.sh
        source "$BOMI_SCRIPT_DIR/demo_defaults.sh"
        START=$(python3 "$BOMI_SCRIPT_DIR/lib/read_waypoint.py" \
            "$BOMI_WAYPOINTS" "$FALLBACK_START_WAYPOINT")
    fi

    : "${MAP:?MAP이 설정되지 않았습니다. $BOMI_STATE 파일을 확인하세요.}"
    : "${START:?START가 설정되지 않았습니다. $BOMI_STATE 파일을 확인하세요.}"
    read -r BOMI_START_X BOMI_START_Y BOMI_START_YAW <<<"$START"
    export BOMI_START_X BOMI_START_Y BOMI_START_YAW

    BOMI_MAP_FILE="$BOMI_WS/src/mapping/maps/$MAP.yaml"
    if [ ! -f "$BOMI_MAP_FILE" ]; then
        echo "지도 파일이 없습니다: $BOMI_MAP_FILE" >&2
        return 1
    fi
}

bomi_navigation_start() {
    # ROS 2 Humble의 setup.bash는 일부 선택 환경변수를 값 없이 참조한다.
    # 호출 스크립트의 nounset(-u)은 유지하되 setup 파일을 읽는 동안만 끈다.
    set +u
    source /opt/ros/humble/setup.bash
    source "$BOMI_WS/install/setup.bash"
    set -u
    cd "$BOMI_WS"

    bomi_navigation_load_state

    echo "[1/4] 기존 ROS 2 주행 프로세스 정리"
    bomi_cleanup
    local leftovers
    leftovers=$(bomi_leftovers || true)
    if [ -n "$leftovers" ]; then
        echo "정리되지 않은 프로세스가 있습니다:" >&2
        echo "$leftovers" >&2
        return 1
    fi

    echo "[2/4] Nav2 시작: $BOMI_MAP_FILE"
    setsid ros2 launch core bomi_navigation_real.launch.py \
        map:="$BOMI_MAP_FILE" \
        pico_port:="${PICO_PORT:-/dev/ttyACM0}" \
        lidar_port:="${LIDAR_PORT:-/dev/ttyUSB0}" \
        use_rviz:=false >"$BOMI_NAV_LOG" 2>&1 &
    BOMI_NAV_PGID=$!

    local active=no
    for _ in $(seq 1 40); do
        case "$(timeout 8 ros2 lifecycle get /amcl 2>&1 || true)" in
            *"active "*) active=yes; break ;;
        esac
        sleep 3
    done
    if [ "$active" != yes ]; then
        echo "AMCL이 활성화되지 않았습니다. 로그: $BOMI_NAV_LOG" >&2
        return 1
    fi
    bomi_require_pico "$BOMI_NAV_LOG"

    echo "[3/4] 초기 위치 설정: $BOMI_START_X $BOMI_START_Y $BOMI_START_YAW"
    timeout 40 python3 "$BOMI_SCRIPT_DIR/lib/set_initpose.py" \
        "$BOMI_START_X" "$BOMI_START_Y" "$BOMI_START_YAW"

    active=no
    for _ in $(seq 1 25); do
        case "$(timeout 8 ros2 lifecycle get /bt_navigator 2>&1 || true)" in
            *"active "*) active=yes; break ;;
        esac
        sleep 3
    done
    if [ "$active" != yes ]; then
        echo "bt_navigator가 활성화되지 않았습니다. 로그: $BOMI_NAV_LOG" >&2
        return 1
    fi
    echo "[4/4] Nav2 준비 완료"
}
