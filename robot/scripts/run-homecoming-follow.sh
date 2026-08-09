#!/usr/bin/env bash
# 현관 이동·대화 후 AI Vision 사용자 추종까지 한 번에 실행한다.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$HERE/../.." && pwd)
ROS_WS="$REPO_ROOT/robot/ros2_ws"
VISION_DIR="$REPO_ROOT/robot/ai_vision"
VISION_PYTHON=${AI_VISION_PYTHON:-$VISION_DIR/venv/bin/python}
FOLLOW_LOG_DIR=${FOLLOW_LOG_DIR:-/tmp/bomi_homecoming_follow}
HOMECOMING_READY_FILE="$FOLLOW_LOG_DIR/homecoming.ready"
AUX_PIDS=()
HOMECOMING_PID=""

follow_finish() {
    rm -f "$HOMECOMING_READY_FILE"
    if [ -n "$HOMECOMING_PID" ]; then
        kill -INT "$HOMECOMING_PID" 2>/dev/null || true
    fi
    for pid in "${AUX_PIDS[@]}"; do
        kill -INT "$pid" 2>/dev/null || true
    done
    sleep 2
    for pid in "${AUX_PIDS[@]}"; do
        kill -TERM "$pid" 2>/dev/null || true
        wait "$pid" 2>/dev/null || true
    done
}

trap follow_finish EXIT
trap 'exit 130' INT TERM HUP

: "${MQTT_PASSWORD:?먼저 MQTT_PASSWORD 환경변수를 설정하세요}"

if [ ! -f /opt/ros/humble/setup.bash ]; then
    echo "ROS 2 Humble을 찾을 수 없습니다: /opt/ros/humble/setup.bash" >&2
    exit 1
fi
if [ ! -f "$ROS_WS/install/setup.bash" ]; then
    echo "ROS 2 워크스페이스가 빌드되지 않았습니다: $ROS_WS/install/setup.bash" >&2
    exit 1
fi
if [ ! -x "$VISION_PYTHON" ]; then
    echo "AI Vision 가상환경이 없습니다: $VISION_PYTHON" >&2
    echo "robot/ai_vision에서 python3 -m venv venv 후 패키지를 설치하세요." >&2
    exit 1
fi

mkdir -p "$FOLLOW_LOG_DIR"
rm -f "$HOMECOMING_READY_FILE"

set +u
source /opt/ros/humble/setup.bash
source "$ROS_WS/install/setup.bash"
set -u

start_aux() {
    local name=$1
    shift
    echo "[추종] $name 시작 — 로그: $FOLLOW_LOG_DIR/$name.log"
    "$@" >"$FOLLOW_LOG_DIR/$name.log" 2>&1 &
    AUX_PIDS+=("$!")
}

# 시연용 현관 흐름은 회전 탐색을 생략하고, FOLLOW_START 즉시 카메라 정면의
# 사용자를 추종한다. 공용 기본값은 /wake_search/start 그대로 유지한다.
export BOMI_SEARCH_ENABLED=true
export BOMI_SEARCH_START_TOPIC=/person_following/enable
export BOMI_HOMECOMING_READY_FILE="$HOMECOMING_READY_FILE"

# 귀가 인사 뒤 추종을 끝내고 완전히 정지한 다음 최신 MQTT 온습도로
# 후속 대화를 시작한다. 센서가 30초 주기라 최근 90초 값만 사용한다.
export HOMECOMING_AMBIENT_ENABLED="${HOMECOMING_AMBIENT_ENABLED:-true}"
export HOMECOMING_HOT_THRESHOLD_C="${HOMECOMING_HOT_THRESHOLD_C:-30}"
export HOMECOMING_AMBIENT_MAX_AGE_SEC="${HOMECOMING_AMBIENT_MAX_AGE_SEC:-90}"
export HOMECOMING_FOLLOW_AMBIENT_PHASE="${HOMECOMING_FOLLOW_AMBIENT_PHASE:-true}"
export HOMECOMING_FOLLOW_SECONDS="${HOMECOMING_FOLLOW_SECONDS:-20}"

if [ -n "${HOMECOMING_AMBIENT_TEST_TEMPERATURE_C:-}" ]; then
    echo "[테스트] 센서 대신 ${HOMECOMING_AMBIENT_TEST_TEMPERATURE_C}도 값을 사용합니다."
fi

echo "현관 대화 후 사용자 추종 시나리오를 시작합니다. 종료: Ctrl+C"
bash "$HERE/run-homecoming-voice.sh" &
HOMECOMING_PID=$!

# 기존 스크립트가 시작할 때 남은 ROS 프로세스를 정리하므로, MQTT 브리지가 준비된
# 뒤에 추종 구성요소를 올려야 정리 대상에 휩쓸리지 않는다.
ready=false
for _ in $(seq 1 90); do
    if ! kill -0 "$HOMECOMING_PID" 2>/dev/null; then
        wait "$HOMECOMING_PID"
        exit $?
    fi
    if [ -f "$HOMECOMING_READY_FILE" ]; then
        ready=true
        break
    fi
    sleep 2
done
if [ "$ready" != true ]; then
    echo "MQTT 브리지가 180초 안에 준비되지 않았습니다." >&2
    exit 1
fi

start_aux vision_udp_bridge ros2 run core vision_udp_bridge
start_aux person_follower ros2 launch core person_following.launch.py \
    output_topic:=/cmd_vel_follow start_enabled:=false
start_aux wake_search ros2 run core wake_search --ros-args \
    --params-file "$ROS_WS/src/core/config/wake_search.yaml" \
    -p follow_timeout_sec:=600.0
start_aux person_search_patrol ros2 run core person_search_patrol --ros-args \
    --params-file "$ROS_WS/src/core/config/person_search_patrol.yaml" \
    -p waypoint_file:="$ROS_WS/src/core/config/room_waypoints.yaml" \
    -p start_automatically:=false
start_aux twist_mux ros2 run twist_mux twist_mux --ros-args \
    --params-file "$ROS_WS/src/core/config/twist_mux.yaml" \
    -r cmd_vel_out:=/cmd_vel

echo "[추종] ai_vision 시작 — 로그: $FOLLOW_LOG_DIR/ai_vision.log"
(
    cd "$VISION_DIR"
    exec "$VISION_PYTHON" -u -m bomi_vision.udp_main \
        --host 127.0.0.1 \
        --port 5005 \
        --no-window \
        --confidence 0.30 \
        --horizontal-dead-zone 0.40 \
        --forward-threshold 0.90 \
        --lost-tolerance-frames 12 \
        --select-primary-person
) >"$FOLLOW_LOG_DIR/ai_vision.log" 2>&1 &
AUX_PIDS+=("$!")

sleep 5
for pid in "${AUX_PIDS[@]}"; do
    if ! kill -0 "$pid" 2>/dev/null; then
        echo "추종 구성요소가 시작 직후 종료됐습니다. 로그를 확인하세요: $FOLLOW_LOG_DIR" >&2
        exit 1
    fi
done

wait "$HOMECOMING_PID"
