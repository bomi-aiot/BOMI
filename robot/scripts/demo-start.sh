#!/usr/bin/env bash
# 시연 준비를 한 번에 수행하고, 각 단계를 '실제 상태'로 확인한다.
#
# 왜 필요한가
#   2026-08-09 실기에서 준비를 손으로 하다가 세 번 헛돌았다.
#     - 스택이 뜨기 전에 문을 열어 시나리오가 고착됐고, 이후 모든 트리거가
#       ACTIVE_SCENARIO_EXISTS 로 조용히 막혔다.
#     - 로봇을 옮긴 뒤 초기 위치를 다시 잡지 않아 엉뚱한 곳으로 주행했다.
#     - run-homecoming-voice.sh 가 "Nav2 준비 완료"라고 했지만 map_server 와
#       amcl 이 inactive 였다. 지도 없이 주행을 시작해 모든 명령이 실패했다.
#   그래서 이 스크립트는 보고를 믿지 않는다. lifecycle 은 노드에 직접 묻고,
#   위치는 TF 로 확인하고, 경로는 실제로 한 번 계산해 본다.
#
# 사용법
#   bash robot/scripts/demo-start.sh        # 로봇을 출발점에 놓고 실행한다
#   WATCH_SECONDS=1800 bash robot/scripts/demo-start.sh
#   bash robot/scripts/demo-stop.sh         # 전부 내린다
#
# 종료 코드
#   0  준비 완료 — 문을 열어도 된다
#   1  어느 단계에서 멈췄다. 그 지점의 이유가 출력된다.
set -uo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$HERE/../.." && pwd)
ROS_WS="$REPO_ROOT/robot/ros2_ws"

WATCH_SECONDS=${WATCH_SECONDS:-900}
WAYPOINTS=${WAYPOINTS:-$ROS_WS/src/core/config/room_waypoints.yaml}
RUN_LOG=${RUN_LOG:-/tmp/homecoming_run.log}
WATCH_LOG=${WATCH_LOG:-/tmp/mqtt_watch.log}
DISPLAY_LOG=${DISPLAY_LOG:-/tmp/bomi_display.log}
LCD_DISPLAY=${LCD_DISPLAY:-:0}
AI_STATUS_FILE=${AI_STATUS_FILE:-/tmp/bomi_ai_status}
export BOMI_DISPLAY_STATUS_FILE="$AI_STATUS_FILE"

die() { echo "❌ $*" >&2; exit 1; }
step() { echo; echo "── $* ──"; }

psql_run() { ssh bomi "docker exec -i bomi-postgres psql -U bomi -d bomi -t"; }

# 좌표는 재매핑할 때마다 바뀐다. 여기에 적어두면 그때마다 이 파일도 고쳐야
# 하고, 잊으면 옛 좌표로 초기 위치를 잡은 채 "준비 완료"가 뜬다(2026-08-09에
# 실제로 그랬다 — 방향이 130도 틀어진 상태로 통과했다).
# bomi_map.sh 가 갱신하는 room_waypoints.yaml 을 단일 출처로 읽는다.
waypoint_of() {
    local name=$1 line
    line=$(timeout 20 python3 "$HERE/lib/read_waypoint.py" "$WAYPOINTS" "$name" 2>&1) \
        || die "웨이포인트 '$name' 를 읽지 못했다: $line"
    [ -n "$line" ] || die "웨이포인트 '$name' 가 $WAYPOINTS 에 없다"
    printf '%s\n' "$line"
}

[ -f "$WAYPOINTS" ] || die "웨이포인트 파일이 없다: $WAYPOINTS"
read -r START_X START_Y START_YAW <<<"$(waypoint_of charging)"
read -r ENTRANCE_X ENTRANCE_Y ENTRANCE_YAW <<<"$(waypoint_of entrance)"

# ── 1. 시나리오·로봇 상태 ────────────────────────────────────────────────────
step "1/9 시나리오·로봇 상태 확인"

active_count() {
    echo "SELECT count(*) FROM scenario WHERE final_status NOT IN \
        ('COMPLETED','FAILED','CANCELLED','TIMED_OUT');" | psql_run | tr -d ' \n'
}
robot_mode() {
    echo "SELECT current_mode FROM robot WHERE device_id='bomi-AA001';" \
        | psql_run | tr -d ' \n'
}

n=$(active_count); mode=$(robot_mode)
echo "  활성 시나리오 ${n}건 / 로봇 ${mode}"
# SAFE_STOP 하나만으로도 모든 이동 시나리오가 차단된다. 활성 시나리오가 없어도
# 리셋해야 한다 — 이 조건을 빠뜨려 "문을 열어도 무반응"을 한 번 겪었다.
if [ "$n" != "0" ] || [ "$mode" != "IDLE" ]; then
    echo "  -> 리셋 실행"
    ssh bomi "docker exec -i bomi-postgres psql -U bomi -d bomi" \
        < "$REPO_ROOT/scripts/dev/reset-demo.sql" > /dev/null || die "리셋 실패"
    n=$(active_count); mode=$(robot_mode)
    echo "  리셋 후: 활성 ${n}건 / 로봇 ${mode}"
fi
[ "$n" = "0" ] || die "활성 시나리오가 남아 있다(${n}건) — 진행 중인 시나리오가 있는지 확인한다"
[ "$mode" = "IDLE" ] || die "로봇이 IDLE 이 아니다(${mode}) — 이 상태로는 문을 열어도 차단된다"

# ── 2. 스피커와 TTS ──────────────────────────────────────────────────────────
# 스택을 2분 올린 뒤에 "로봇이 말을 안 한다"를 발견하는 것보다, 여기서 먼저
# 막는 편이 낫다. 2026-08-09 실기의 무음은 스피커가 아니라 Typecast 403 이었다.
step "2/9 스피커·TTS 확인"
if [ "${SKIP_SPEECH_CHECK:-0}" = "1" ]; then
    echo "    SKIP_SPEECH_CHECK=1 — 건너뛴다 (로봇이 무음일 수 있다)"
else
    AI_PY="$REPO_ROOT/robot/ai_chat/.venv/bin/python"
    [ -x "$AI_PY" ] || AI_PY="$REPO_ROOT/robot/ai_chat/venv/bin/python"
    [ -x "$AI_PY" ] || die "ai_chat 가상환경을 찾지 못했다 (.venv 또는 venv)"
    # ROS 의 PYTHONPATH 가 섞이면 ai_chat 의존성이 깨진다(CLAUDE.md 환경 함정).
    ( cd "$REPO_ROOT/robot/ai_chat" \
      && env -u PYTHONPATH "$AI_PY" "$HERE/lib/check_speech.py" ) \
        || die "스피커·TTS 점검 실패 — 위 사유를 먼저 해결한다 (건너뛰려면 SKIP_SPEECH_CHECK=1)"
fi

# ── 3~4. 정리와 기동 ─────────────────────────────────────────────────────────
step "3/9 스택 정리"
bash "$HERE/demo-stop.sh" > /dev/null 2>&1
rm -f "$AI_STATUS_FILE"

step "4/9 스택 기동"
: "${MQTT_PASSWORD:=$(grep -m1 '^MQTT_PASSWORD=' \
    "$REPO_ROOT/robot/ai_chat/.env" | cut -d= -f2- | tr -d '\r')}"
export MQTT_PASSWORD
[ -n "$MQTT_PASSWORD" ] || die "MQTT_PASSWORD 를 .env 에서 읽지 못했다"

# 젯슨의 ai_chat 가상환경은 venv 가 아니라 .venv 다.
if [ -x "$REPO_ROOT/robot/ai_chat/.venv/bin/python" ]; then
    export AI_CHAT_PYTHON="$REPO_ROOT/robot/ai_chat/.venv/bin/python"
fi
# 추종이 길수록 AMCL 이 어긋날 여지가 커진다. 시연에는 10초면 충분하다.
export HOMECOMING_FOLLOW_SECONDS="${HOMECOMING_FOLLOW_SECONDS:-10}"

rm -f "$RUN_LOG"
nohup setsid bash "$HERE/run-homecoming-follow.sh" \
    > "$RUN_LOG" 2>&1 < /dev/null &
echo "  기동 시작 (로그: $RUN_LOG)"

step "5/9 준비 대기 (최대 4분)"
for _ in $(seq 1 80); do
    grep -qE '추종\] ai_vision 시작' "$RUN_LOG" 2>/dev/null && break
    grep -qE '활성화되지|180초 안에|시작 직후 종료' "$RUN_LOG" 2>/dev/null \
        && die "기동 실패 — $RUN_LOG 확인"
    pgrep -f run-homecoming-follow > /dev/null || die "기동 프로세스가 사라졌다"
    sleep 3
done
sleep 10

set +u
source /opt/ros/humble/setup.bash
source "$ROS_WS/install/setup.bash"
set -u

# ── 5. lifecycle 은 노드에 직접 묻는다 ───────────────────────────────────────
step "6/9 Nav2 실제 상태 확인"
for node in map_server amcl bt_navigator planner_server controller_server \
            behavior_server; do
    state=""
    for _ in $(seq 1 10); do
        # 서비스 호출이 타임아웃나면 빈 문자열이 온다. 그때는 계속 기다린다.
        state=$(timeout 15 ros2 lifecycle get "/$node" 2>&1 | head -1)
        case "$state" in "active "*) break ;; esac
        sleep 2
    done
    case "$state" in
        "active "*) printf "  %-18s %s\n" "$node" "$state" ;;
        *) die "$node 가 active 가 아니다: [$state]" ;;
    esac
done

# ── 6. 위치와 경로 ───────────────────────────────────────────────────────────
step "7/9 초기 위치 설정 (로봇이 출발점에 있어야 한다)"
timeout 60 python3 "$HERE/lib/set_initpose.py" \
    "$START_X" "$START_Y" "$START_YAW" | tail -1
sleep 3
pose=$(timeout 20 ros2 run tf2_ros tf2_echo map base_link 2>&1 \
    | grep -m1 "Translation")
[ -n "$pose" ] || die "map -> base_link TF 가 없다"
echo "  $pose"

echo "  현관까지 경로 계획 시험: ($ENTRANCE_X, $ENTRANCE_Y, yaw $ENTRANCE_YAW)"
# yaw -> 쿼터니언(z, w). 방향까지 맞춰야 목표 자세가 실제 현관 방향이 된다.
read -r EQ_Z EQ_W <<<"$(python3 -c \
    "import math,sys; y=float(sys.argv[1]); print(math.sin(y/2), math.cos(y/2))" \
    "$ENTRANCE_YAW")"
plan=$(timeout 40 ros2 action send_goal /compute_path_to_pose \
    nav2_msgs/action/ComputePathToPose \
    "{goal: {header: {frame_id: map}, pose: {position: {x: $ENTRANCE_X, \
      y: $ENTRANCE_Y, z: 0.0}, orientation: {x: 0.0, y: 0.0, z: $EQ_Z, \
      w: $EQ_W}}}, use_start: false}" 2>&1 | grep -E "Goal finished")
echo "    $plan"
case "$plan" in
    *SUCCEEDED*) ;;
    *) die "현관까지 경로가 나오지 않는다 — 로봇이 출발점에 있는지 확인한다" ;;
esac

# ── 7. LCD 상태 화면 ─────────────────────────────────────────────────────────
step "8/9 LCD 상태 화면 시작"
command -v python3 >/dev/null 2>&1 || die "python3를 찾을 수 없다"
python3 -c 'import PySide6' >/dev/null 2>&1 \
    || die "PySide6가 없다 — python3 -m pip install PySide6 실행 후 다시 시작한다"

# 새로 추가된 bomi_display가 아직 install에 없다면 이 패키지만 빠르게 빌드한다.
if ! ros2 pkg prefix bomi_display >/dev/null 2>&1; then
    (cd "$ROS_WS" && colcon build --symlink-install --packages-select bomi_display) \
        > "$DISPLAY_LOG.build" 2>&1 \
        || die "LCD 패키지 빌드 실패 — $DISPLAY_LOG.build 확인"
    set +u
    source "$ROS_WS/install/setup.bash"
    set -u
fi

rm -f "$DISPLAY_LOG"
nohup setsid env DISPLAY="$LCD_DISPLAY" \
    ros2 run bomi_display face_display --ai-status-file "$AI_STATUS_FILE" \
    > "$DISPLAY_LOG" 2>&1 < /dev/null &
DISPLAY_PID=$!
sleep 3
kill -0 "$DISPLAY_PID" 2>/dev/null \
    || die "LCD 상태 화면을 시작하지 못했다 — $DISPLAY_LOG 확인"
echo "  LCD $LCD_DISPLAY 전체 화면 (PID: $DISPLAY_PID, 로그: $DISPLAY_LOG)"

# ── 8. 감시 ──────────────────────────────────────────────────────────────────
step "9/9 MQTT 감시 시작"
rm -f "$WATCH_LOG"
nohup setsid timeout "$WATCH_SECONDS" mosquitto_sub \
    -h "${MQTT_BROKER_HOST:-i15e102.p.ssafy.io}" \
    -p "${MQTT_BROKER_PORT:-8883}" --capath /etc/ssl/certs \
    -u "${MQTT_USERNAME:-bomi-jetson}" -P "$MQTT_PASSWORD" \
    -t 'bomi/v1/robot/bomi-AA001/commands' \
    -t 'bomi/v1/robot/bomi-AA001/events' \
    -t 'bomi/v1/robot/bomi-AA001/results' \
    -t 'bomi/v1/ai/bomi-AA001/commands' \
    -v > "$WATCH_LOG" 2>&1 < /dev/null &
sleep 3
pgrep -f 'mosquitto_[s]ub' > /dev/null || die "MQTT 감시를 시작하지 못했다"
echo "  감시 ${WATCH_SECONDS}초 (로그: $WATCH_LOG)"

MY_IP=$(hostname -I | awk '{print $1}')
echo
echo "✅ 준비 완료 — 이제 문을 열어도 된다."
echo
echo "   개발 PC 에서:"
echo "     ssh ssafy@${MY_IP} 'tail -f $WATCH_LOG'                              # MQTT"
echo "     ssh ssafy@${MY_IP} 'tail -f /tmp/bomi_homecoming_follow/wake_search.log'  # 회전 탐색"
echo "     ssh ssafy@${MY_IP} 'tail -f /tmp/bomi_ai_chat.log'                    # 대화"
echo "     ssh ssafy@${MY_IP} 'bash $HERE/demo-stop.sh'                          # 내리기"
