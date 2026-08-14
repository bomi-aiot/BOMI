# BOMI Hardware

BOMI의 현재 프로토타입은 Jetson Orin Nano, Raspberry Pi Pico, MDD10A 모터 드라이버, 4개의 DC 모터와 엔코더, IMU, 2D LiDAR, 카메라 및 스마트홈 센서로 구성됩니다.

> 아래 자료는 현재 프로토타입의 연결 기준입니다. 부품이나 배선이 변경되면 구조도와 실제 장비를 함께 갱신해야 합니다.

## 전체 연결 구조

모터 구동 전원과 Jetson 전원은 서로 다른 경로를 사용합니다. Jetson은 USB 직렬 통신으로 Pico에 명령을 전달하고, Pico는 MDD10A를 제어하며 각 바퀴의 엔코더 값을 수집합니다.

<p align="center">
  <img src="../assets/motor-pico-jetson-wiring.png" width="900" alt="모터 전원, MDD10A, Raspberry Pi Pico, 엔코더와 Jetson Orin Nano의 전체 연결 구조도">
</p>

### 제어 핀 요약

| 용도 | Pico 핀 |
| --- | --- |
| MDD10A DIR1 | `GP2` |
| MDD10A PWM1 | `GP3` |
| MDD10A DIR2 | `GP4` |
| MDD10A PWM2 | `GP5` |
| 오른쪽 뒤 엔코더 C1 / C2 | `GP6` / `GP7` |
| 왼쪽 뒤 엔코더 C1 / C2 | `GP14` / `GP9` |
| 오른쪽 앞 엔코더 C1 / C2 | `GP10` / `GP11` |
| 왼쪽 앞 엔코더 C1 / C2 | `GP12` / `GP13` |

## Jetson 전원 연결

Jetson 전원은 4S LiPo 배터리 출력을 DFR0946 DC-DC 컨버터로 19V에 맞춘 뒤 5.5×2.5mm DC 플러그로 공급합니다.

<p align="center">
  <img src="../assets/jetson-power-wiring.png" width="900" alt="4S LiPo 배터리, 퓨즈, DFR0946 DC-DC 컨버터와 Jetson Orin Nano 전원 연결 구조도">
</p>

### 전원 작업 주의사항

- 배선 작업은 반드시 배터리를 분리한 상태에서 진행합니다.
- DC 플러그는 **센터 핀 양극(+), 외곽 음극(-)** 극성을 사용합니다.
- Jetson 연결 전에 멀티미터로 컨버터 출력이 `19.0V`인지 확인합니다.
- 퓨즈는 배터리와 가까운 위치에 두고, 배터리가 연결된 상태에서 DC 플러그를 조립하거나 분해하지 않습니다.
- 전원을 끌 때는 Jetson을 정상 종료한 뒤 LED가 꺼진 것을 확인하고 배터리를 분리합니다.

## IMU 연결

IMU는 I2C로 Pico에 연결합니다. 아래 핀맵은 Pico H의 USB 포트가 위쪽을 향한 상태를 기준으로 합니다.

<p align="center">
  <img src="../assets/imu-pico-wiring.png" width="650" alt="Pico H의 전원, I2C와 인터럽트 핀을 표시한 IMU 연결 구조도">
</p>

| IMU 신호 | Pico H 연결 |
| --- | --- |
| GND | 38번 `GND` |
| 3.3V | 36번 `3V3(OUT)` |
| INT | 34번 `GP28` |
| SCL | 32번 `GP27` |
| SDA | 31번 `GP26` |

사용 중인 IMU 모듈의 실물 모습입니다.

<p align="center">
  <img src="../assets/imu-module.png" width="480" alt="BOMI 프로토타입에서 사용하는 IMU 센서 모듈">
</p>

## 센서 및 돌봄 기능 기준

- 카메라는 일정 시간 이상 누움 자세를 로컬 Vision에서 판정하는 데 사용합니다. 프레임·관절 좌표·얼굴 특징은 중앙 DB로 보내지 않습니다.
- 온습도 센서는 단위가 명확한 `°C`, `%RH` 값을 제공하고 장치 ID·관측시각과 함께 MQTT 이벤트를 만듭니다.
- 초당 원시 측정값은 중앙 DB에 저장하지 않습니다. 최신값과 임계값 초과 또는 의미 있는 변화만 전송합니다.
- 센서 고장, 오래된 관측 또는 안전 조건이 불확실한 경우 로봇은 접근을 강행하지 않고 안전한 기본 동작을 유지합니다.

## 관련 문서

- [Robot 실행 및 하드웨어 제어](../../robot/README.md)
- [IoT 장치 구성](../../iot/README.md)
- [오디오 에코·Barge-in 검증](audio-echo-bargein-verification.md)
