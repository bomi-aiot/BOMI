# BOMI Robot

Ubuntu 22.04, ROS 2 Humble, Python 3.10을 기준으로 하는 로봇 워크스페이스입니다. Nav2와 SLAM Toolbox를 이용할 예정이며 실제 자율주행 패키지는 아직 구현하지 않았습니다.

현재 `robot/ros2_ws/src` 아래에는 이동 명령과 기본 상태 처리를 담당하는 `core` 패키지가 있습니다. 향후 다음 패키지를 추가할 예정입니다.

- `navigation`: Nav2 목적지 이동과 경로 추종
- `mapping`: SLAM Toolbox 지도 생성·관리
- `sensors`: LiDAR, IMU, 카메라 데이터 처리
- `communication`: 백엔드 MQTT/REST 통신
- `scenario`: 귀가 환영 등 로봇 시나리오 조율

```bash
cd robot/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install
ros2 run core status_publisher
```
