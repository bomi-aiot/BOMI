# SLAM 지도 기반 waypoint 순찰

`nav2_waypoint_patrol`은 SLAM으로 생성한 지도 위의 고정 지점들을 Nav2 목표로
순서대로 보내는 노드입니다. 이 노드는 모터를 직접 제어하지 않고, Nav2의
`navigate_to_pose` 액션 서버에 목표 pose만 전달합니다. 전역 경로는 NavFn
Planner의 A* 탐색으로 계산하며, 실제 `/cmd_vel` 생성과 장애물 회피는 Nav2가
담당합니다.

## waypoint 파일

기본 waypoint 예시는 `ros2_ws/src/core/config/room_waypoints.yaml`에 있습니다.

```yaml
waypoints:
  - name: sofa
    x: 0.0
    y: 0.0
    yaw: 0.0
loop: true
max_goal_retries: 3
goal_retry_delay_sec: 5.0
```

Nav2 목표가 실패하거나 거부되면 같은 waypoint를 `goal_retry_delay_sec` 간격으로
`max_goal_retries`회까지 재시도하며, 모두 실패하면 안전을 위해 해당 지점에서
순찰을 정지합니다.

## 실행

실행 전에는 SLAM으로 만든 `map.yaml`, `map.pgm`을 Nav2에 로드하고, 로봇의
위치 추정과 `navigate_to_pose` 액션 서버가 준비되어 있어야 합니다.

```bash
ros2 run core nav2_waypoint_patrol
```

다른 waypoint 파일을 사용하려면 다음처럼 파라미터를 넘깁니다.

```bash
ros2 run core nav2_waypoint_patrol --ros-args \
  -p waypoint_file:=/path/to/room_waypoints.yaml
```

## 시뮬레이션 없이 검증

시뮬레이션 없이 waypoint 파일 검증, 순찰 순서, 목표 재시도와 yaw 변환을
확인할 수 있습니다.

```bash
cd /mnt/c/S15P11E102/robot/ros2_ws
source /opt/ros/humble/setup.bash
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install --packages-select core
colcon test --packages-select core
colcon test-result --verbose
```

## TurtleBot3로 통합 확인

Gazebo Classic의 TurtleBot3 Waffle과 함께 순찰을 확인하는 launch가 있습니다.
[`turtlebot3-nav2-sim.md`](turtlebot3-nav2-sim.md)를 참고하세요.
