# BOMI IoT

장치별 책임을 분리한 IoT 코드 영역입니다.

- `raspberry-pi`: 현관 센서, GPIO, UART/I2C, MQTT 이벤트 발행
- `jetson`: Jetson Orin Nano 장치 연동 보조 코드
- `sensor-nodes`: 재사용 가능한 센서 노드
- `mqtt`: 토픽 및 메시지 처리 모듈
- `config`: 장치 설정 예시(실제 네트워크·인증 정보는 커밋 금지)

실제 센서 제어는 하드웨어 핀 구성 확정 후 구현합니다. Python 3.10 환경에서 `pip install -r requirements.txt`로 공통 의존성을 설치할 수 있습니다.
