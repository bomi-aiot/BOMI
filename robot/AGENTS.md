# BOMI Robot 작업 지침

이 문서는 `robot/` 아래의 ROS 2 코드, 설정, 실행 파일, 테스트 및 문서를 수정하는 모든 작업에 적용한다.

변경 대상에 더 가까운 `AGENTS.md`가 있으면 함께 적용하며, 충돌할 때는 더 가까운 문서를 우선한다. `robot/ai_vision/` 작업은 해당 디렉터리의 `AGENTS.md`와 그 문서가 지정한 설계 문서를 따른다.

[`CLAUDE.md`](CLAUDE.md)는 Claude 계열 도구를 위한 연결 문서다. 작업 규칙의 원본은 이 문서다.

## 1. 개발 환경과 현재 상태

기본 환경은 Ubuntu 22.04, ROS 2 Humble, Python 3.10이며 `colcon`으로 빌드한다.

주행 관련 구현과 향후 실제 하드웨어 제어는 `robot/ros2_ws/src/core/` 패키지가 담당한다.

| 실행 진입점 | 현재 동작 |
| --- | --- |
| `status_publisher` | `/bomi/status`에 `bomi is ready`를 1초마다 발행 |
| `keyboard_teleop` | 키보드 입력을 `/cmd_vel`의 `geometry_msgs/Twist`로 발행 |
| `mock_motor_driver` | `/cmd_vel`을 구독해 값을 로그로 출력 |
| `joy_cmd_filter` | 조이스틱 입력을 `/cmd_vel` 명령으로 변환 |
| `nav2_waypoint_patrol` | YAML 순찰 지점을 Nav2 `NavigateToPose` 목표로 순서대로 전송 |
| `vision_udp_bridge` | AI 비전의 UDP 추적 결과를 `/vision/follow_result`로 발행 |
| `person_follower` | 추적 결과와 LiDAR 스캔으로 속도 명령 생성, 근접 시 정지 |
| `scan_sanitizer` | 각도 범위가 360°가 아닌 LaserScan을 버리고 나머지를 다시 발행 |

실제 하드웨어 제어는 아직 Mock 단계다. 실제 모터 드라이버, Pico 통신, 하드웨어 YAML 설정, 명령 타임아웃과 비상 정지는 구현되지 않았다. `mock_motor_driver`도 메시지를 기록할 뿐 GPIO나 PWM을 제어하지 않는다.

속도 명령원은 각자 별도 토픽에 발행하고 `twist_mux`가 우선순위로 중재해 최종 `/cmd_vel`을 만든다. 현재 `core/config/twist_mux.yaml`에는 `/cmd_vel_keyboard`와 `/cmd_vel_joy`만 등록되어 있다. `person_follower`의 기본 출력 `/cmd_vel_follow`와 Nav2의 출력은 아직 등록되지 않았으므로, 두 기능을 동시에 실행할 때 어느 명령이 로봇에 전달되는지 확인한 뒤 사용한다.

명령원을 추가하거나 출력 토픽을 바꿀 때는 `/cmd_vel`에 두 개 이상이 동시에 발행되지 않는지 확인한다.

차량 하드웨어는 조립과 모터 구동 확인까지 완료했고 엔코더 값 확인과 IMU 설정이 진행 중이다. Odometry 보정과 실제 드라이버는 아직 남아 있다. 단계별 상태는 `robot/docs/hardware-control.md`를 따른다.

`core/core/__pycache__/`, `ros2_ws/{build,install,log}/`과 별도 테스트에서 생성한 `{build,install,log}_core_test/`는 소스나 현재 기능으로 취급하지 않는다.

## 2. 이동·제어 기준

세부 하드웨어 구성과 진행 상태는 `robot/docs/hardware-control.md`를 따른다.

현재 차량은 JGB37-520 엔코더 모터 4개, MDD10A와 Pico H를 사용하는 차동구동 구조다. MDD10A의 두 채널이 각각 같은 쪽 모터 2개를 구동한다.

`geometry_msgs/Twist`는 표준 의미를 유지한다.

- `linear.x`: 로봇 전후 방향의 목표 선속도
- `angular.z`: 로봇 수직축 기준 목표 각속도

`linear.x`와 `angular.z`는 PWM에 직접 복사하지 않고 좌우 바퀴 목표 속도로 변환하는 순수 로직을 거친다. 차동구동이므로 `linear.x == 0`이고 `angular.z != 0`인 명령은 제자리 회전으로 변환하며, 두 값이 모두 0이면 좌우 모터 출력을 0으로 만든다.

좌우 변환에는 바퀴 지름과 좌우 바퀴 간 거리가 필요하다. 두 값은 아직 측정하지 않았으므로 임시값을 코드에 넣지 않고 설정에서 주입받아 시작 시 검증한다.

현재 `keyboard_teleop`의 속도와 키 매핑은 Mock 검증용이며 실차 보정값이 아니다.

## 3. 안전 및 설계 규칙

실제 하드웨어 제어는 실패 시 정지를 기본값으로 사용한다.

- 시작, 정상 종료, 예외와 초기화 실패 시 좌우 모터 출력을 모두 0으로 만든다.
- 명령 타임아웃과 Pico 통신 끊김에서는 좌우 모터를 모두 정지시킨다.
- `NaN`, 무한대, 타입 오류와 허용 범위를 벗어난 명령은 하드웨어에 전달하지 않는다.
- 전진과 후진을 전환할 때는 정지 구간과 필요한 가감속 제한을 둔다.
- 제자리 회전에도 최대 각속도와 가감속 제한을 적용한다.
- 비상 정지와 정상 종료 정리 코드를 제거하거나 우회하지 않는다.
- 하드웨어 import와 I2C/PWM 초기화를 모듈 import 시점에 강제하지 않는다.
- 하드웨어 접근, 보드별 드라이버, ROS 2 노드, 명령 변환과 안전 정책을 분리해 순수 로직을 하드웨어 없이 테스트할 수 있게 한다.
- AI 비전 코드는 모터를 직접 제어하지 않는다.

## 4. 코드와 패키지 구성

- Python 모듈, 클래스와 공개 함수에는 역할을 설명하는 한국어 docstring을 작성한다.
- 변수, 함수, 클래스와 모듈 이름은 영어로 작성한다.
- 설정값의 단위와 허용 범위를 명시하고 시작 시 검증한다.
- 현재 하드웨어에 필요하지 않은 추상화나 미래 기능을 미리 구현하지 않는다.
- 테스트를 삭제하거나 안전 제한을 약화해 구현을 통과시키지 않는다.

패키지 전용 설정과 launch 파일은 각각 `robot/ros2_ws/src/core/config/`, `robot/ros2_ws/src/core/launch/`에 둔다. ROS 2 노드나 설정을 변경하면 `package.xml`, `setup.py`의 `console_scripts`와 `data_files`, 테스트 및 `robot/README.md`를 실제 구현과 함께 갱신한다.

## 5. 작업과 검증

작업 전에는 다음을 확인한다.

1. 이 문서와 변경 대상에 더 가까운 `AGENTS.md`
2. `robot/README.md`, `robot/ros2_ws/src/core/package.xml`, `robot/ros2_ws/src/core/setup.py`, 관련 코드와 테스트
3. 추적되는 소스와 로컬 생성물, 현재 구현과 계획, 확인된 하드웨어 값과 미확정 값의 구분
4. `robot/docs/hardware-control.md`의 진행 상태와 아직 확정하지 않은 값
5. 기존 안전 정지 경로

현재 `core/test/`에는 패키지 생성 시 만들어진 lint 테스트만 있다. 동작을 변경하거나 기능을 추가하면 외부에서 관찰되는 동작을 검증하는 테스트를 함께 작성한다.

기본 검증 명령은 다음과 같다.

```bash
cd robot/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install
colcon test --packages-select core
colcon test-result --verbose
```

이동·제어 동작을 변경할 때는 작업 범위에 해당하는 항목을 검증한다.

- 전진, 후진, 정지의 부호와 출력 제한
- 모든 키의 `Twist` 매핑과 알 수 없는 키의 정지 명령
- `linear.x`와 `angular.z`에서 좌우 바퀴 목표 속도로의 변환과 각 부호
- `linear.x == 0`이고 `angular.z != 0`인 명령이 제자리 회전으로 변환되며 최대 각속도 제한을 넘지 않음
- `linear.x`와 `angular.z`가 모두 0일 때 좌우 모터 출력이 0
- 명령 타임아웃과 Pico 통신 끊김에서의 안전 정지
- 잘못된 설정과 비정상 명령의 거부
- 종료와 예외 발생 시 하드웨어 출력 해제
- 코드, 패키지 메타데이터, 설정, launch 파일과 README의 일치

구현되지 않은 기능, 확인되지 않은 하드웨어 값이나 미래 계획을 현재 사실처럼 문서화하지 않는다. ROS 2 또는 실제 하드웨어 환경이 없어 검증하지 못한 항목은 실행한 것처럼 보고하지 않고, 소프트웨어 테스트 결과와 구분해 기록한다.
