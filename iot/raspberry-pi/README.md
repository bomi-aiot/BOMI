# Raspberry Pi 5 — IoT 번역기

Zigbee2MQTT 가 브로커로 발행한 센서 메시지를 백엔드 계약 형식
(`bomi/v1/iot/<sourceId>/events`)으로 변환·재발행하는 번역기다. GPIO 를 직접
읽지 않고, 이미 브로커에 올라온 Zigbee 메시지를 구독해 통역한다.

## 구성 (관심사별 파일 분리)

| 파일 | 역할 | I/O |
| --- | --- | --- |
| `contract.py` | 계약 봉투·토픽 빌더 | 없음(순수) |
| `mapping.py` | Zigbee 값 → 계약 이벤트(엣지 판정) | 없음(순수) |
| `translator.py` | 구독 메시지 → mapping → 발행(주입) | 없음(발행 주입) |
| `main.py` | config 로드 + paho 로 실행 | paho-mqtt |
| `test/` | 순수 모듈·코어 단위 테스트 | 없음(브로커 불필요) |

## 매핑 규칙 (MVP)

- 문(`contact`): `true`(닫힘)→`false`(열림) 전이에서만 `DOOR_OPENED`.
- PIR(`occupancy`): `false`→`true` 전이에서만 `PRESENCE_DETECTED`(`direction=UNKNOWN`).
- retained 메시지는 상태만 갱신하고 발행하지 않는다(재시작 오발행 방지).
- 백엔드는 현재 `DOOR_OPENED` 만 시나리오 트리거로 처리한다.

## 실행

```bash
pip install -r ../requirements.txt
# 실제 설정은 config/device.yaml 로 복사(예시: config/device.example.yaml)
python main.py            # 또는: python main.py /path/to/device.yaml
```

## 테스트

```bash
python -m pytest        # iot/raspberry-pi 에서 실행
```
