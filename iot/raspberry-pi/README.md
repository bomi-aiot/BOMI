# Raspberry Pi 5 — IoT Gateway

Raspberry Pi에서 동작하는 IoT 게이트웨이 구성 영역이다. 현재는 Zigbee2MQTT가
브로커로 발행한 센서 메시지를 백엔드 계약 형식
(`bomi/v1/iot/<sourceId>/events`)으로 변환·재발행하는 번역기를 포함한다.

## 현재 구성

| 경로 | 역할 |
| --- | --- | --- |
| `zigbee2mqtt/` | Zigbee2MQTT와 로컬 Mosquitto Docker 환경 |
| `translator/` | Zigbee2MQTT 메시지를 백엔드 MQTT 계약으로 변환 |
| `translator/config/` | 번역기 장치 설정 예시 |
| `translator/tests/` | 단위 테스트와 실제 브로커 E2E 테스트 |

`zigbee2mqtt/compose.yaml`은 Zigbee2MQTT, 로컬 Mosquitto, MQTT 번역기를 함께
실행한다. Raspberry Pi Docker 실행 방법은 `zigbee2mqtt/README.md`를 따른다.

## 매핑 규칙 (MVP)

- 문(`contact`): 열림 전이는 `DOOR_OPENED`, 닫힘 전이는 `DOOR_CLOSED`.
- PIR(`occupancy`): `false`→`true` 전이에서만 `MOTION_DETECTED`.
- retained 메시지는 상태만 갱신하고 발행하지 않는다(재시작 오발행 방지).
- `PRESENCE_DETECTED`는 방향 판정 결과용 예약어이므로 센서에서 직접 발행하지 않는다.

## 실행

```bash
cd raspberry-pi/translator
pip install -r requirements.txt
cp config/device.example.yaml config/device.yaml
# 실제 설정은 config/device.yaml 로 복사(예시: config/device.example.yaml)
python main.py             # 또는: python main.py /path/to/device.yaml
```

## 테스트

```bash
cd raspberry-pi/translator
pip install -r requirements-dev.txt
python -m pytest
```
