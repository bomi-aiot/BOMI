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

# 현관까지 좌우 15도로 번갈아 기울며 다가간다(bridge/zigzag.py). 어르신을
# 반기러 나가는 걸음을 보여 주기 위한 것이라 귀가 대본에서만 켠다 —
# 순찰·매핑처럼 사람이 보고 있지 않은 이동에서는 의미가 없다.
# 실기에서 경유점이 벽에 걸려 경로가 안 나오면
# BOMI_ZIGZAG_ENABLED=false bash robot/scripts/demo-start.sh 로 끈다.
export BOMI_ZIGZAG_ENABLED="${BOMI_ZIGZAG_ENABLED:-true}"

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

# ai_vision 은 프레임 처리에 상한이 없어 놔두면 전 코어를 90%까지 채운다.
# 그러면 Nav2 의 20Hz 제어 루프와 lifecycle/costmap 서비스 호출이 데드라인을
# 놓쳐 주행이 실패한다(2026-08-09 실기: amcl 활성화 실패, 경로 계획 실패).
# 마지막 두 코어에 가두고 Nav2 에 나머지를 남긴다.
VISION_CPUS=${AI_VISION_CPUS:-}
if [ -z "$VISION_CPUS" ] && command -v nproc >/dev/null 2>&1; then
    _cores=$(nproc)
    if [ "$_cores" -ge 4 ]; then
        VISION_CPUS="$((_cores - 2)),$((_cores - 1))"
    fi
fi
VISION_LAUNCHER=()
if [ -n "$VISION_CPUS" ] && command -v taskset >/dev/null 2>&1; then
    VISION_LAUNCHER=(taskset -c "$VISION_CPUS")
    echo "[추종] ai_vision CPU 고정: $VISION_CPUS"
fi

# torch 2.11 휠이 nvidia/cu12/lib 아래 libcudss.so.0 을 깔면서 RPATH 를 안 남긴다.
# 이게 없으면 import torch 가 실패해 추종 단계가 통째로 빠진다.
_torch_libs="$VISION_DIR/venv/lib/python3.10/site-packages/nvidia/cu12/lib"

echo "[추종] ai_vision 시작 — 로그: $FOLLOW_LOG_DIR/ai_vision.log"
(
    cd "$VISION_DIR"
    if [ -d "$_torch_libs" ]; then
        export LD_LIBRARY_PATH="$_torch_libs${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    fi
    # 위에서 코어를 2개로 줄였으므로 torch 의 CPU 스레드도 함께 맞춘다.
    export OMP_NUM_THREADS=${OMP_NUM_THREADS:-2}
    # set -u 아래에서 빈 배열 전개가 안전하도록 +형태를 쓴다.
    exec ${VISION_LAUNCHER[@]+"${VISION_LAUNCHER[@]}"} \
        "$VISION_PYTHON" -u -m bomi_vision.udp_main \
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
