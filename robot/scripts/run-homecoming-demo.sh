#!/usr/bin/env bash
# 귀가 시나리오 실기 준비를 한 번에 수행한다.
#
# 왜 필요한가: 2026-08-09 실기에서 준비 단계를 손으로 하다가 세 번 헛돌았다.
#   - 스택 기동 전에 문을 열어 시나리오가 고착 -> 이후 모든 트리거 차단
#   - 로봇을 옮긴 뒤 초기 위치를 다시 안 잡아 엉뚱한 곳으로 주행
#   - 스크립트가 "준비 완료"라고 했지만 Nav2 가 실제로는 죽어 있었음
# 그래서 이 스크립트는 매 단계를 '보고' 가 아니라 '실제 상태' 로 확인한다.
#
# 사용: ssh ssafy@<젯슨IP> 'bash ~/bomi_demo_run.sh'
set -uo pipefail

REPO="$HOME/S15P11E102"
WATCH_SECONDS=${WATCH_SECONDS:-900}
START_X=${START_X:--0.062}
START_Y=${START_Y:-0.103}
START_YAW=${START_YAW:-3.2244}

die() { echo "❌ $*" >&2; exit 1; }
step() { echo; echo "── $* ──"; }

psql_run() { ssh bomi "docker exec -i bomi-postgres psql -U bomi -d bomi -t" ; }

active_scenarios() {
    echo "SELECT count(*) FROM scenario WHERE final_status NOT IN \
        ('COMPLETED','FAILED','CANCELLED','TIMED_OUT');" | psql_run | tr -d ' \n'
}

robot_mode() {
    echo "SELECT current_mode FROM robot WHERE device_id='bomi-AA001';" \
        | psql_run | tr -d ' \n'
}

step "1/7 시나리오·로봇 상태 확인"
n=$(active_scenarios)
mode=$(robot_mode)
echo "  활성 시나리오 ${n}건 / 로봇 ${mode}"
# SAFE_STOP 하나만으로도 모든 이동 시나리오가 차단된다. 활성 시나리오가
# 없어도 리셋해야 한다(2026-08-09: 이 조건을 빠뜨려 문을 열어도 무반응이었다).
if [ "$n" != "0" ] || [ "$mode" != "IDLE" ]; then
    echo "  -> 리셋 실행"
    ssh bomi "docker exec -i bomi-postgres psql -U bomi -d bomi" \
        < "$REPO/scripts/dev/reset-demo.sql" > /dev/null || die "리셋 실패"
    n=$(active_scenarios); mode=$(robot_mode)
    echo "  리셋 후: 활성 ${n}건 / 로봇 ${mode}"
fi
[ "$n" = "0" ] || die "활성 시나리오가 남아 있음(${n}건) — 진행 중인 시나리오가 있는지 확인"
[ "$mode" = "IDLE" ] || die "로봇이 IDLE 이 아님(${mode}) — 이 상태로는 문을 열어도 차단된다"

step "2/7 스택 정리"
bash "$HOME/stop_stack.sh" > /dev/null 2>&1

step "3/7 스택 기동"
bash "$HOME/launch_homecoming.sh" || die "기동 실패"

step "4/7 준비 대기 (최대 4분)"
for _ in $(seq 1 80); do
    grep -qE '추종\] ai_vision 시작' /tmp/homecoming_run.log 2>/dev/null && break
    grep -qE '활성화되지|180초 안에|시작 직후 종료' /tmp/homecoming_run.log 2>/dev/null \
        && die "기동 실패 — /tmp/homecoming_run.log 확인"
    pgrep -f run-homecoming-follow > /dev/null || die "기동 프로세스가 사라짐"
    sleep 3
done
sleep 10

set +u
source /opt/ros/humble/setup.bash
source "$REPO/robot/ros2_ws/install/setup.bash"
set -u

step "5/7 Nav2 실제 상태 확인"
# 스크립트의 '준비 완료' 는 믿지 않는다. 노드마다 직접 물어본다.
for node in map_server amcl bt_navigator planner_server controller_server behavior_server; do
    state=""
    for _ in $(seq 1 10); do
        state=$(timeout 15 ros2 lifecycle get "/$node" 2>&1 | head -1)
        case "$state" in "active "*) break ;; esac
        sleep 2
    done
    case "$state" in
        "active "*) printf "  %-18s %s\n" "$node" "$state" ;;
        *) die "$node 가 active 가 아님: [$state]" ;;
    esac
done

step "6/7 초기 위치 설정 (로봇이 출발점에 있어야 함)"
timeout 60 python3 "$REPO/robot/scripts/lib/set_initpose.py" \
    "$START_X" "$START_Y" "$START_YAW" | tail -1
sleep 3
pose=$(timeout 20 ros2 run tf2_ros tf2_echo map base_link 2>&1 \
    | grep -m1 "Translation")
[ -n "$pose" ] || die "map -> base_link TF 가 없음"
echo "  $pose"

echo "  현관까지 경로 계획 시험:"
plan=$(timeout 40 ros2 action send_goal /compute_path_to_pose \
    nav2_msgs/action/ComputePathToPose \
    "{goal: {header: {frame_id: map}, pose: {position: {x: 0.49, y: 0.047, z: 0.0}, \
      orientation: {x: 0.0, y: 0.0, z: -0.5624, w: 0.8268}}}, use_start: false}" 2>&1 \
    | grep -E "Goal finished")
echo "    $plan"
case "$plan" in *SUCCEEDED*) ;; *) die "현관까지 경로가 안 나옴 — 로봇 위치 확인" ;; esac

step "7/7 MQTT 감시 시작"
bash "$HOME/watch_mqtt.sh" "$WATCH_SECONDS"

MY_IP=$(hostname -I | awk '{print $1}')
echo
echo "✅ 준비 완료 — 이제 문을 열어도 됩니다."
echo
echo "   개발 PC 에서 그대로 붙여 쓰세요:"
echo "     ssh ssafy@${MY_IP} 'tail -f /tmp/mqtt_watch.log'      # MQTT 이벤트"
echo "     ssh ssafy@${MY_IP} 'tail -f /tmp/bomi_ai_chat.log'    # AI 대화 로그"
echo "     ssh ssafy@${MY_IP} 'bash ~/stop_stack.sh'             # 전부 내리기"
