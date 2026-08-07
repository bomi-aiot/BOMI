# 현관 waypoint 실측과 Nav2 주행 확인 (실기 절차)

로봇 앞에서 명령을 찾느라 시간을 쓰지 않도록, 순서대로 복사해 쓰는 시트다.
목표는 하나다 — **재매핑 → 현관 좌표 실측 → 그 좌표로 실제 주행.**

각 단계에 성공 판정 기준이 있다. 판정을 통과하지 못하면 다음 단계로 넘어가지
않는다. 앞 단계가 틀린 채로 진행하면 마지막에 실패하고 원인을 찾느라 시간을
날린다.

전제: 로봇(Pico + X4-PRO LiDAR)과 조이스틱이 연결돼 있고, 시리얼 포트는
`/dev/ttyACM0`(Pico), `/dev/ttyUSB0`(LiDAR)이다. 다르면 각 명령의 포트 인자를
바꾼다.

## 접속과 화면

작업은 Jetson(`ssafy-desktop`, aarch64)에서 한다. 노트북에서 SSH로 붙는다.

```bash
ssh ssafy@192.168.0.27
```

RViz를 노트북 화면에 띄우려면 `-X`를 붙인다. Jetson이 렌더링하고 화면만
넘어온다 (소프트웨어 렌더링이라 느리지만 동작한다).

```bash
ssh -X ssafy@192.168.0.27
```

> DDS로 노트북에서 rviz2를 직접 돌리는 방식은 **안 된다.** Jetson → 노트북
> 방향이 Windows 방화벽에 막혀 있어(ping 100% 손실) 토픽이 보이지 않는다.
> 굳이 그 방식을 쓰려면 Windows에서 관리자 권한으로 인바운드 UDP
> 7400–7500을 열고, `~/bomi_fastdds_wsl.xml`의 IP를 현재 값으로 고쳐야 한다
> (지금은 옛 네트워크 `192.168.30.x`가 적혀 있다).

```bash
# 모든 터미널에서 먼저 실행
export WS=~/S15P11E102/robot/ros2_ws
cd $WS
source /opt/ros/humble/setup.bash
source install/setup.bash
```

> 워크스페이스가 여럿 있다. `~/S15P11E102-hotfix`는 **팀원이 쓰는 곳이니
> 건드리지 않는다.** 359 작업은 `~/S15P11E102`에서 한다 (359 브랜치 체크아웃
> 및 빌드 완료 상태).

---

## 0. 빌드

```bash
cd $WS
colcon build --packages-select core mapping bomi_lidar bridge
source install/setup.bash
```

**판정:** 에러 없이 완료. 실패하면 여기서 멈춘다.

> Jetson에는 `robot_localization`이 이미 설치돼 있다(확인함). `use_ekf`
> 기본값(true)을 그대로 쓴다. 개발 PC(WSL)에는 없으므로 거기서 Nav2를 돌리려면
> `sudo apt install ros-humble-robot-localization` 또는 `use_ekf:=false`가
> 필요하다.

**시작 전 확인 — 시리얼 포트를 다른 사람이 쓰고 있지 않은지:**

```bash
pgrep -a -f "pico_driver|slam_toolbox|nav2"
```

`pico_driver`가 떠 있으면 `/dev/ttyACM0`이 점유된 상태다. 그대로 매핑을
시작하면 포트 충돌로 실패한다. 팀원에게 확인한 뒤 종료하고 시작한다.

---

## 1. 재매핑

> ⚠️ **이 단계에서 반드시 지킬 것 두 가지.** 지난 지도(`bomi_real_11`)가
> 여기서 실패했다.
>
> 1. **로봇을 충전소에 도킹한 상태로 시작한다.** 그러면 지도 원점이 곧
>    충전소가 되어 `charging` 웨이포인트 `(0, 0, 0)`이 자동으로 맞는다.
> 2. **현관과 소파를 모두 스캔에 포함시킨다.** `bomi_real_11`은 현관 방향을
>    안 찍어서 `entrance`가 미탐색 영역이었고 `sofa`는 지도 밖이었다. 그
>    상태로는 Nav2가 목표를 거부해서 무슨 짓을 해도 주행이 안 된다.

```bash
ros2 launch core joystick_slam_robot.launch.py \
  pico_port:=/dev/ttyACM0 \
  lidar_port:=/dev/ttyUSB0
```

LiDAR 장착 위치(`laser_x`, `laser_z` 등)를 지난번에 실측해 뒀다면 그 값을 같이
넘긴다 — `robot-joystick-slam.md` 참고. WSL에서 RViz가 깨지면 앞에
`LIBGL_ALWAYS_SOFTWARE=1`을 붙인다.

조이스틱으로 **천천히** 공간을 돈다. 빠르면 벽선이 두 겹으로 찍힌다.

**판정:** RViz 지도에서
- 벽선이 한 겹으로 나온다 (두 겹이면 더 천천히 다시)
- **현관 쪽이 회색(미탐색)이 아니다**
- **소파 쪽도 회색이 아니다**

이 세 개를 눈으로 확인한 다음 저장한다.

---

## 2. 지도 저장

```bash
cd $WS
ros2 run nav2_map_server map_saver_cli -f src/mapping/maps/bomi_real_12
```

기존 `bomi_real_11`은 덮지 말고 새 이름으로 남긴다 (비교용).

```bash
colcon build --packages-select mapping && source install/setup.bash
```

**판정:** `src/mapping/maps/bomi_real_12.pgm`과 `.yaml`이 생겼다.

---

## 3. Nav2 실행과 위치 잡기

1단계 launch를 끄고 실행한다.

```bash
ros2 launch core bomi_navigation_real.launch.py \
  map:=$WS/install/mapping/share/mapping/maps/bomi_real_12.yaml \
  pico_port:=/dev/ttyACM0 \
  lidar_port:=/dev/ttyUSB0
```

`robot_localization`이 없으면 `use_ekf:=false`를 추가한다.

RViz가 뜨면 **초기 위치는 사람이 알려줘야 한다** (launch가 자동으로 넣지
않는다):

1. 로봇을 지도에 찍힌 실제 공간에 놓는다 (충전소 자리가 가장 쉽다)
2. RViz 상단 **"2D Pose Estimate"** 클릭
3. 지도에서 로봇이 있는 자리를 클릭하고, 로봇이 보는 방향으로 드래그

**판정:** **LiDAR 점이 지도의 벽선에 겹친다.** 이것이 유일한 기준이다.
어긋나면 2번을 다시 한다. 좁고 네모난 공간에서는 AMCL이 벽을 착각하므로,
구석이나 문 앞처럼 특징이 있는 위치에 로봇을 두고 다시 찍으면 잘 잡힌다.

---

## 4. 좌표 없이 주행부터 확인

RViz 상단 **"Nav2 Goal"** 클릭 → 2m 앞 아무 데나 찍는다. 코드는 필요 없다.

**판정:** 로봇이 실제로 굴러가서 도착한다.

여기가 진짜 관문이다. 통과하면 나머지는 거의 자동으로 된다. 안 되면 아래
"증상별 대처"를 본다.

---

## 5. 현관 좌표 실측

조이스틱으로 로봇을 **현관 앞에, 문을 바라보게** 세운다. 그 자리에서:

```bash
ros2 topic echo /amcl_pose --once
```

출력에서 `position.x`, `position.y`, `orientation.z`, `orientation.w`를 본다.
yaw는 다음으로 계산한다:

```bash
python3 -c "import math; z=<orientation.z>; w=<orientation.w>; print(2*math.atan2(z,w))"
```

`src/core/config/room_waypoints.yaml`의 `entrance` 세 값을 교체한다:

```yaml
  - name: entrance
    x: <측정한 x>
    y: <측정한 y>
    yaw: <계산한 yaw>
```

소파도 같은 방법으로 측정해 `sofa`를 교체한다 — `NAVIGATE(LIVING_ROOM)`이
`sofa`를 가리키므로 보미야 호출·복약·온습도 시나리오가 여기에 달려 있다.

**판정:** 측정한 x, y가 지도의 주행 가능 영역 안이다. 벽에 너무 붙으면
`robot_radius` 때문에 목표가 거부되므로, 벽에서 최소 35cm는 떨어진 지점을
고른다.

---

## 6. 좌표만 따로 확인 (MQTT·백엔드 없이)

`goto_waypoint`는 이름 하나로 그 지점까지 한 번만 주행한다. **Nav2만 떠 있으면
되고 브로커·백엔드·AI는 필요 없다.** 좌표가 틀린 것인지 배선이 틀린 것인지
분리해서 보는 것이 목적이다.

```bash
ros2 run core goto_waypoint --ros-args \
  -p waypoint_name:=entrance \
  -p waypoint_file:=$WS/src/core/config/room_waypoints.yaml
```

`waypoint_file`로 **소스 트리**를 가리키므로 좌표를 고칠 때마다 다시 빌드하지
않아도 된다. 좌표를 바꿔가며 반복할 때 이 인자를 꼭 쓴다.

같은 명령으로 다른 지점도 확인한다 (코드 수정 불필요):

```bash
ros2 run core goto_waypoint --ros-args -p waypoint_name:=charging  -p waypoint_file:=...
ros2 run core goto_waypoint --ros-args -p waypoint_name:=sofa      -p waypoint_file:=...
```

**판정:** `도착: entrance` 로그가 뜨고 프로세스가 스스로 끝난다.

실패하면 이유를 찍고 바로 끝난다 (재시도하지 않는다):

| 로그 | 뜻 |
|---|---|
| `Nav2가 목표를 거부했다...` | 좌표가 미탐색 영역이나 장애물 위다. 5단계로 |
| `주행 실패: status=...` | 목표는 받았으나 도달 못 함. 경로가 막혔거나 파라미터 문제 |
| `Nav2가 30초 안에 활성화되지...` | 3단계 launch가 안 떠 있다 |
| `'xxx' 웨이포인트가 없다. 사용 가능: ...` | 이름 오타 |

---

## 7. 백엔드 명령 경로 확인

6단계가 되면 브릿지를 붙인다.

```bash
ros2 launch bridge mqtt_bridge.launch.py \
  driver_type:=nav2 \
  broker_host:=<브로커 호스트> \
  waypoint_file:=$WS/src/core/config/room_waypoints.yaml
```

> `waypoint_file`을 주지 않으면 **설치본**(`share/core/config`)의 좌표를 읽는다.
> 소스 YAML만 고치고 빌드를 빼먹으면 옛 좌표로 주행하면서도 원인이 로그에
> 드러나지 않는다.

실브로커(`8883`)에 붙을 때는 `use_tls:=true ca_certs:=<경로>`가 함께 필요하다.

백엔드가 `NAVIGATE(ENTRANCE)`를 발행하면 로봇이 현관으로 가고 결과가
`SUCCEEDED/ARRIVED`로 돌아온다.

**판정:** 결과 토픽에 `outcome: SUCCEEDED`, `resultCode: ARRIVED`.

---

## 증상별 대처

| 증상 | 먼저 볼 곳 |
|---|---|
| launch가 바로 죽음 (`robot_localization`) | 0단계 — 설치하거나 `use_ekf:=false` |
| LiDAR 점이 벽선과 안 겹침 | 3단계 2D Pose Estimate 다시. 특징 있는 위치에서 |
| 목표를 거부함 | 좌표가 미탐색/장애물. 5단계 재측정. 그다음 `robot_radius` |
| "경로를 찾을 수 없음" | `nav2_safe_params_real.yaml`의 `robot_radius`(현재 0.31)를 낮춘다 |
| 아예 안 움직임 | `nav2_safe_params_real.yaml` 속도 파라미터 (실측 튜닝 전 초안값) |
| 빙글빙글 돌기만 함 | 3단계 정위치가 실은 안 된 것. 3단계로 복귀 |
| 좌표를 고쳤는데 옛 자리로 감 | `waypoint_file` 인자를 줬는지. 안 줬으면 `colcon build` |
| 지도가 두 겹으로 찍힘 | 1단계 더 천천히. 스캔 위생 노드가 걸러도 속도에는 한계 |

---

## 커밋할 것

- 새 지도: `src/mapping/maps/bomi_real_12.{pgm,yaml}`
- 실측 좌표: `src/core/config/room_waypoints.yaml`
- 튜닝한 파라미터: `src/core/config/nav2_safe_params_real.yaml`

세 개를 따로 커밋하면 나중에 어느 값이 왜 바뀌었는지 추적하기 쉽다.

---

## 참고

- 매핑 상세: `robot-joystick-slam.md`, `handheld-lidar-mapping.md`
- Nav2 문제 해결: `nav2-troubleshooting.md`
- 순찰(여러 지점 순회): `waypoint-patrol.md`
