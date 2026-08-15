# Zigbee2MQTT Gateway

Raspberry Pi 5에 연결한 Sonoff ZBDongle-P로 Zigbee 센서 데이터를 수신하는
Docker Compose 환경이다. Zigbee2MQTT와 로컬 Mosquitto Broker를 함께 실행한다.

## 구성

| Compose 서비스 | 컨테이너 이름 | 역할 | 기본 포트 |
| --- | --- | --- | --- |
| `zigbee2mqtt` | `zigbee2mqtt` | Zigbee 센서 데이터를 MQTT 메시지로 변환하고 관리 UI 제공 | 8080 |
| `mqtt` | `zigbee-mqtt` | Zigbee2MQTT와 IoT 번역기가 사용하는 로컬 MQTT Broker | 1883 |
| `translator` | `bomi-iot-translator` | 센서 메시지를 BOMI MQTT 계약 이벤트로 변환 | 없음 |

`docker compose ...` 명령에는 **서비스** 이름을, `docker exec ...` 에는
**컨테이너** 이름을 쓴다. 아래 예시들도 그렇게 나뉘어 있다.

이미지 태그는 Zigbee2MQTT 만 `latest` 이고 Mosquitto 는 `eclipse-mosquitto:2` 로
메이저를 고정했다. 재빌드 시점에 따라 Zigbee2MQTT 동작이 달라질 수 있다.

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
mkdir -p mosquitto/config/conf.d
cp mosquitto/bridge.example.conf mosquitto/config/conf.d/bridge.conf
```

무엇을 왜 복사하는지는 아래와 같다.

| 복사본 | 원본 | 무엇을 바꿔야 하나 |
| --- | --- | --- |
| `.env` | `.env.example` | `ZIGBEE_DEVICE_PATH` (필수, 기본값 없음) |
| `data/configuration.yaml` | `data/configuration.example.yaml` | 대개 그대로 (Zigbee 채널 11, 어댑터 `zstack` — Sonoff ZBDongle-P 기준) |
| `../translator/config/device.yaml` | `device.example.yaml` | `friendly_name`, `source_id` |
| `mosquitto/config/conf.d/bridge.conf` | `mosquitto/bridge.example.conf` | `remote_password` |

> `translator` 컨테이너는 `device.yaml` 이 없으면 **뜨지 않는다.** 읽기 전용
> bind 를 `create_host_path: false` 로 걸어 두었기 때문이며, 첫 실행 실패의
> 가장 흔한 원인이다.

`.env`의 `ZIGBEE_DEVICE_PATH`를 앞에서 확인한 `/dev/serial/by-id/...` 경로로
변경한다. `../translator/config/device.yaml`의 `friendly_name`은 Zigbee2MQTT에
등록된 실제 센서 이름과 일치시킨다. `.env`, `data/configuration.yaml`, 번역기의
`device.yaml`은 장치별 실제 설정이므로 Git에 커밋하지 않는다.

`mosquitto/config/conf.d/bridge.conf`의 `remote_password`에는 EC2 Mosquitto의
`bomi-iot-gateway` 계정 비밀번호를 입력한다. 이 파일은 Git에서 제외되며
Raspberry Pi에만 보관한다.

서비스를 실행하기 전에 아래를 검사한다.

```bash
./scripts/check-config.sh
```

이 스크립트가 보는 것은 넷이다 — 설정 파일 4개의 존재, `ZIGBEE_DEVICE_PATH` 가
실제 경로인지, Bridge 계정이 채워졌는지, 그리고 **설정 파일들이 git-ignore
대상인지**. 마지막 항목이 비밀정보 커밋을 막는 자리라 가장 중요하다.

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

> 이 구독에는 **DHT11 온습도 이벤트(`AMBIENT_ENVIRONMENT_OBSERVED`)도 함께
> 보인다.** DHT11 수집기는 이 Compose 안이 아니라 Pi 호스트 systemd 로 돌면서
> 같은 로컬 브로커에 발행하기 때문이다(`bomi-iot-translator` 이미지에는 DHT11
> 코드가 들어 있지 않다). 설정과 실행은 [`../README.md`](../README.md) 의
> "DHT11 온습도 이벤트" 절을 따른다.

## EC2 MQTT Broker 전달

로컬 Mosquitto Bridge는 Translator가 발행한 다음 토픽만 EC2 운영 Broker로
단방향 전달한다.

```text
bomi/v1/iot/+/events
```

운영 연결 정보는 다음과 같다.

| 항목 | 값 |
| --- | --- |
| Host | `i15e102.p.ssafy.io` |
| Port | `8883` |
| TLS | 사용, Let's Encrypt 서버 인증서 검증 |
| Username | `bomi-iot-gateway` |
| QoS | 1 |

Bridge 는 `bridge_outgoing_retain false` 로 retain 을 막는다. 계약이 retain 을
금지하므로 이 설정 자체가 계약 준수의 일부다.

Bridge 연결 상태는 Mosquitto 로그에서 확인한다.

```bash
docker compose logs -f mqtt
```

비밀번호 오류, 인증서 검증 오류 또는 네트워크 단절 시 로그에 연결 실패가
출력된다. 비밀번호와 실제 `bridge.conf` 내용은 이슈, MR 또는 Git에 첨부하지
않는다.

## 가짜 도어 센서 Smoke Test

Mosquitto와 Translator가 실행 중이면 실제 센서 없이 닫힘 → 열림 메시지를
발행하고 `DOOR_OPENED` 계약 이벤트를 자동으로 확인할 수 있다.

```bash
./scripts/smoke-test.sh
```

실제 `friendly_name`과 `source_id`가 기본값 `door_sensor`와 다르면 인자로
전달한다.

```bash
./scripts/smoke-test.sh <door_friendly_name> <expected_source_id>
```

> ⚠️ **`source_id` 는 아직 두 값이 공존한다.** 예시 설정과 이 스크립트는
> `door_sensor` 를, 백엔드 정식 등록값은 `door-sensor-01` 을 쓴다. 백엔드가
> 임시로 둘 다 받아 주고 있으나, 그 줄에는 "IoT 가 `door-sensor-01` 로
> 되돌리면 지운다"는 메모가 붙어 있다. 새 Pi 를 설정한다면
> **`door-sensor-01` 로 맞추는 편이 안전하다.**

이 검사는 로컬 메시지 변환까지 확인한다. EC2 수신 여부는 Mosquitto Bridge 로그와
Backend 로그에서 별도로 확인한다.

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
접속을 허용한다. 이 포트는 신뢰할 수 있는 로컬 네트워크에서만 사용해야 한다.
EC2 연결은 `bomi-iot-gateway` 계정, 발행 전용 ACL, TLS 서버 인증서 검증을
사용한다.
