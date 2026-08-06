# Jetson Orin Nano

로봇 메인 제어와 별도로 필요한 Jetson 장치 연동 코드를 배치합니다. ROS 2 노드는 `robot` 워크스페이스에서 관리합니다.

## systemd
`bomi-robot.service` — 젯슨 전원 on 시 로봇 소프트웨어(ROS2 노드 + MQTT 브릿지)를 자동 실행하는 systemd 유닛 파일.

**상태: ExecStart 비어있음** — 로봇 소프트웨어(ros2_ws 하위 패키지들) 구현 완료 후 채워야 함.