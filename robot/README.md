# BOMI Robot

Ubuntu 22.04, ROS 2 Humble, Python 3.10을 기준으로 하는 로봇 워크스페이스입니다. Nav2와 SLAM Toolbox를 이용할 예정이며 실제 자율주행 패키지는 아직 구현하지 않았습니다.

향후 `robot/ros2_ws/src` 아래에 다음 패키지를 생성합니다.

- `bomi_navigation`: Nav2 목적지 이동과 경로 추종
- `bomi_mapping`: SLAM Toolbox 지도 생성·관리
- `bomi_sensors`: LiDAR, IMU, 카메라 데이터 처리
- `bomi_communication`: 백엔드 MQTT/REST 통신
- `bomi_scenario`: 귀가 환영 등 로봇 시나리오 조율

```bash
cd robot/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install
```
