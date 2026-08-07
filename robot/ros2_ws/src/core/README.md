# 비전 기반 사용자 추종 및 실제 LiDAR 안전 정지 실행 방법

실제 노트북 카메라의 사람 추적 결과와 실제 X4 Pro LiDAR 거리 정보를 이용해
Gazebo 로봇의 전진, 좌회전, 우회전, 정지를 확인한다.

```text
실제 노트북 카메라
→ AI 비전 모델
→ UDP
→ core/vision_udp_bridge
→ /vision/follow_result
→ person_follower
   + 실제 X4 Pro LiDAR /scan_real
→ /cmd_vel
→ Gazebo 로봇
```

> 실제 카메라와 실제 X4 Pro LiDAR를 사용한다.
> 최종 이동은 실제 모터가 아니라 Gazebo 로봇으로 확인한다.
> Gazebo의 가상 LiDAR는 `/scan`, 실제 X4 Pro는 `/scan_real`로 분리한다.

---

## 1. 실행 전 준비

필요한 것:

- Windows 11
- WSL2 Ubuntu 22.04
- ROS 2 Humble
- Git Bash
- X4 Pro LiDAR
- 노트북 카메라
- `usbipd-win`
- Gazebo 및 `ros_gz` 패키지

로컬에서 별도로 생성하는 파일은 아래 하나다.

> 문서의 `Windows사용자이름`은 각 팀원의 실제 Windows 계정명으로 바꾼다.
> `본인_BUSID`도 `usbipd list`에서 확인한 값으로 바꾼다.

```text
C:\Users\Windows사용자이름\Desktop\bomi_local_test\
└── bomi_ai_udp_live.py
```

`vision_udp_bridge.py`를 로컬에 따로 만들지 않는다.

비전 UDP 브리지는 Robot 패키지에 포함된 실행 파일을 사용한다.

```bash
ros2 run core vision_udp_bridge
```

### 사용되는 비전 상태값

```text
not_detected
tracking
temporarily_lost
multiple_pending
multiple_persons
single_recovery
```

### 사용되는 명령값

```text
stop
turn_left
turn_right
move_forward
```

### 비전 JSON 필드

```text
status   : AI 사람 추적 상태
command  : 추종 명령
track_id : 추적 대상 ID. 대상이 명확하지 않으면 null
reason   : 상태 또는 명령이 결정된 이유
```

---

## 2. Robot 브랜치 이동 및 빌드

### 2-1. Robot 브랜치 확인

[Git Bash]

```bash
cd ~/Desktop/bomi-robot
git fetch origin
```

#### MR 검토 중인 경우

```bash
git switch robot/feat/S15P11E102-165-person-following
git status
```

로컬 브랜치가 없으면:

```bash
git switch --track origin/robot/feat/S15P11E102-165-person-following
```

정상 예시:

```text
On branch robot/feat/S15P11E102-165-person-following
nothing to commit, working tree clean
```

#### 기능이 `robot-develop`에 머지된 이후

```bash
git switch robot-develop
git pull origin robot-develop
git status
```

정상 예시:

```text
On branch robot-develop
Your branch is up to date with 'origin/robot-develop'.
nothing to commit, working tree clean
```

### 2-2. Robot 코드 빌드

[Ubuntu]

```bash
cd /mnt/c/Users/Windows사용자이름/Desktop/bomi-robot/robot/ros2_ws

source /opt/ros/humble/setup.bash

colcon build --symlink-install

source install/setup.bash
```

정상 예시:

```text
Summary: ... packages finished
```

실행 파일 확인:

```bash
ros2 pkg executables core |
grep -E "person_follower|vision_udp_bridge"
```

정상:

```text
core person_follower
core vision_udp_bridge
```

### `Package 'core' not found`가 나올 때

```bash
cd /mnt/c/Users/Windows사용자이름/Desktop/bomi-robot/robot/ros2_ws

source /opt/ros/humble/setup.bash
source install/setup.bash
```

그래도 나오면 다시 빌드한다.

```bash
colcon build --symlink-install
source install/setup.bash
```

---

## 3. AI 코드 준비

Robot 코드와 AI 코드를 동시에 사용하기 위해 AI worktree를 사용한다.

### 3-1. AI worktree가 없는 경우

[Git Bash]

```bash
cd ~/Desktop/bomi-robot

git fetch origin ai-develop

git worktree add --detach \
  ~/Desktop/bomi-ai-run \
  origin/ai-develop
```

### 3-2. AI worktree가 이미 있는 경우

먼저 수정 파일이 없는지 확인한다.

```bash
git -C ~/Desktop/bomi-ai-run status --short
```

아무것도 출력되지 않을 때만 최신 `ai-develop`으로 맞춘다.

```bash
cd ~/Desktop/bomi-robot

git fetch origin ai-develop

git -C ~/Desktop/bomi-ai-run \
  checkout --detach origin/ai-develop
```

> `git -C ~/Desktop/bomi-ai-run status --short`에 파일이 출력되면
> 임의로 checkout하지 말고 변경 내용을 먼저 확인한다.

### 3-3. AI 가상환경 실행

```bash
cd ~/Desktop/bomi-ai-run/robot/ai_vision

source venv/Scripts/activate
```

정상 확인:

```bash
python --version

python -c \
  "import cv2; import ultralytics; print('AI 실행 준비 완료')"
```

정상:

```text
AI 실행 준비 완료
```

현재 AI 코드가 로컬 UDP 실행 파일에서 사용하는 API와 맞는지도 확인한다.

```bash
python -c "from bomi_vision.tracking import UserTrackingService; from bomi_vision.follow import FollowCommandGenerator; print('AI API 호환 확인 완료')"
```

정상:

```text
AI API 호환 확인 완료
```

### `venv/Scripts/activate: No such file or directory`가 나올 때

```bash
cd ~/Desktop/bomi-ai-run/robot/ai_vision

python -m venv venv
source venv/Scripts/activate
python -m pip install --upgrade pip
```

AI 폴더에 `requirements.txt`가 있으면 설치한다.

```bash
python -m pip install -r requirements.txt
```

> `requirements.txt`가 없다면 임의로 패키지 버전을 설치하지 말고
> AI 팀에서 사용하는 가상환경 설치 방법을 확인한다.

---

## 4. Gazebo 관련 패키지 확인

[Ubuntu]

```bash
source /opt/ros/humble/setup.bash

ros2 pkg executables ros_gz_sim
ros2 pkg executables ros_gz_bridge
```

### 패키지가 없을 때

```bash
sudo apt update

sudo apt install -y \
  ros-humble-ros-gz-sim \
  ros-humble-ros-gz-bridge
```

설치 후 환경을 다시 적용한다.

```bash
cd /mnt/c/Users/Windows사용자이름/Desktop/bomi-robot/robot/ros2_ws

source /opt/ros/humble/setup.bash
source install/setup.bash
```

---

## 5. X4 Pro LiDAR를 WSL에 연결

LiDAR USB를 노트북에 연결한다.

### 5-1. BUSID 확인

`usbipd`는 Ubuntu 명령이 아니라 Windows 명령이다.

[관리자 PowerShell]

```powershell
usbipd list
```

다음 장치를 찾는다.

```text
CP2102 USB to UART Bridge Controller
```

예시:

```text
BUSID 1-3
STATE Shared
```

### 5-2. 장치 공유

`Not shared`일 때만 실행한다.

```powershell
usbipd bind --busid 본인_BUSID
```

일반 bind가 실패하고 `--force` 사용 안내가 나올 때만:

```powershell
usbipd bind --busid 본인_BUSID --force
```

이미 `Shared`이면 bind를 다시 하지 않는다.

### 5-3. WSL에 연결

Ubuntu 창을 하나 먼저 열어 둔다.

[관리자 PowerShell]

```powershell
usbipd attach --wsl --busid 본인_BUSID
```

> 컴퓨터 재부팅 또는 `wsl --shutdown` 이후에는 attach를 다시 해야 한다.

[Ubuntu]

```bash
ls -l /dev/ttyUSB*
```

정상 예시:

```text
/dev/ttyUSB0
```

### 5-4. 시리얼 포트 권한 확인

```bash
groups
```

출력에 `dialout`이 있으면 정상이다.

없으면:

```bash
sudo usermod -aG dialout $USER
```

그다음 PowerShell에서 WSL을 종료한다.

```powershell
wsl --shutdown
```

Ubuntu를 다시 열고 `usbipd attach`부터 다시 진행한다.

---

## 6. Gazebo 실행

`bomi_sim.launch.py`가 다음 항목을 함께 실행한다.

- Gazebo 월드
- `bomi_robot` 생성
- `/cmd_vel` 브리지
- Gazebo 가상 LiDAR `/scan`
- `/odom`, `/tf`, `/clock` 브리지

따라서 로봇 생성 명령과 별도의 Gazebo 브리지를 추가로 실행하지 않는다.

[Ubuntu 창 1]

```bash
cd /mnt/c/Users/Windows사용자이름/Desktop/bomi-robot/robot/ros2_ws

source /opt/ros/humble/setup.bash
source install/setup.bash

unset GALLIUM_DRIVER
unset QT_QUICK_BACKEND
unset QT_OPENGL

export LIBGL_ALWAYS_SOFTWARE=1

ros2 launch simulation bomi_sim.launch.py
```

정상:

- Gazebo 창이 유지된다.
- `bomi_robot`이 나타난다.
- 월드의 바닥과 장애물이 보인다.
- 화면이 심하게 깜빡이지 않는다.

> 이 환경에서는 `LIBGL_ALWAYS_SOFTWARE=1`을 사용해 Gazebo를 실행했다.
> `ign gazebo`로 월드만 직접 열면 로봇과 브리지가 자동으로 실행되지 않는다.

---

## 7. 실제 X4 Pro LiDAR를 `/scan_real`로 실행

Gazebo 가상 LiDAR가 이미 `/scan`을 사용하므로
실제 X4 Pro는 `/scan_real`로 remap한다.

[Ubuntu 창 2]

```bash
cd /mnt/c/Users/Windows사용자이름/Desktop/bomi-robot/robot/ros2_ws

source /opt/ros/humble/setup.bash
source install/setup.bash

ros2 run ydlidar_ros2_driver ydlidar_ros2_driver_node \
  --ros-args \
  --params-file src/bomi_lidar/config/x4_pro.yaml \
  -p port:=/dev/ttyUSB0 \
  -r /scan:=/scan_real
```

정상 로그 예시:

```text
Lidar successfully connected [/dev/ttyUSB0:128000]
Lidar running correctly! The health status good
Lidar has started!
```

다음 경고가 반복되더라도 `/scan_real`이 정상 발행되면 테스트를 진행할 수 있다.

```text
Real points 441 > fixed points 440
```

### 7-1. 실제 LiDAR 주기 확인

[새 Ubuntu 창]

```bash
cd /mnt/c/Users/Windows사용자이름/Desktop/bomi-robot/robot/ros2_ws

source /opt/ros/humble/setup.bash
source install/setup.bash

ros2 topic hz /scan_real
```

정상 예시:

```text
average rate: 약 10~12 Hz
```

확인 후 `Ctrl+C`로 `hz` 명령만 종료한다.

### 7-2. 실제 LiDAR Publisher 확인

```bash
ros2 topic info /scan_real -v
```

정상:

```text
Publisher count: 1
Node name: ydlidar_ros2_driver_node
```

`person_follower` 실행 전에는 다음도 정상이다.

```text
Subscription count: 0
```

### 토픽 구분

```text
Gazebo 가상 LiDAR → /scan
실제 X4 Pro       → /scan_real
```

`person_follower`는 `/scan_real`만 사용한다.

---

## 8. 로컬 카메라 AI 실행 파일 생성

아래 명령은 최초 생성할 때 실행한다. README의 생성 코드가 변경됐거나 기존 파일이 구형이면 다시 실행한다.

> `cat >` 명령은 기존 `bomi_ai_udp_live.py`가 있어도 최신 내용으로 덮어쓴다.

[Git Bash]

```bash
mkdir -p ~/Desktop/bomi_local_test
```

### 8-1. `bomi_ai_udp_live.py` 생성

```bash
cat > ~/Desktop/bomi_local_test/bomi_ai_udp_live.py <<'PY'
#!/usr/bin/env python3

import json
import os
import socket

from bomi_vision.adapters.opencv import (
    OpenCVCamera,
    OpenCVDebugView,
)
from bomi_vision.adapters.tracking import (
    UltralyticsByteTracker,
)
from bomi_vision.follow import FollowCommandGenerator
from bomi_vision.main import build_parser
from bomi_vision.tracking import UserTrackingService


UDP_HOST = os.environ.get("BOMI_WSL_IP", "")
UDP_PORT = int(
    os.environ.get(
        "BOMI_VISION_UDP_PORT",
        "5005",
    )
)


def main() -> int:
    args = build_parser().parse_args()

    if not UDP_HOST:
        raise SystemExit(
            "BOMI_WSL_IP 환경 변수를 설정하세요."
        )

    tracker = UltralyticsByteTracker(
        args.model,
        args.confidence,
        args.tracker,
    )

    tracking_service = UserTrackingService(
        lost_tolerance_frames=(
            args.lost_tolerance_frames
        ),
        multiple_confirm_frames=(
            args.multiple_confirm_frames
        ),
        single_recovery_frames=(
            args.single_recovery_frames
        ),
    )

    follow_command_generator = FollowCommandGenerator(
        args.horizontal_dead_zone,
        args.forward_threshold,
    )

    camera = OpenCVCamera(args.camera)
    view = OpenCVDebugView()

    udp_socket = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM,
    )

    previous_payload = None

    print(
        "AI 결과 UDP 송신 시작: "
        f"{UDP_HOST}:{UDP_PORT}"
    )

    try:
        while True:
            frame = camera.read()
            tracked_people = tracker.track(frame)

            frame_height, frame_width = frame.shape[:2]

            tracking_result = tracking_service.update(
                tracked_people,
                frame_width=frame_width,
                frame_height=frame_height,
            )

            follow_result = (
                follow_command_generator.generate(
                    tracking_result
                )
            )

            payload = {
                "status": (
                    tracking_result.status.value
                ),
                "command": (
                    follow_result.command.value
                ),
                "track_id": follow_result.track_id,
                "reason": follow_result.reason,
            }

            message = json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")

            udp_socket.sendto(
                message,
                (UDP_HOST, UDP_PORT),
            )

            if payload != previous_payload:
                print(payload)
                previous_payload = payload

            if not view.show(
                frame,
                tracked_people,
                tracking_result,
                follow_result,
            ):
                break

    finally:
        udp_socket.close()
        camera.release()
        view.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
PY
```

### 8-2. 생성 및 문법 확인

```bash
ls -l ~/Desktop/bomi_local_test/bomi_ai_udp_live.py

cd ~/Desktop/bomi-ai-run/robot/ai_vision
source venv/Scripts/activate

python -m py_compile \
  ~/Desktop/bomi_local_test/bomi_ai_udp_live.py

python ~/Desktop/bomi_local_test/bomi_ai_udp_live.py --help
```

두 명령에서 오류가 없고 `--help` 사용법이 출력되면, 문법·import·현재 AI 인자 호환까지 정상이다.

---

## 9. Robot 비전 UDP 브리지 실행

로컬 `vision_udp_bridge.py` 파일을 만들지 않는다.

[Ubuntu 창 3]

```bash
cd /mnt/c/Users/Windows사용자이름/Desktop/bomi-robot/robot/ros2_ws

source /opt/ros/humble/setup.bash
source install/setup.bash

ros2 run core vision_udp_bridge
```

정상 예시:

```text
비전 UDP 브리지를 시작했습니다.
수신=0.0.0.0:5005
ROS2 출력=/vision/follow_result
```

이 창은 종료하지 않는다.

---

## 10. 사람 추종 노드 실행

실제 LiDAR 토픽 `/scan_real`을 사용한다.

[Ubuntu 창 4]

```bash
cd /mnt/c/Users/Windows사용자이름/Desktop/bomi-robot/robot/ros2_ws

source /opt/ros/humble/setup.bash
source install/setup.bash

ros2 run core person_follower \
  --ros-args \
  --params-file src/core/config/person_following.yaml \
  -p use_lidar:=true \
  -p require_lidar_before_motion:=true \
  -p scan_topic:=/scan_real \
  -p output_topic:=/cmd_vel
```

정상 예시:

```text
사람 추종 노드를 시작했습니다.
비전 입력=/vision/follow_result
LiDAR 입력=/scan_real
속도 출력=/cmd_vel
```

`person_follower` 실행 후 확인:

```bash
ros2 topic info /scan_real -v
```

정상:

```text
Publisher count: 1
Subscription count: 1
```

---

## 11. 카메라 AI 실행

[Git Bash]

```bash
cd ~/Desktop/bomi-ai-run/robot/ai_vision

source venv/Scripts/activate
```

WSL IP 설정:

```bash
export BOMI_WSL_IP=$(
  wsl.exe hostname -I |
  tr -d '\r' |
  awk '{print $1}'
)

echo "WSL IP = $BOMI_WSL_IP"
```

실행:

```bash
python ~/Desktop/bomi_local_test/bomi_ai_udp_live.py \
  --model yolo11n.pt \
  --camera 0 \
  --confidence 0.5
```

카메라가 열리지 않으면 종료 후 카메라 번호를 바꾼다.

```bash
python ~/Desktop/bomi_local_test/bomi_ai_udp_live.py \
  --model yolo11n.pt \
  --camera 1 \
  --confidence 0.5
```

정상:

- 노트북 카메라 창이 열린다.
- 사람 감지 박스가 나타난다.
- 상태와 명령이 JSON 형태로 출력된다.

예시:

```text
{
  'status': 'tracking',
  'command': 'stop',
  'track_id': 24,
  'reason': 'safe_follow_distance_reached'
}
```

---

## 12. 토픽 확인

### 12-1. 비전 결과 확인

[새 Ubuntu 창]

```bash
cd /mnt/c/Users/Windows사용자이름/Desktop/bomi-robot/robot/ros2_ws

source /opt/ros/humble/setup.bash
source install/setup.bash

ros2 topic echo /vision/follow_result
```

정상 예시:

```text
data: '{"status":"tracking","command":"stop","track_id":24,"reason":"safe_follow_distance_reached"}'
```

### 12-2. 최종 속도 확인

[새 Ubuntu 창]

```bash
cd /mnt/c/Users/Windows사용자이름/Desktop/bomi-robot/robot/ros2_ws

source /opt/ros/humble/setup.bash
source install/setup.bash

ros2 topic echo /cmd_vel
```

판정 기준:

```text
turn_left 또는 turn_right
→ angular.z가 0이 아님

move_forward
→ linear.x가 0보다 큼

stop
→ linear.x와 angular.z가 모두 0
```

---

## 13. 최종 동작 확인

### 13-1. 사람 없음

카메라에서 사람이 보이지 않게 한다.

정상:

- AI 명령이 `stop`
- `/cmd_vel`의 `linear.x`, `angular.z`가 모두 `0.0`
- Gazebo 로봇이 정지

상태는 상황에 따라 다음 중 하나일 수 있다.

```text
temporarily_lost
not_detected
```

### 13-2. 한 명 좌우 회전

카메라 기준 왼쪽과 오른쪽으로 이동한다.

정상:

- `turn_left`, `turn_right`가 출력됨
- Gazebo 로봇이 서로 반대 방향으로 회전함

### 13-3. 한 명 전진

카메라 중앙에서 멀리 선다.

정상 예시:

```text
AI:
status=tracking
command=move_forward

/cmd_vel:
linear.x: 0.15
angular.z: 0.0
```

Gazebo 로봇이 전진하면 정상이다.

### 13-4. 두 명 감지 시 정지

1. 한 명만 보이게 해서 추종 상태를 만든다.
2. 카메라에 두 명 이상이 보이게 한다.

기대 순서:

```text
multiple_pending
→ multiple_persons
```

`multiple_pending`부터 즉시 정지해야 한다.

```text
linear.x: 0.0
angular.z: 0.0
```

### 13-5. 두 명에서 다시 한 명으로 복구

1. `multiple_persons` 상태를 유지한다.
2. 다시 한 명만 화면에 남긴다.

기대 순서:

```text
single_recovery
→ tracking
→ 같은 Track ID 확인
→ 추종 재개
```

정상 동작:

- `single_recovery` 동안 계속 정지
- 한 명이 보였다고 즉시 움직이지 않음
- 같은 Track ID가 복구 시간 동안 유지된 뒤 약 1초 후 이동 재개

### 13-6. 실제 LiDAR 장애물 안전 정지

1. 카메라에서 AI가 `move_forward`를 출력하도록 한다.
2. 실제 X4 Pro LiDAR 정면에 장애물이 없을 때 Gazebo 로봇이 전진하는지 확인한다.
3. LiDAR 정면을 넓게 가리거나 가까운 장애물을 둔다.

정상:

```text
AI 명령:
move_forward

최종 /cmd_vel:
linear.x: 0.0
angular.z: 0.0
```

즉, 카메라는 직진 명령을 보내더라도 실제 LiDAR가 가까운 장애물을 감지하면 Gazebo 로봇은 정지해야 한다.

### `/cmd_vel`은 나오지만 Gazebo 로봇이 움직이지 않을 때

```bash
ros2 topic info /cmd_vel -v
```

정상:

- Publisher에 `person_follower`
- Subscriber에 Gazebo 브리지

Subscriber가 없으면 Gazebo launch가 정상 실행 중인지 확인한다.

---

## 14. core 테스트

[Ubuntu]

```bash
cd /mnt/c/Users/Windows사용자이름/Desktop/bomi-robot/robot/ros2_ws

source /opt/ros/humble/setup.bash
source install/setup.bash

PYTHONPATH=$PWD/src/core:$PYTHONPATH python3 -m pytest \
  src/core/test/test_follow_state_machine.py \
  src/core/test/test_person_following_controller.py \
  src/core/test/test_person_follower.py \
  -v
```

검증 당시 정상 결과:

```text
42 passed
```

추가로 ROS2 패키지 테스트를 실행할 수 있다.

```bash
colcon test --packages-select core

colcon test-result \
  --verbose \
  --test-result-base build/core
```

정상 기준:

```text
0 errors
0 failures
```

`SelectableGroups dict interface is deprecated`는 경고이며 테스트 실패가 아니다.

---

## 15. 다음 실행부터의 짧은 순서

```text
1. 관리자 PowerShell에서 X4 Pro BUSID 확인
2. usbipd attach --wsl 실행
3. Ubuntu에서 /dev/ttyUSB0 확인
4. LIBGL_ALWAYS_SOFTWARE=1 설정 후 bomi_sim.launch.py 실행
5. 실제 X4 Pro를 /scan_real로 실행
6. /scan_real 주기와 Publisher 확인
7. ros2 run core vision_udp_bridge 실행
8. person_follower를 scan_topic=/scan_real로 실행
9. Git Bash에서 WSL IP 설정
10. bomi_ai_udp_live.py 실행
11. /vision/follow_result와 /cmd_vel 확인
12. 한 명, 두 명, 복구, LiDAR 장애물 정지 확인
```

작업 종료 시 각 실행 창에서 `Ctrl+C`를 누른다.

LiDAR를 WSL에서 분리할 때:

[관리자 PowerShell]

```powershell
usbipd detach --busid 본인_BUSID
```

정상:

```text
Attached → Shared
```

---

## 16. 최종 성공 체크리스트

```text
[ ] Robot 브랜치 확인
[ ] Robot 코드 빌드 성공
[ ] core person_follower 실행 파일 확인
[ ] core vision_udp_bridge 실행 파일 확인
[ ] AI worktree 최신 상태 확인
[ ] AI 가상환경 실행
[ ] bomi_local_test/bomi_ai_udp_live.py 생성
[ ] X4 Pro가 WSL에 연결됨
[ ] /dev/ttyUSB0 존재
[ ] Gazebo와 bomi_robot 정상 실행
[ ] Gazebo 가상 LiDAR가 /scan으로 존재
[ ] 실제 X4 Pro가 /scan_real로 약 10~12 Hz 출력
[ ] /scan_real Publisher가 ydlidar_ros2_driver_node 하나
[ ] vision_udp_bridge 실행
[ ] /vision/follow_result에 status, command, track_id, reason 출력
[ ] person_follower가 /scan_real 구독
[ ] 왼쪽·오른쪽 회전 확인
[ ] 한 명 전진 확인
[ ] 사람 없음 즉시 정지 확인
[ ] 두 명 감지 시 multiple_pending부터 즉시 정지 확인
[ ] multiple_persons 정지 유지 확인
[ ] single_recovery 동안 정지 확인
[ ] 같은 Track ID 확인 후 약 1초 뒤 추종 재개
[ ] AI가 move_forward여도 실제 LiDAR 장애물에서 정지
[ ] core pytest 42개 통과
[ ] 필요 시 colcon test 추가 확인
```

위 항목이 확인되면 다음 연결이 정상이다.

```text
실제 카메라 AI
→ UDP
→ core vision_udp_bridge
→ 사람 추종 상태 머신
→ 실제 X4 Pro LiDAR 안전 제어
→ /cmd_vel
→ Gazebo 로봇 이동
```

---

## 17. 이번 검증 범위

이번에 직접 확인한 항목:

- 카메라에서 한 명 인식 및 추종
- 왼쪽·오른쪽 회전
- 중앙의 먼 사람을 향한 전진
- 사람 없음 시 정지
- 두 명 감지 시 즉시 정지
- 두 명에서 한 명으로 돌아온 뒤 즉시 움직이지 않고 약 1초 후 재개
- 실제 X4 Pro `/scan_real` 약 11 Hz 발행
- 실제 LiDAR 장애물 감지 시 AI 직진 명령보다 안전 정지 우선
- Gazebo 로봇 이동
- 관련 pytest 42개 통과

이번 검증에 포함하지 않은 항목:

- 실제 모터 구동
- 카메라 AI 프로세스 강제 종료 시 타임아웃 정지
- LiDAR 노드 강제 종료 시 타임아웃 정지

# ROS2 Ubuntu 설치 및 조이스틱 연결 설치방법

관리자 파워셀
wsl --install -d Ubuntu-22.04

재부팅

Ubuntu 다운로드 후 사용할 사용자 이름과 비번 작성(영문)

일반 파워셀
wsl.exe -l -v 로 버전 확인

NAME            STATE           VERSION
Ubuntu-22.04    Running         2
가 나오면 정상

Ubuntu 열고
sudo apt update
(이후 비밀번호 작성)

 ROS2 설치 위해서
Ubuntu 창에 작성
sudo apt install -y locales software-properties-common curl

이후
sudo locale-gen en_US en_US.UTF-8

sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
작성

export LANG=en_US.UTF-8

locale

화면에서 이거 아래 내용 보이면 성공
LANG=en_US.UTF-8
LC_ALL=en_US.UTF-8

이후
sudo add-apt-repository universe
작성후 엔터 치기

sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg


echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

sudo apt update

ROS 2 Humble 설치

sudo apt install -y ros-humble-desktop

echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc

source ~/.bashrc

ros2 --help

터틀심과 프로젝드 빌드 도구 설치
sudo apt install -y ros-humble-turtlesim python3-colcon-common-extensions

거부기 나오는지 확인
ros2 run turtlesim turtlesim_node


코드로 움직이는지 확인
코드 있는곳 까지 이동

패키지 설정
sudo apt install -y ros-humble-joy ros-humble-teleop-twist-joy

설치후 코드 빌드
colcon build --symlink-install

ros2 launch core joystick_teleop.launch.py --show-args

응답 이렇게 나오면 됨.
Arguments (pass arguments as '<name>:=<value>'):

    'cmd_vel_topic':
        조이스틱 속도 명령을 보낼 토픽
        (default: '/cmd_vel')


조이스틱 연결
USB 연결하기

관리자 파워셀
winget install --interactive --exact dorssel.usbipd-win
usbipd list
usbipd bind --busid 1-3 --force
usbipd list(Shared 확인)
재부팅




============================================================
Xbox 360 조이스틱 연결부터 최종 작동 확인까지
============================================================

※ 아래 단계는 위의 ROS2 Humble, TurtleSim, colcon 설치가 끝난 뒤 진행하기.
※ 명령어 위에 표시된 창 꼭 확인하기.
   - [관리자 PowerShell] : Windows에서 관리자 권한으로 실행한 PowerShell
   - [일반 PowerShell]   : Windows에서 일반 실행한 PowerShell
   - [Ubuntu]           : Ubuntu 22.04(WSL) 창
※ BUSID는 노트북마다 다름. 예시의 1-3을 무조건 쓰지 말고,
   반드시 본인 usbipd list 결과에 나온 Xbox 장치 BUSID 사용하기.


------------------------------------------------------------
1. Xbox 컨트롤러와 USB 리시버 준비
------------------------------------------------------------

1) Xbox 360 무선 컨트롤러라면 USB 무선 리시버를 노트북에 꽂기.
2) 컨트롤러 전원 켜기.
3) 리시버와 컨트롤러의 연결 버튼을 눌러 페어링하기.

정상:
- 컨트롤러의 초록색 불이 한 위치에 고정되면 정상.
- Windows의 장치 관리자 또는 usbipd list에
  Xbox 360 Controller, Xbox 360 Wireless Receiver 등 Xbox 장치가 보이면 정상.

정상이 아닐 때:
- 불이 계속 회전하면 아직 컨트롤러와 리시버가 페어링되지 않은 거야.
- USB를 뽑았다가 다른 USB 포트에 다시 꽂기.
- 배터리를 확인하고 다시 페어링하기.
- 장치 관리자에 노란 느낌표가 있다면 해당 장치를 제거하지 말고
  먼저 Windows 업데이트와 선택적 드라이버 업데이트를 확인하기.


------------------------------------------------------------
2. WSL 버전과 업데이트 확인
------------------------------------------------------------

[일반 PowerShell]

wsl.exe -l -v

정상 예시:

NAME            STATE           VERSION
Ubuntu-22.04    Running         2

정상이 아닐 때:

1) VERSION이 1이면 아래 명령을 실행하기.

wsl --set-version Ubuntu-22.04 2

2) Ubuntu-22.04가 목록에 없으면 위쪽의 WSL 설치 단계부터 다시 확인하기.

3) WSL을 최신 상태로 업데이트하기.

wsl --update

업데이트 후 필요하면 WSL을 종료하고 다시 실행하기.

wsl --shutdown

그다음 Ubuntu 22.04를 다시 열기.


------------------------------------------------------------
3. usbipd-win 설치 확인
------------------------------------------------------------

[관리자 PowerShell]

usbipd --version

정상:
- 버전 번호가 나오면 정상.

명령어를 찾을 수 없다고 나오면 설치하기.

winget install --interactive --exact dorssel.usbipd-win

설치 도중 Microsoft Store 약관 동의가 나오면 Y를 입력하고 Enter를 누르기.

설치가 끝나면:
1) 현재 PowerShell 창을 완전히 닫기.
2) PowerShell을 다시 관리자 권한으로 열기.
3) 다시 확인하기.

usbipd --version

그래도 명령어를 찾지 못하면 아래 경로로 직접 실행해 확인하기.

& "C:\Program Files\usbipd-win\usbipd.exe" --version


------------------------------------------------------------
4. Xbox 장치의 BUSID 확인
------------------------------------------------------------

[관리자 PowerShell]

usbipd list

정상 예시:

BUSID  VID:PID    DEVICE                 STATE
1-3    ....:....  Xbox 360 Controller   Not shared

여기서 Xbox 장치가 있는 행의 BUSID를 적어두기.
이후 설명에서는 예시로 1-3을 사용하지만 실제로는 본인의 번호를 넣기.

Xbox 장치가 아예 안 보일 때:
1) 리시버를 뽑았다가 다시 꽂기.
2) 다른 USB 포트에 꽂기.
3) 컨트롤러 전원 켜기.
4) 다시 실행하기.

usbipd list

5) 그래도 없으면 Windows 장치 관리자에서 Xbox 장치가 보이는지 확인하기.
   Windows에서도 안 보이면 ROS나 WSL 문제가 아니라 USB·리시버·Windows
   드라이버 문제부터 해결해야 함.


------------------------------------------------------------
5. Xbox USB 장치를 WSL과 공유(bind)
------------------------------------------------------------

※ 이 단계는 관리자 PowerShell에서 실행해야 함.

[관리자 PowerShell]

usbipd bind --busid 1-3

정상:
- 오류 없이 명령이 끝나면 정상.
- 아래 명령으로 확인했을 때 STATE가 Shared로 바뀌면 정상.

usbipd list

정상 예시:

1-3  Xbox 360 Controller  Shared

일반 bind에서 장치 드라이버 충돌 경고가 나오고 --force를 사용하라고 할 때만:

usbipd bind --busid 1-3 --force

그다음 다시 확인하기.

usbipd list

정상 예시:

1-3  Xbox 360 Controller  Shared (forced)

주의:
- --force는 일반 bind가 실패하고 화면에서 요구할 때만 사용하기.
- 재부팅이 필요하다는 문구가 나오면 컴퓨터를 재부팅하기.
- Shared는 공유 준비가 끝난 상태이고, 아직 WSL에 연결된 상태는 아님.


------------------------------------------------------------
6. Xbox USB 장치를 WSL에 연결(attach)
------------------------------------------------------------

1) Ubuntu 22.04 창을 먼저 열어 두기.
2) PowerShell에서 attach를 실행하기.

[일반 PowerShell 또는 관리자 PowerShell]

usbipd attach --wsl --busid 1-3

정상:
- 오류 없이 완료되거나 Successfully attached와 비슷한 내용이 나오면 정상.
- usbipd list에서 STATE가 Attached로 표시됨.

usbipd list

중요:
- attach된 동안 해당 USB 장치는 Windows에서 사용이 안 될 수도 있음.
- 컴퓨터를 재부팅하거나 리시버를 뽑으면 attach가 풀릴 수 있음.
- 다음에 사용할 때는 bind를 매번 다시 할 필요는 없지만,
  attach는 다시 실행해야 할 수 있음.


------------------------------------------------------------
7. attach가 실패할 때 해결
------------------------------------------------------------

A. "There are no WSL 2 distributions running"이 나올 때

1) Ubuntu 22.04를 먼저 실행하기.
2) Ubuntu 입력창이 보이는 상태에서 다시 실행하기.

usbipd attach --wsl --busid 1-3


B. "device is in an error state"가 나올 때

[관리자 PowerShell]

usbipd unbind --busid 1-3

1) Xbox USB 리시버를 노트북에서 뽑기.
2) 5초 정도 기다리기.
3) 다시 꽂기.
4) BUSID가 바뀌었을 수 있으므로 다시 확인하기.

usbipd list

5) 새로 확인한 BUSID로 다시 공유하기.

usbipd bind --busid 새_BUSID --force

6) Ubuntu를 열어 둔 상태에서 다시 연결하기.

usbipd attach --wsl --busid 새_BUSID


C. "Device is already attached"가 나올 때

이미 연결된 상태일 수 있음. Ubuntu에서 lsusb 확인 단계로 넘어가기.


D. "No device found for busid"가 나올 때

리시버를 다시 꽂으면서 BUSID가 바뀐 거야.

usbipd list

새 BUSID를 확인하고 명령어의 번호를 바꿔 다시 실행하기.


E. 계속 실패할 때 WSL 초기화

[일반 PowerShell]

wsl --shutdown
wsl --update

Ubuntu를 다시 연 뒤 attach를 다시 실행하기.

usbipd attach --wsl --busid 본인_BUSID


------------------------------------------------------------
8. Ubuntu에서 USB 장치 자체가 넘어왔는지 확인
------------------------------------------------------------

[Ubuntu]

먼저 USB 목록 확인 프로그램을 설치하기.

sudo apt update
sudo apt install -y usbutils

확인:

lsusb

정상:
- Xbox, Microsoft, Xbox 360 Wireless Receiver와 관련된 행이 보이면 정상.

정상이 아닐 때:
- PowerShell에서 usbipd list를 다시 확인하기.
- STATE가 Shared뿐이면 attach가 아직 안 된 거야.
- STATE가 Attached인지 확인하고 attach 단계부터 다시 진행하기.

중요:
- lsusb에 보인다는 것은 USB가 WSL까지 전달됐다는 뜻임.
- 이것만으로 아직 조이스틱 입력 장치가 생성됐다고 확정할 수는 없음.


------------------------------------------------------------
9. xpad 커널 드라이버 확인
------------------------------------------------------------

xpad는 일반 앱이 아니라 Xbox 컨트롤러용 리눅스 커널 드라이버다.
무조건 별도 프로그램을 설치하는 것이 아니라 먼저 현재 WSL에 있는지 확인하기.

[Ubuntu]

sudo modprobe xpad

정상:
- 아무 문구 없이 입력창으로 돌아오면 정상.

드라이버가 올라왔는지 확인:

lsmod | grep xpad

정상 예시:

xpad ...

정상이 아닐 때:

A. modprobe: FATAL: Module xpad not found가 나올 때

1) Windows PowerShell에서 WSL을 업데이트하기.

[일반 PowerShell]

wsl --update
wsl --shutdown

2) Ubuntu를 다시 열고 USB를 다시 attach하기.
3) Ubuntu에서 다시 실행하기.

sudo modprobe xpad

B. 업데이트 후에도 xpad 모듈이 없을 때

아래 도구를 설치하기.

[Ubuntu]

sudo apt update
sudo apt install -y git dkms build-essential linux-headers-generic joystick

그다음 xpad 드라이버 설치가 필요함.
단, 팀에서 사용한 xpad 설치 저장소 또는 스크립트가 정해져 있다면
반드시 같은 저장소와 버전을 사용하기. 임의의 Xbox One용 xone/xpadneo
드라이버를 Xbox 360 리시버에 설치하면 맞지 않을 수 있음.

※ 이 경우에는 화면의 uname -r 결과와 modprobe 오류를 확인한 후
   팀에서 검증한 xpad 설치 방법을 적용하는 것이 안전하다.

uname -r
sudo modprobe xpad


------------------------------------------------------------
10. /dev/input 장치 확인
------------------------------------------------------------

[Ubuntu]

ls -l /dev/input/

정상:
- event0, event1 등의 장치가 보이면 정상.
- 조이스틱 드라이버까지 정상이라면 js0도 보일 수 있음.

조이스틱 장치만 확인:

ls -l /dev/input/js* 2>/dev/null

정상 예시:

/dev/input/js0

아무것도 안 나올 때:

1) lsusb에 Xbox 장치가 보이는지 다시 확인하기.
2) xpad가 올라왔는지 확인하기.

lsmod | grep xpad

3) 최근 커널 메시지에서 Xbox 또는 xpad 오류를 확인하기.

sudo dmesg | tail -n 50

4) /dev/input/event 장치라도 생겼는지 확인하기.

ls -l /dev/input/event* 2>/dev/null

판단:
- lsusb에도 없음 → usbipd attach 문제
- lsusb에는 있음, xpad 없음 → xpad 드라이버 문제
- xpad 있음, js0 없음 → 드라이버 인식 또는 권한 문제
- js0 있음 → 다음 입력 테스트로 다음 단계로 넘어가기.


------------------------------------------------------------
11. jstest 설치 및 실제 버튼·스틱 입력 확인
------------------------------------------------------------

[Ubuntu]

sudo apt install -y joystick

실행:

jstest /dev/input/js0

정상:
- Axes와 Buttons 숫자가 화면에 나오면 정상.
- 스틱을 움직이면 축 숫자가 변하면 정상.
- 버튼을 누르면 off가 on으로 바뀌거나 값이 변하면 정상.

종료:

Ctrl + C

"No such file or directory"가 나오면:
- /dev/input/js0가 아직 생기지 않은 거야.
- 8~10단계로 돌아가 lsusb, xpad, js0 순서로 다시 확인하기.

"Permission denied"가 나오면 임시로 확인:

sudo jstest /dev/input/js0

sudo에서는 되는데 일반 jstest에서는 안 될 때:

sudo usermod -aG input $USER

그다음 Ubuntu 창을 모두 닫고 다시 열기.
그래도 권한이 반영되지 않으면 Windows PowerShell에서:

wsl --shutdown

Ubuntu를 다시 열고 USB attach부터 다시 진행하기.


------------------------------------------------------------
12. ROS2 joy_node 설치 확인
------------------------------------------------------------

[Ubuntu]

sudo apt install -y ros-humble-joy ros-humble-teleop-twist-joy

설치 확인:

ros2 pkg executables joy

정상:
- joy joy_node와 비슷한 실행 파일이 나오면 정상.

아무것도 나오지 않거나 package not found가 나오면:

source /opt/ros/humble/setup.bash

다시 확인:

ros2 pkg executables joy

그래도 없으면 다시 설치하기.

sudo apt update
sudo apt install -y ros-humble-joy ros-humble-teleop-twist-joy


------------------------------------------------------------
13. joy_node만 실행해서 ROS2 조이스틱 데이터 확인
------------------------------------------------------------

※ jstest가 정상인 것을 확인한 뒤 진행하기.

[Ubuntu 창 1]

source /opt/ros/humble/setup.bash
ros2 run joy joy_node --ros-args -p device_id:=0

정상:
- 창이 계속 실행 중인 상태가 됨.
- 오류 없이 조이스틱 입력을 기다리기.

"Couldn't open joystick /dev/input/js0"가 나오면:
- js0가 없거나 권한이 없는 거야.
- jstest 단계부터 다시 확인하기.

[Ubuntu 창 2]

source /opt/ros/humble/setup.bash
ros2 topic list

정상:
- /joy 토픽이 보이면 정상.

실제 데이터 확인:

ros2 topic echo /joy

정상:
- 스틱이나 버튼을 누를 때 axes와 buttons 값이 계속 출력됨.

아무것도 출력되지 않을 때:
- 컨트롤러 전원이 켜져 있는지 확인하기.
- jstest가 정상인지 다시 확인하기.
- Ubuntu 창 1의 joy_node 오류 내용을 확인하기.

테스트 종료:
- 각 Ubuntu 창에서 Ctrl + C


------------------------------------------------------------
14. 프로젝트 브랜치와 코드 위치 확인
------------------------------------------------------------

※ Git 브랜치 변경은 Git Bash에서 진행해도 되고 Ubuntu에서 진행해도 됨.
※ Git Bash와 Ubuntu가 같은 S15P11E102 폴더를 보고 있으면
   한쪽에서 브랜치를 바꾼 결과가 다른 쪽에도 바로 반영됨.

[Git Bash 또는 Ubuntu]

프로젝트 최상위 폴더로 이동한 뒤:

git status
git branch --show-current

정상:
- working tree clean
- 현재 사용할 조이스틱 브랜치 이름이 나오면 정상.

사용할 브랜치 예시:

robot/feat/S15P11E102-55-joystick-control

다른 브랜치라면:

git switch robot/feat/S15P11E102-55-joystick-control

브랜치가 없다고 나오면:

git fetch origin
git switch --track origin/robot/feat/S15P11E102-55-joystick-control

주의:
- git status에 수정 파일이 있으면 임의로 삭제하거나 브랜치를 바꾸지 않기.
- 본인 작업인지 확인한 뒤 커밋 또는 stash 여부를 결정하기.


------------------------------------------------------------
15. ROS2 작업공간으로 이동 및 빌드
------------------------------------------------------------

[Ubuntu]

각자의 실제 경로에 맞춰 ros2_ws로 이동하기.
예시는 Windows 바탕화면에 프로젝트가 있는 경우다.

cd "/mnt/c/Users/Windows사용자이름/Desktop/보미 로봇/S15P11E102/robot/ros2_ws"

현재 위치 확인:

pwd
ls

정상:
- 경로 마지막이 /robot/ros2_ws
- ls 결과에 src가 보이면 정상.

패키지 확인:

ls src

정상:
- core가 보이면 정상.

빌드:

colcon build --symlink-install

정상 예시:

Finished <<< core
Summary: 1 package finished

colcon 명령을 찾지 못하면:

sudo apt install -y python3-colcon-common-extensions

package 오류가 나오면:

source /opt/ros/humble/setup.bash
colcon build --symlink-install


------------------------------------------------------------
16. 빌드 결과 적용 및 launch 파일 확인
------------------------------------------------------------

[Ubuntu]

ros2_ws 위치에서:

source /opt/ros/humble/setup.bash
source install/setup.bash

launch 파일 확인:

ros2 launch core joystick_teleop.launch.py --show-args

정상 예시:

Arguments (pass arguments as '<name>:=<value>'):

    'cmd_vel_topic':
        조이스틱 속도 명령을 보낼 토픽
        (default: '/cmd_vel')

"Package 'core' not found"가 나오면:
- ros2_ws 위치가 맞는지 확인하기.
- 빌드가 성공했는지 확인하기.
- source install/setup.bash를 실행했는지 확인하기.

"file ... was not found"가 나오면:
- 현재 브랜치에 launch 파일이 있는지 확인하기.
- 다시 colcon build --symlink-install을 실행하기.


------------------------------------------------------------
17. 프로젝트 조이스틱 launch 실행
------------------------------------------------------------

[Ubuntu 창 1]

ros2_ws로 이동:

cd "/mnt/c/Users/Windows사용자이름/Desktop/보미 로봇/S15P11E102/robot/ros2_ws"

환경 적용:

source /opt/ros/humble/setup.bash
source install/setup.bash

실행:

ros2 launch core joystick_teleop.launch.py

정상:
- joy_node와 teleop_node가 실행됨.
- 창이 입력 대기 상태로 돌아오지 않고 계속 실행됨.
- /joy와 /cmd_vel 관련 노드·토픽이 생성됨.

joy_node에서 /dev/input/js0 오류가 나면:
- 프로젝트 코드 문제가 아니라 장치 연결 문제임.
- jstest /dev/input/js0부터 다시 확인하기.


------------------------------------------------------------
18. /joy와 /cmd_vel 토픽 확인
------------------------------------------------------------

[Ubuntu 창 2]

source /opt/ros/humble/setup.bash

프로젝트 환경도 적용:

cd "/mnt/c/Users/Windows사용자이름/Desktop/보미 로봇/S15P11E102/robot/ros2_ws"
source install/setup.bash

토픽 목록:

ros2 topic list

정상:
- /joy
- /cmd_vel

조이스틱 원본 데이터 확인:

ros2 topic echo /joy

스틱이나 버튼을 움직일 때 axes, buttons 값이 변하면 정상이다.
Ctrl + C로 종료하기.

속도 명령 확인:

ros2 topic echo /cmd_vel

정상:
- 조이스틱을 움직이면 linear.x 또는 angular.z 값이 변하면 정상.
- 스틱을 놓으면 0.0 값이 나오면 정상.

/joy는 변하지만 /cmd_vel이 변하지 않을 때:
- teleop_twist_joy 설정의 축 번호가 컨트롤러와 맞지 않을 수 있음.
- enable 버튼 설정이 켜져 있는지 YAML을 확인하기.
- require_enable_button: false 또는 사용 중인 enable 버튼 설정을 확인하기.
- launch 실행 창의 오류를 확인하기.

/cmd_vel 토픽 자체가 없을 때:
- teleop_node가 실행되지 않았을 수 있음.
- launch 실행 창에서 package 또는 YAML 오류를 확인하기.


------------------------------------------------------------
19. TurtleSim을 네 조이스틱 코드로 움직이기
------------------------------------------------------------

프로젝트 launch의 기본 출력이 /cmd_vel이고 TurtleSim은
/turtle1/cmd_vel을 구독하므로 토픽을 맞춰야 함.

[Ubuntu 창 1: TurtleSim]

source /opt/ros/humble/setup.bash
ros2 run turtlesim turtlesim_node

정상:
- 파란 창에 거북이가 나타나면 정상.

[Ubuntu 창 2: 프로젝트 조이스틱 launch]

cd "/mnt/c/Users/Windows사용자이름/Desktop/보미 로봇/S15P11E102/robot/ros2_ws"
source /opt/ros/humble/setup.bash
source install/setup.bash

TurtleSim 토픽으로 실행:

ros2 launch core joystick_teleop.launch.py cmd_vel_topic:=/turtle1/cmd_vel

정상:
- 조이스틱을 움직이면 거북이가 이동하거나 회전하면 정상.
- 스틱을 놓으면 거북이가 멈춘다.

안 움직일 때 확인:

[Ubuntu 창 3]

source /opt/ros/humble/setup.bash
ros2 topic echo /turtle1/cmd_vel

판단:
- 값이 변함 + 거북이 안 움직임 → TurtleSim 창/토픽 상태 확인
- 값이 안 변함 + /joy는 변함 → teleop 설정 또는 remapping 문제
- /joy도 안 변함 → 장치, xpad, joy_node 문제

토픽 연결 관계 확인:

ros2 topic info /turtle1/cmd_vel -v

정상:
- Publisher에 teleop 관련 노드가 보이면 정상.
- Subscriber에 turtlesim 노드가 보이면 정상.


------------------------------------------------------------
20. mock_motor_driver로 코드 확인
------------------------------------------------------------

실제 하드웨어 없이 /cmd_vel 명령이 모터 드라이버 노드까지 전달되는지
확인할 때 사용하기.

[Ubuntu 창 1]

cd "/mnt/c/Users/Windows사용자이름/Desktop/보미 로봇/S15P11E102/robot/ros2_ws"
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch core joystick_teleop.launch.py

[Ubuntu 창 2]

cd "/mnt/c/Users/Windows사용자이름/Desktop/보미 로봇/S15P11E102/robot/ros2_ws"
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 run core mock_motor_driver

정상:
- 조이스틱을 움직일 때 mock_motor_driver 창에
  linear.x, angular.z 등의 속도 값이 출력됨.

실행 파일을 찾을 수 없으면:

ros2 pkg executables core

목록에 실제 등록된 실행 파일 이름을 확인하기.
mock_motor_driver가 목록에 없다면 setup.py의 console_scripts 등록과
빌드 결과를 확인해야 함.


------------------------------------------------------------
21. 다음 날 다시 사용할 때의 짧은 실행 순서
------------------------------------------------------------

이미 설치와 bind가 끝난 노트북에서는 매번 전체 설치를 반복하지 않기.

1) Xbox USB 리시버 연결
2) 컨트롤러 전원 켜기 및 페어링 확인
3) Ubuntu 22.04 창 먼저 열기
4) PowerShell에서 BUSID 확인

usbipd list

5) STATE가 Shared이면 attach

usbipd attach --wsl --busid 본인_BUSID

6) Ubuntu에서 장치 확인

lsusb
ls -l /dev/input/js* 2>/dev/null
jstest /dev/input/js0

7) ros2_ws로 이동 후 환경 적용

source /opt/ros/humble/setup.bash
source install/setup.bash

8) 프로젝트 실행

ros2 launch core joystick_teleop.launch.py


------------------------------------------------------------
22. 작업 종료 후 안전하게 연결 해제
------------------------------------------------------------

실행 중인 ROS2 명령은 각 Ubuntu 창에서:

Ctrl + C

USB를 WSL에서 분리:

[PowerShell]

usbipd detach --busid 본인_BUSID

정상:
- usbipd list에서 Attached가 Shared로 바뀌면 정상.

공유 설정까지 완전히 해제해야 할 때만:

[관리자 PowerShell]

usbipd unbind --busid 본인_BUSID

주의:
- 일반적인 작업 종료에서는 detach만 하면 됨.
- unbind까지 하면 다음 사용 시 관리자 PowerShell에서 bind를 다시 해야 함.


------------------------------------------------------------
23. 최종 성공 체크리스트
------------------------------------------------------------

[ ] wsl.exe -l -v에서 Ubuntu-22.04가 VERSION 2
[ ] usbipd --version에서 버전 출력
[ ] usbipd list에 Xbox 장치 표시
[ ] Xbox 장치 STATE가 Attached
[ ] Ubuntu의 lsusb에 Xbox 또는 Microsoft 장치 표시
[ ] sudo modprobe xpad 성공
[ ] /dev/input/js0 생성
[ ] jstest에서 스틱과 버튼 값 변화
[ ] ros2 topic echo /joy에서 값 변화
[ ] ros2 topic echo /cmd_vel 또는 /turtle1/cmd_vel에서 값 변화
[ ] 조이스틱으로 TurtleSim 거북이 이동
[ ] mock_motor_driver에 속도 명령 출력

위 항목이 전부 확인되면
Xbox 컨트롤러 → Windows → WSL → xpad → /dev/input/js0
→ ROS2 joy_node → teleop_twist_joy → /cmd_vel
전체 연결이 정상적으로 완료


# ROS2 Ubuntu 설치 및 조이스틱 연결 설치방법

관리자 파워셀
wsl --install -d Ubuntu-22.04

재부팅

Ubuntu 다운로드 후 사용할 사용자 이름과 비번 작성(영문)

일반 파워셀
wsl.exe -l -v 로 버전 확인

NAME            STATE           VERSION
Ubuntu-22.04    Running         2
가 나오면 정상

Ubuntu 열고
sudo apt update
(이후 비밀번호 작성)

 ROS2 설치 위해서
Ubuntu 창에 작성
sudo apt install -y locales software-properties-common curl

이후
sudo locale-gen en_US en_US.UTF-8

sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
작성

export LANG=en_US.UTF-8

locale

화면에서 이거 아래 내용 보이면 성공
LANG=en_US.UTF-8
LC_ALL=en_US.UTF-8

이후
sudo add-apt-repository universe
작성후 엔터 치기

sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg


echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

sudo apt update

ROS 2 Humble 설치

sudo apt install -y ros-humble-desktop

echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc

source ~/.bashrc

ros2 --help

터틀심과 프로젝드 빌드 도구 설치
sudo apt install -y ros-humble-turtlesim python3-colcon-common-extensions

거부기 나오는지 확인
ros2 run turtlesim turtlesim_node


코드로 움직이는지 확인
코드 있는곳 까지 이동

패키지 설정
sudo apt install -y ros-humble-joy ros-humble-teleop-twist-joy

설치후 코드 빌드
colcon build --symlink-install

ros2 launch core joystick_teleop.launch.py --show-args

응답 이렇게 나오면 됨.
Arguments (pass arguments as '<name>:=<value>'):

    'cmd_vel_topic':
        조이스틱 속도 명령을 보낼 토픽
        (default: '/cmd_vel')


조이스틱 연결
USB 연결하기

관리자 파워셀
winget install --interactive --exact dorssel.usbipd-win
usbipd list
usbipd bind --busid 1-3 --force
usbipd list(Shared 확인)
재부팅




============================================================
Xbox 360 조이스틱 연결부터 최종 작동 확인까지
============================================================

※ 아래 단계는 위의 ROS2 Humble, TurtleSim, colcon 설치가 끝난 뒤 진행하기.
※ 명령어 위에 표시된 창 꼭 확인하기.
   - [관리자 PowerShell] : Windows에서 관리자 권한으로 실행한 PowerShell
   - [일반 PowerShell]   : Windows에서 일반 실행한 PowerShell
   - [Ubuntu]           : Ubuntu 22.04(WSL) 창
※ BUSID는 노트북마다 다름. 예시의 1-3을 무조건 쓰지 말고,
   반드시 본인 usbipd list 결과에 나온 Xbox 장치 BUSID 사용하기.


------------------------------------------------------------
1. Xbox 컨트롤러와 USB 리시버 준비
------------------------------------------------------------

1) Xbox 360 무선 컨트롤러라면 USB 무선 리시버를 노트북에 꽂기.
2) 컨트롤러 전원 켜기.
3) 리시버와 컨트롤러의 연결 버튼을 눌러 페어링하기.

정상:
- 컨트롤러의 초록색 불이 한 위치에 고정되면 정상.
- Windows의 장치 관리자 또는 usbipd list에
  Xbox 360 Controller, Xbox 360 Wireless Receiver 등 Xbox 장치가 보이면 정상.

정상이 아닐 때:
- 불이 계속 회전하면 아직 컨트롤러와 리시버가 페어링되지 않은 거야.
- USB를 뽑았다가 다른 USB 포트에 다시 꽂기.
- 배터리를 확인하고 다시 페어링하기.
- 장치 관리자에 노란 느낌표가 있다면 해당 장치를 제거하지 말고
  먼저 Windows 업데이트와 선택적 드라이버 업데이트를 확인하기.


------------------------------------------------------------
2. WSL 버전과 업데이트 확인
------------------------------------------------------------

[일반 PowerShell]

wsl.exe -l -v

정상 예시:

NAME            STATE           VERSION
Ubuntu-22.04    Running         2

정상이 아닐 때:

1) VERSION이 1이면 아래 명령을 실행하기.

wsl --set-version Ubuntu-22.04 2

2) Ubuntu-22.04가 목록에 없으면 위쪽의 WSL 설치 단계부터 다시 확인하기.

3) WSL을 최신 상태로 업데이트하기.

wsl --update

업데이트 후 필요하면 WSL을 종료하고 다시 실행하기.

wsl --shutdown

그다음 Ubuntu 22.04를 다시 열기.


------------------------------------------------------------
3. usbipd-win 설치 확인
------------------------------------------------------------

[관리자 PowerShell]

usbipd --version

정상:
- 버전 번호가 나오면 정상.

명령어를 찾을 수 없다고 나오면 설치하기.

winget install --interactive --exact dorssel.usbipd-win

설치 도중 Microsoft Store 약관 동의가 나오면 Y를 입력하고 Enter를 누르기.

설치가 끝나면:
1) 현재 PowerShell 창을 완전히 닫기.
2) PowerShell을 다시 관리자 권한으로 열기.
3) 다시 확인하기.

usbipd --version

그래도 명령어를 찾지 못하면 아래 경로로 직접 실행해 확인하기.

& "C:\Program Files\usbipd-win\usbipd.exe" --version


------------------------------------------------------------
4. Xbox 장치의 BUSID 확인
------------------------------------------------------------

[관리자 PowerShell]

usbipd list

정상 예시:

BUSID  VID:PID    DEVICE                 STATE
1-3    ....:....  Xbox 360 Controller   Not shared

여기서 Xbox 장치가 있는 행의 BUSID를 적어두기.
이후 설명에서는 예시로 1-3을 사용하지만 실제로는 본인의 번호를 넣기.

Xbox 장치가 아예 안 보일 때:
1) 리시버를 뽑았다가 다시 꽂기.
2) 다른 USB 포트에 꽂기.
3) 컨트롤러 전원 켜기.
4) 다시 실행하기.

usbipd list

5) 그래도 없으면 Windows 장치 관리자에서 Xbox 장치가 보이는지 확인하기.
   Windows에서도 안 보이면 ROS나 WSL 문제가 아니라 USB·리시버·Windows
   드라이버 문제부터 해결해야 함.


------------------------------------------------------------
5. Xbox USB 장치를 WSL과 공유(bind)
------------------------------------------------------------

※ 이 단계는 관리자 PowerShell에서 실행해야 함.

[관리자 PowerShell]

usbipd bind --busid 1-3

정상:
- 오류 없이 명령이 끝나면 정상.
- 아래 명령으로 확인했을 때 STATE가 Shared로 바뀌면 정상.

usbipd list

정상 예시:

1-3  Xbox 360 Controller  Shared

일반 bind에서 장치 드라이버 충돌 경고가 나오고 --force를 사용하라고 할 때만:

usbipd bind --busid 1-3 --force

그다음 다시 확인하기.

usbipd list

정상 예시:

1-3  Xbox 360 Controller  Shared (forced)

주의:
- --force는 일반 bind가 실패하고 화면에서 요구할 때만 사용하기.
- 재부팅이 필요하다는 문구가 나오면 컴퓨터를 재부팅하기.
- Shared는 공유 준비가 끝난 상태이고, 아직 WSL에 연결된 상태는 아님.


------------------------------------------------------------
6. Xbox USB 장치를 WSL에 연결(attach)
------------------------------------------------------------

1) Ubuntu 22.04 창을 먼저 열어 두기.
2) PowerShell에서 attach를 실행하기.

[일반 PowerShell 또는 관리자 PowerShell]

usbipd attach --wsl --busid 1-3

정상:
- 오류 없이 완료되거나 Successfully attached와 비슷한 내용이 나오면 정상.
- usbipd list에서 STATE가 Attached로 표시됨.

usbipd list

중요:
- attach된 동안 해당 USB 장치는 Windows에서 사용이 안 될 수도 있음.
- 컴퓨터를 재부팅하거나 리시버를 뽑으면 attach가 풀릴 수 있음.
- 다음에 사용할 때는 bind를 매번 다시 할 필요는 없지만,
  attach는 다시 실행해야 할 수 있음.


------------------------------------------------------------
7. attach가 실패할 때 해결
------------------------------------------------------------

A. "There are no WSL 2 distributions running"이 나올 때

1) Ubuntu 22.04를 먼저 실행하기.
2) Ubuntu 입력창이 보이는 상태에서 다시 실행하기.

usbipd attach --wsl --busid 1-3


B. "device is in an error state"가 나올 때

[관리자 PowerShell]

usbipd unbind --busid 1-3

1) Xbox USB 리시버를 노트북에서 뽑기.
2) 5초 정도 기다리기.
3) 다시 꽂기.
4) BUSID가 바뀌었을 수 있으므로 다시 확인하기.

usbipd list

5) 새로 확인한 BUSID로 다시 공유하기.

usbipd bind --busid 새_BUSID --force

6) Ubuntu를 열어 둔 상태에서 다시 연결하기.

usbipd attach --wsl --busid 새_BUSID


C. "Device is already attached"가 나올 때

이미 연결된 상태일 수 있음. Ubuntu에서 lsusb 확인 단계로 넘어가기.


D. "No device found for busid"가 나올 때

리시버를 다시 꽂으면서 BUSID가 바뀐 거야.

usbipd list

새 BUSID를 확인하고 명령어의 번호를 바꿔 다시 실행하기.


E. 계속 실패할 때 WSL 초기화

[일반 PowerShell]

wsl --shutdown
wsl --update

Ubuntu를 다시 연 뒤 attach를 다시 실행하기.

usbipd attach --wsl --busid 본인_BUSID


------------------------------------------------------------
8. Ubuntu에서 USB 장치 자체가 넘어왔는지 확인
------------------------------------------------------------

[Ubuntu]

먼저 USB 목록 확인 프로그램을 설치하기.

sudo apt update
sudo apt install -y usbutils

확인:

lsusb

정상:
- Xbox, Microsoft, Xbox 360 Wireless Receiver와 관련된 행이 보이면 정상.

정상이 아닐 때:
- PowerShell에서 usbipd list를 다시 확인하기.
- STATE가 Shared뿐이면 attach가 아직 안 된 거야.
- STATE가 Attached인지 확인하고 attach 단계부터 다시 진행하기.

중요:
- lsusb에 보인다는 것은 USB가 WSL까지 전달됐다는 뜻임.
- 이것만으로 아직 조이스틱 입력 장치가 생성됐다고 확정할 수는 없음.


------------------------------------------------------------
9. xpad 커널 드라이버 확인
------------------------------------------------------------

xpad는 일반 앱이 아니라 Xbox 컨트롤러용 리눅스 커널 드라이버다.
무조건 별도 프로그램을 설치하는 것이 아니라 먼저 현재 WSL에 있는지 확인하기.

[Ubuntu]

sudo modprobe xpad

정상:
- 아무 문구 없이 입력창으로 돌아오면 정상.

드라이버가 올라왔는지 확인:

lsmod | grep xpad

정상 예시:

xpad ...

정상이 아닐 때:

A. modprobe: FATAL: Module xpad not found가 나올 때

1) Windows PowerShell에서 WSL을 업데이트하기.

[일반 PowerShell]

wsl --update
wsl --shutdown

2) Ubuntu를 다시 열고 USB를 다시 attach하기.
3) Ubuntu에서 다시 실행하기.

sudo modprobe xpad

B. 업데이트 후에도 xpad 모듈이 없을 때

아래 도구를 설치하기.

[Ubuntu]

sudo apt update
sudo apt install -y git dkms build-essential linux-headers-generic joystick

그다음 xpad 드라이버 설치가 필요함.
단, 팀에서 사용한 xpad 설치 저장소 또는 스크립트가 정해져 있다면
반드시 같은 저장소와 버전을 사용하기. 임의의 Xbox One용 xone/xpadneo
드라이버를 Xbox 360 리시버에 설치하면 맞지 않을 수 있음.

※ 이 경우에는 화면의 uname -r 결과와 modprobe 오류를 확인한 후
   팀에서 검증한 xpad 설치 방법을 적용하는 것이 안전하다.

uname -r
sudo modprobe xpad


------------------------------------------------------------
10. /dev/input 장치 확인
------------------------------------------------------------

[Ubuntu]

ls -l /dev/input/

정상:
- event0, event1 등의 장치가 보이면 정상.
- 조이스틱 드라이버까지 정상이라면 js0도 보일 수 있음.

조이스틱 장치만 확인:

ls -l /dev/input/js* 2>/dev/null

정상 예시:

/dev/input/js0

아무것도 안 나올 때:

1) lsusb에 Xbox 장치가 보이는지 다시 확인하기.
2) xpad가 올라왔는지 확인하기.

lsmod | grep xpad

3) 최근 커널 메시지에서 Xbox 또는 xpad 오류를 확인하기.

sudo dmesg | tail -n 50

4) /dev/input/event 장치라도 생겼는지 확인하기.

ls -l /dev/input/event* 2>/dev/null

판단:
- lsusb에도 없음 → usbipd attach 문제
- lsusb에는 있음, xpad 없음 → xpad 드라이버 문제
- xpad 있음, js0 없음 → 드라이버 인식 또는 권한 문제
- js0 있음 → 다음 입력 테스트로 다음 단계로 넘어가기.


------------------------------------------------------------
11. jstest 설치 및 실제 버튼·스틱 입력 확인
------------------------------------------------------------

[Ubuntu]

sudo apt install -y joystick

실행:

jstest /dev/input/js0

정상:
- Axes와 Buttons 숫자가 화면에 나오면 정상.
- 스틱을 움직이면 축 숫자가 변하면 정상.
- 버튼을 누르면 off가 on으로 바뀌거나 값이 변하면 정상.

종료:

Ctrl + C

"No such file or directory"가 나오면:
- /dev/input/js0가 아직 생기지 않은 거야.
- 8~10단계로 돌아가 lsusb, xpad, js0 순서로 다시 확인하기.

"Permission denied"가 나오면 임시로 확인:

sudo jstest /dev/input/js0

sudo에서는 되는데 일반 jstest에서는 안 될 때:

sudo usermod -aG input $USER

그다음 Ubuntu 창을 모두 닫고 다시 열기.
그래도 권한이 반영되지 않으면 Windows PowerShell에서:

wsl --shutdown

Ubuntu를 다시 열고 USB attach부터 다시 진행하기.


------------------------------------------------------------
12. ROS2 joy_node 설치 확인
------------------------------------------------------------

[Ubuntu]

sudo apt install -y ros-humble-joy ros-humble-teleop-twist-joy

설치 확인:

ros2 pkg executables joy

정상:
- joy joy_node와 비슷한 실행 파일이 나오면 정상.

아무것도 나오지 않거나 package not found가 나오면:

source /opt/ros/humble/setup.bash

다시 확인:

ros2 pkg executables joy

그래도 없으면 다시 설치하기.

sudo apt update
sudo apt install -y ros-humble-joy ros-humble-teleop-twist-joy


------------------------------------------------------------
13. joy_node만 실행해서 ROS2 조이스틱 데이터 확인
------------------------------------------------------------

※ jstest가 정상인 것을 확인한 뒤 진행하기.

[Ubuntu 창 1]

source /opt/ros/humble/setup.bash
ros2 run joy joy_node --ros-args -p device_id:=0

정상:
- 창이 계속 실행 중인 상태가 됨.
- 오류 없이 조이스틱 입력을 기다리기.

"Couldn't open joystick /dev/input/js0"가 나오면:
- js0가 없거나 권한이 없는 거야.
- jstest 단계부터 다시 확인하기.

[Ubuntu 창 2]

source /opt/ros/humble/setup.bash
ros2 topic list

정상:
- /joy 토픽이 보이면 정상.

실제 데이터 확인:

ros2 topic echo /joy

정상:
- 스틱이나 버튼을 누를 때 axes와 buttons 값이 계속 출력됨.

아무것도 출력되지 않을 때:
- 컨트롤러 전원이 켜져 있는지 확인하기.
- jstest가 정상인지 다시 확인하기.
- Ubuntu 창 1의 joy_node 오류 내용을 확인하기.

테스트 종료:
- 각 Ubuntu 창에서 Ctrl + C


------------------------------------------------------------
14. 프로젝트 브랜치와 코드 위치 확인
------------------------------------------------------------

※ Git 브랜치 변경은 Git Bash에서 진행해도 되고 Ubuntu에서 진행해도 됨.
※ Git Bash와 Ubuntu가 같은 S15P11E102 폴더를 보고 있으면
   한쪽에서 브랜치를 바꾼 결과가 다른 쪽에도 바로 반영됨.

[Git Bash 또는 Ubuntu]

프로젝트 최상위 폴더로 이동한 뒤:

git status
git branch --show-current

정상:
- working tree clean
- 현재 사용할 조이스틱 브랜치 이름이 나오면 정상.

사용할 브랜치 예시:

robot/feat/S15P11E102-55-joystick-control

다른 브랜치라면:

git switch robot/feat/S15P11E102-55-joystick-control

브랜치가 없다고 나오면:

git fetch origin
git switch --track origin/robot/feat/S15P11E102-55-joystick-control

주의:
- git status에 수정 파일이 있으면 임의로 삭제하거나 브랜치를 바꾸지 않기.
- 본인 작업인지 확인한 뒤 커밋 또는 stash 여부를 결정하기.


------------------------------------------------------------
15. ROS2 작업공간으로 이동 및 빌드
------------------------------------------------------------

[Ubuntu]

각자의 실제 경로에 맞춰 ros2_ws로 이동하기.
예시는 Windows 바탕화면에 프로젝트가 있는 경우다.

cd "/mnt/c/Users/Windows사용자이름/Desktop/보미 로봇/S15P11E102/robot/ros2_ws"

현재 위치 확인:

pwd
ls

정상:
- 경로 마지막이 /robot/ros2_ws
- ls 결과에 src가 보이면 정상.

패키지 확인:

ls src

정상:
- core가 보이면 정상.

빌드:

colcon build --symlink-install

정상 예시:

Finished <<< core
Summary: 1 package finished

colcon 명령을 찾지 못하면:

sudo apt install -y python3-colcon-common-extensions

package 오류가 나오면:

source /opt/ros/humble/setup.bash
colcon build --symlink-install


------------------------------------------------------------
16. 빌드 결과 적용 및 launch 파일 확인
------------------------------------------------------------

[Ubuntu]

ros2_ws 위치에서:

source /opt/ros/humble/setup.bash
source install/setup.bash

launch 파일 확인:

ros2 launch core joystick_teleop.launch.py --show-args

정상 예시:

Arguments (pass arguments as '<name>:=<value>'):

    'cmd_vel_topic':
        조이스틱 속도 명령을 보낼 토픽
        (default: '/cmd_vel')

"Package 'core' not found"가 나오면:
- ros2_ws 위치가 맞는지 확인하기.
- 빌드가 성공했는지 확인하기.
- source install/setup.bash를 실행했는지 확인하기.

"file ... was not found"가 나오면:
- 현재 브랜치에 launch 파일이 있는지 확인하기.
- 다시 colcon build --symlink-install을 실행하기.


------------------------------------------------------------
17. 프로젝트 조이스틱 launch 실행
------------------------------------------------------------

[Ubuntu 창 1]

ros2_ws로 이동:

cd "/mnt/c/Users/Windows사용자이름/Desktop/보미 로봇/S15P11E102/robot/ros2_ws"

환경 적용:

source /opt/ros/humble/setup.bash
source install/setup.bash

실행:

ros2 launch core joystick_teleop.launch.py

정상:
- joy_node와 teleop_node가 실행됨.
- 창이 입력 대기 상태로 돌아오지 않고 계속 실행됨.
- /joy와 /cmd_vel 관련 노드·토픽이 생성됨.

joy_node에서 /dev/input/js0 오류가 나면:
- 프로젝트 코드 문제가 아니라 장치 연결 문제임.
- jstest /dev/input/js0부터 다시 확인하기.


------------------------------------------------------------
18. /joy와 /cmd_vel 토픽 확인
------------------------------------------------------------

[Ubuntu 창 2]

source /opt/ros/humble/setup.bash

프로젝트 환경도 적용:

cd "/mnt/c/Users/Windows사용자이름/Desktop/보미 로봇/S15P11E102/robot/ros2_ws"
source install/setup.bash

토픽 목록:

ros2 topic list

정상:
- /joy
- /cmd_vel

조이스틱 원본 데이터 확인:

ros2 topic echo /joy

스틱이나 버튼을 움직일 때 axes, buttons 값이 변하면 정상이다.
Ctrl + C로 종료하기.

속도 명령 확인:

ros2 topic echo /cmd_vel

정상:
- 조이스틱을 움직이면 linear.x 또는 angular.z 값이 변하면 정상.
- 스틱을 놓으면 0.0 값이 나오면 정상.

/joy는 변하지만 /cmd_vel이 변하지 않을 때:
- teleop_twist_joy 설정의 축 번호가 컨트롤러와 맞지 않을 수 있음.
- enable 버튼 설정이 켜져 있는지 YAML을 확인하기.
- require_enable_button: false 또는 사용 중인 enable 버튼 설정을 확인하기.
- launch 실행 창의 오류를 확인하기.

/cmd_vel 토픽 자체가 없을 때:
- teleop_node가 실행되지 않았을 수 있음.
- launch 실행 창에서 package 또는 YAML 오류를 확인하기.


------------------------------------------------------------
19. TurtleSim을 네 조이스틱 코드로 움직이기
------------------------------------------------------------

프로젝트 launch의 기본 출력이 /cmd_vel이고 TurtleSim은
/turtle1/cmd_vel을 구독하므로 토픽을 맞춰야 함.

[Ubuntu 창 1: TurtleSim]

source /opt/ros/humble/setup.bash
ros2 run turtlesim turtlesim_node

정상:
- 파란 창에 거북이가 나타나면 정상.

[Ubuntu 창 2: 프로젝트 조이스틱 launch]

cd "/mnt/c/Users/Windows사용자이름/Desktop/보미 로봇/S15P11E102/robot/ros2_ws"
source /opt/ros/humble/setup.bash
source install/setup.bash

TurtleSim 토픽으로 실행:

ros2 launch core joystick_teleop.launch.py cmd_vel_topic:=/turtle1/cmd_vel

정상:
- 조이스틱을 움직이면 거북이가 이동하거나 회전하면 정상.
- 스틱을 놓으면 거북이가 멈춘다.

안 움직일 때 확인:

[Ubuntu 창 3]

source /opt/ros/humble/setup.bash
ros2 topic echo /turtle1/cmd_vel

판단:
- 값이 변함 + 거북이 안 움직임 → TurtleSim 창/토픽 상태 확인
- 값이 안 변함 + /joy는 변함 → teleop 설정 또는 remapping 문제
- /joy도 안 변함 → 장치, xpad, joy_node 문제

토픽 연결 관계 확인:

ros2 topic info /turtle1/cmd_vel -v

정상:
- Publisher에 teleop 관련 노드가 보이면 정상.
- Subscriber에 turtlesim 노드가 보이면 정상.


------------------------------------------------------------
20. mock_motor_driver로 코드 확인
------------------------------------------------------------

실제 하드웨어 없이 /cmd_vel 명령이 모터 드라이버 노드까지 전달되는지
확인할 때 사용하기.

[Ubuntu 창 1]

cd "/mnt/c/Users/Windows사용자이름/Desktop/보미 로봇/S15P11E102/robot/ros2_ws"
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch core joystick_teleop.launch.py

[Ubuntu 창 2]

cd "/mnt/c/Users/Windows사용자이름/Desktop/보미 로봇/S15P11E102/robot/ros2_ws"
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 run core mock_motor_driver

정상:
- 조이스틱을 움직일 때 mock_motor_driver 창에
  linear.x, angular.z 등의 속도 값이 출력됨.

실행 파일을 찾을 수 없으면:

ros2 pkg executables core

목록에 실제 등록된 실행 파일 이름을 확인하기.
mock_motor_driver가 목록에 없다면 setup.py의 console_scripts 등록과
빌드 결과를 확인해야 함.


------------------------------------------------------------
21. 다음 날 다시 사용할 때의 짧은 실행 순서
------------------------------------------------------------

이미 설치와 bind가 끝난 노트북에서는 매번 전체 설치를 반복하지 않기.

1) Xbox USB 리시버 연결
2) 컨트롤러 전원 켜기 및 페어링 확인
3) Ubuntu 22.04 창 먼저 열기
4) PowerShell에서 BUSID 확인

usbipd list

5) STATE가 Shared이면 attach

usbipd attach --wsl --busid 본인_BUSID

6) Ubuntu에서 장치 확인

lsusb
ls -l /dev/input/js* 2>/dev/null
jstest /dev/input/js0

7) ros2_ws로 이동 후 환경 적용

source /opt/ros/humble/setup.bash
source install/setup.bash

8) 프로젝트 실행

ros2 launch core joystick_teleop.launch.py


------------------------------------------------------------
22. 작업 종료 후 안전하게 연결 해제
------------------------------------------------------------

실행 중인 ROS2 명령은 각 Ubuntu 창에서:

Ctrl + C

USB를 WSL에서 분리:

[PowerShell]

usbipd detach --busid 본인_BUSID

정상:
- usbipd list에서 Attached가 Shared로 바뀌면 정상.

공유 설정까지 완전히 해제해야 할 때만:

[관리자 PowerShell]

usbipd unbind --busid 본인_BUSID

주의:
- 일반적인 작업 종료에서는 detach만 하면 됨.
- unbind까지 하면 다음 사용 시 관리자 PowerShell에서 bind를 다시 해야 함.


------------------------------------------------------------
23. 최종 성공 체크리스트
------------------------------------------------------------

[ ] wsl.exe -l -v에서 Ubuntu-22.04가 VERSION 2
[ ] usbipd --version에서 버전 출력
[ ] usbipd list에 Xbox 장치 표시
[ ] Xbox 장치 STATE가 Attached
[ ] Ubuntu의 lsusb에 Xbox 또는 Microsoft 장치 표시
[ ] sudo modprobe xpad 성공
[ ] /dev/input/js0 생성
[ ] jstest에서 스틱과 버튼 값 변화
[ ] ros2 topic echo /joy에서 값 변화
[ ] ros2 topic echo /cmd_vel 또는 /turtle1/cmd_vel에서 값 변화
[ ] 조이스틱으로 TurtleSim 거북이 이동
[ ] mock_motor_driver에 속도 명령 출력

위 항목이 전부 확인되면
Xbox 컨트롤러 → Windows → WSL → xpad → /dev/input/js0
→ ROS2 joy_node → teleop_twist_joy → /cmd_vel
전체 연결이 정상적으로 완료