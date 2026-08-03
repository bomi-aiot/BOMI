# Raspberry Pi 5 — IoT Gateway

Raspberry Pi에서 동작하는 IoT 게이트웨이 구성 영역이다. 현재는 Zigbee2MQTT가
브로커로 발행한 센서 메시지를 백엔드 계약 형식
(`bomi/v1/iot/<sourceId>/events`)으로 변환·재발행하는 번역기를 포함한다.

Zigbee2MQTT와 Mosquitto의 Docker 구성은 후속 작업에서 이 디렉터리에 추가한다.

## 현재 구성

| 경로 | 역할 |
| --- | --- | --- |
| `translator/` | Zigbee2MQTT 메시지를 백엔드 MQTT 계약으로 변환 |
| `translator/config/` | 번역기 장치 설정 예시 |
| `translator/tests/` | 단위 테스트와 실제 브로커 E2E 테스트 |

## 매핑 규칙 (MVP)

- 문(`contact`): `true`(닫힘)→`false`(열림) 전이에서만 `DOOR_OPENED`.
- PIR(`occupancy`): `false`→`true` 전이에서만 `PRESENCE_DETECTED`(`direction=UNKNOWN`).
- retained 메시지는 상태만 갱신하고 발행하지 않는다(재시작 오발행 방지).
- 백엔드는 현재 `DOOR_OPENED` 만 시나리오 트리거로 처리한다.

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
