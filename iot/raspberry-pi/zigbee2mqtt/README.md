# Zigbee2MQTT Gateway

Raspberry Pi 5에 연결한 Sonoff ZBDongle-P로 Zigbee 센서 데이터를 수신하는
Docker Compose 환경이다. Zigbee2MQTT와 로컬 Mosquitto Broker를 함께 실행한다.

## 구성

| 서비스 | 역할 | 기본 포트 |
| --- | --- | --- |
| `zigbee2mqtt` | Zigbee 센서 데이터를 MQTT 메시지로 변환하고 관리 UI 제공 | 8080 |
| `zigbee-mqtt` | Zigbee2MQTT와 IoT 번역기가 사용하는 로컬 MQTT Broker | 1883 |
| `bomi-iot-translator` | 센서 메시지를 BOMI MQTT 계약 이벤트로 변환 | 없음 |

확인된 센서 값은 다음과 같다.

- 도어 센서: `contact` (`true` 닫힘, `false` 열림)
- PIR 센서: `occupancy` (`true` 움직임 감지)

## 최초 설정

Raspberry Pi에서 Sonoff Dongle의 고정 장치 경로를 확인한다.

```bash
ls -l /dev/serial/by-id/
```

예시 파일을 실제 설정으로 복사하고 장치 경로를 입력한다.

```bash
cd iot/raspberry-pi/zigbee2mqtt
cp .env.example .env
cp data/configuration.example.yaml data/configuration.yaml
cp ../translator/config/device.example.yaml ../translator/config/device.yaml
```

`.env`의 `ZIGBEE_DEVICE_PATH`를 앞에서 확인한 `/dev/serial/by-id/...` 경로로
변경한다. `../translator/config/device.yaml`의 `friendly_name`은 Zigbee2MQTT에
등록된 실제 센서 이름과 일치시킨다. `.env`, `data/configuration.yaml`, 번역기의
`device.yaml`은 장치별 실제 설정이므로 Git에 커밋하지 않는다.

## 실행 및 확인

```bash
docker compose up -d
docker compose ps
```

번역기는 Compose 내부에서 `mqtt:1883`에 연결한다. 연결 상태와 이벤트 변환 로그는
다음 명령으로 확인한다.

```bash
docker compose logs -f translator
```

같은 네트워크의 PC에서 다음 주소로 관리 화면에 접속한다.

```text
http://<RASPBERRY_PI_IP>:8080
```

센서 MQTT 메시지는 다음 명령으로 확인한다.

```bash
docker exec -it zigbee-mqtt \
  mosquitto_sub -h localhost -t 'zigbee2mqtt/#' -v
```

변환된 BOMI 계약 이벤트는 다음 명령으로 확인한다.

```bash
docker exec -it zigbee-mqtt \
  mosquitto_sub -h localhost -t 'bomi/v1/iot/+/events' -v
```

로그와 종료 명령은 다음과 같다.

```bash
docker compose logs -f zigbee2mqtt
docker compose down
```

## 기존 Raspberry Pi 환경 이관

이미 센서가 페어링된 `~/zigbee2mqtt` 환경은 덮어쓰지 않는다. 먼저 컨테이너를
중지하고 기존 디렉터리를 백업한다.

```bash
cd ~/zigbee2mqtt
docker compose down
cd ~
cp -a zigbee2mqtt zigbee2mqtt-backup
```

기존 `data/configuration.yaml`, `data/database.db`,
`data/coordinator_backup.json`, `data/state.json`에는 Zigbee 네트워크와 센서
페어링 상태가 들어갈 수 있다. 이 파일은 Git에 올리지 않고 Raspberry Pi에서
유지한다. 저장소의 예시 설정과 기존 설정을 비교한 뒤 Compose와 Mosquitto
설정만 선택적으로 반영한다.

## 보안 참고

현재 Mosquitto는 Raspberry Pi 로컬 게이트웨이에서의 초기 연동을 위해 익명
접속을 허용한다. 외부 네트워크나 EC2 Broker에 연결할 때는 계정 인증, ACL 및
TLS를 별도 구성해야 한다.
