# BOMI IoT

장치별 책임을 분리한 IoT 코드 영역입니다.

- `raspberry-pi`: Zigbee 센서 게이트웨이와 MQTT 이벤트 발행
- `jetson`: Jetson Orin Nano 장치 연동 보조 코드
- `sensor-nodes`: 재사용 가능한 센서 노드
- `mqtt`: 토픽 및 메시지 처리 모듈

Raspberry Pi 번역기의 설치 및 실행 방법은 `raspberry-pi/README.md`를 따릅니다.
실제 네트워크·인증 정보와 장치별 설정은 커밋하지 않습니다.
