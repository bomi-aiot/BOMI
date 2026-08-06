# Nav2 시뮬레이션 문제 해결

증상과 확인할 곳만 정리합니다. 원인과 설계 근거는 해당 파일의 주석에 있습니다.
실행 방법은 [`../README.md`](../README.md)를 참고하세요.

## 주행이 시작되지만 목표가 중단된다

```text
GridBased: failed to create plan
No valid trajectories
PathDistCritic: global plan points were not in the local costmap and free
```

**Nav2 파라미터보다 먼저 Gazebo 실제 자세의 roll/pitch를 확인합니다.**
차체가 기울면 LiDAR가 바닥을 스캔하고, 오도메트리 TF는 평면 변환만 발행하므로
바닥 반사가 가짜 근거리 장애물로 코스트맵에 누적됩니다.

수평 유지 조건은 `description/models/bomi_robot/model.sdf`의 구동륜 조인트와
캐스터 주석에 있습니다. `simulation` 패키지의 `test_robot_model_stability.py`가
이 조건을 검증합니다.

## 목표 근처에서 제자리 회전만 한다

```text
controller_server: Failed to make progress
```

`core/config/nav2_safe_params.yaml`의 `FollowPath.xy_goal_tolerance`와
`general_goal_checker.xy_goal_tolerance` 값을 비교합니다. 해당 주석에 조건이
있습니다.

이 파일은 `nav2_patrol_sim.launch.py`와 공유하므로 값을 바꿀 때는
[TurtleBot3 순찰 시뮬레이션](turtlebot3-nav2-sim.md) 동작도 확인해야 합니다.

## RViz에서 로봇이 순간이동한다

`2D Pose Estimate`로 실제 위치와 다른 곳을 지정하면 AMCL 위치 추정이 깨집니다.
로봇이 이동한 것이 아니라 좌표계가 바뀐 것입니다. `Ctrl+C`로 종료하고 다시
실행합니다. 목표 지정은 `2D Goal Pose`를 사용합니다.

## LiDAR 거리가 모두 최솟값으로 나온다

WSLg와 Gazebo Fortress 조합에서 NVIDIA D3D12 렌더링을 쓰면 GPU LiDAR가 모든
거리를 최솟값으로 반환할 수 있습니다. launch 파일이 Gazebo와 RViz에 `llvmpipe`
소프트웨어 렌더링을 적용하므로 별도 지정은 필요하지 않습니다. 이 설정을
바꿀 때는 `/scan` 값이 실제 벽 거리와 맞는지 확인합니다.

## 지도와 월드의 장애물 위치가 다르다

AMCL 위치 추정과 Nav2 경로 검증을 신뢰할 수 없습니다. `map:=` 인자로 다른
지도를 쓸 때는 같은 Gazebo 월드에서 만든 지도를 전달합니다.

## 빌드가 실패한다

```text
error: can't copy '.../build/core/launch/<파일>.launch.py':
doesn't exist or not a regular file
```

브랜치를 바꾼 뒤 이전 브랜치의 launch 파일 심볼릭 링크가 `build/`에 남은
경우입니다. `setup.py`가 `glob('launch/*.launch.py')`로 파일을 모을 때 끊어진
링크를 잡습니다. 생성물을 지우고 다시 빌드합니다.

```bash
cd /mnt/c/S15P11E102/robot/ros2_ws
rm -rf build install log
colcon build --symlink-install
```
