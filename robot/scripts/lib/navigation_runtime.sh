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

# 노드가 정확히 active 가 될 때까지 기다린다. 되면 0, 시간초과면 1.
#
# 앞을 고정해서 비교하는 이유: 이전 구현은 *"active "* 패턴이라
# "inactive [2]" 에도 걸렸다. 그래서 죽은 Nav2 를 "준비 완료"로 보고했고,
# 2026-08-09 실기에서 지도 없이 주행을 시작해 모든 명령이 실패했다.
# 서비스 호출이 타임아웃나면 빈 문자열이 오는데, 그때는 계속 기다린다.
bomi_wait_active() {
    local node=$1 tries=$2 state
    for _ in $(seq 1 "$tries"); do
        state=$(timeout 8 ros2 lifecycle get "$node" 2>&1 | head -1 || true)
        case "$state" in
            "active "*) return 0 ;;
        esac
        sleep 3
    done
    return 1
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

    # map_server 도 본다. 2026-08-09 실기에서 amcl 의 change_state 응답이
    # 타임아웃나며 localization 쪽 활성화가 중단됐는데, 확인 대상이 아니라
    # 지도 없이 "준비 완료"로 넘어갔다.
    if ! bomi_wait_active /map_server 20; then
        echo "map_server가 활성화되지 않았습니다. 로그: $BOMI_NAV_LOG" >&2
        return 1
    fi
    if ! bomi_wait_active /amcl 40; then
        echo "AMCL이 활성화되지 않았습니다. 로그: $BOMI_NAV_LOG" >&2
        return 1
    fi
    bomi_require_pico "$BOMI_NAV_LOG"

    echo "[3/4] 초기 위치 설정: $BOMI_START_X $BOMI_START_Y $BOMI_START_YAW"
    timeout 40 python3 "$BOMI_SCRIPT_DIR/lib/set_initpose.py" \
        "$BOMI_START_X" "$BOMI_START_Y" "$BOMI_START_YAW"

    if ! bomi_wait_active /bt_navigator 25; then
        echo "bt_navigator가 활성화되지 않았습니다. 로그: $BOMI_NAV_LOG" >&2
        return 1
    fi
    echo "[4/4] Nav2 준비 완료"
}

bomi_run_mqtt_bridge() {
    : "${MQTT_PASSWORD:?먼저 MQTT_PASSWORD 환경변수를 설정하세요.}"

    ros2 run bridge mqtt_bridge --ros-args \
        -p driver_type:=nav2 \
        -p robot_id:="${ROBOT_ID:-bomi-AA001}" \
        -p broker_host:="${MQTT_BROKER_HOST:-i15e102.p.ssafy.io}" \
        -p broker_port:="${MQTT_BROKER_PORT:-8883}" \
        -p use_tls:=true \
        -p ca_certs:="${MQTT_CA_CERTS:-/etc/ssl/certs/ca-certificates.crt}" \
        -p username:="${MQTT_USERNAME:-bomi-jetson}" \
        -p password:="$MQTT_PASSWORD" \
        -p waypoint_file:="$BOMI_WAYPOINTS" \
        -p approach_enabled:=false \
        -p search_enabled:="${BOMI_SEARCH_ENABLED:-false}" \
        -p search_start_topic:="${BOMI_SEARCH_START_TOPIC:-/wake_search/start}" \
        -p zigzag_enabled:="${BOMI_ZIGZAG_ENABLED:-false}"
}
