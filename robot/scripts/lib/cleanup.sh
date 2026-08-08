#!/usr/bin/env bash
# 로봇 관련 ROS 2 프로세스를 모두 정리한다. 두 실행 스크립트가 공용으로 쓴다.
#
# 왜 필요한가: 매핑(slam_toolbox)과 주행(AMCL)은 둘 다 map -> odom TF 를
# 발행한다. 하나라도 남은 채 다른 쪽을 켜면 두 노드가 같은 변환을 서로
# 덮어써서 지도가 흔들리고 경로 탐색이 실패한다. 2026-08-07 시연 리허설에서
# 매핑 스택 2개와 Nav2 1개가 동시에 떠서 정확히 그 증상이 났다. ssh 를
# Ctrl+C 로 끊었을 때 원격 프로세스가 고아로 남은 것이 원인이었다.

LAUNCH_PATTERN="joystick_slam_robot|bomi_navigation_real|mapping_real"
NODE_PATTERN="slam_toolbox|ydlidar_ros2_driver_node|pico_driver|joy_linux\
|ekf_node|rviz2|teleop_node|scan_sanitizer|amcl|controller_server\
|planner_server|bt_navigator|map_server|behavior_server|velocity_smoother\
|lifecycle_manager|waypoint_follower|smoother_server|mqtt_bridge\
|nav2_robot_driver|nav2_waypoint_patrol|twist_mux"

bomi_cleanup() {
    # pkill은 일치하는 프로세스가 없으면 1을 반환한다. 이미 깨끗한 상태는
    # 실패가 아니므로 set -e를 쓰는 호출 스크립트에서도 계속 진행시킨다.
    pkill -INT -f "$LAUNCH_PATTERN" 2>/dev/null || true
    sleep 4
    pkill -f "$NODE_PATTERN" 2>/dev/null || true
    sleep 2
    # launch 부모가 자식만 잃고 남는 경우가 있어 PID 로 확실히 끊는다.
    for pid in $(pgrep -f "ros2 launch" 2>/dev/null || true); do
        kill -9 "$pid" 2>/dev/null || true
    done
    sleep 1
}

# 정리 후에도 남은 것이 있으면 이름을 돌려준다(비어 있으면 깨끗).
bomi_leftovers() {
    pgrep -a -f "ros2 launch|$NODE_PATTERN" 2>/dev/null | grep -v pgrep
}
