# turtlesim으로 키보드 제어 확인하기

`turtlesim` 실행은 키 입력과 `/cmd_vel` 발행을 화면에서 확인하기 위한
개발용 테스트입니다. 실제 차량의 주행 특성을 재현하거나 하드웨어를
제어하지는 않습니다.

아래 경로는 저장소가 `C:\S15P11E102`에 있는 경우를 기준으로 합니다.
저장소 위치가 다르면 `/mnt/c/S15P11E102` 부분을 실제 경로에 맞게 바꾸세요.
(다른 로봇 문서는 `<저장소>` 자리표시자를 씁니다.)

## 1. WSL 실행

Windows 터미널이나 PowerShell에서 Ubuntu 22.04를 실행합니다.

```bash
wsl -d Ubuntu-22.04
```

`robot/` 아래 텍스트 파일의 줄바꿈은 `robot/.gitattributes`에서 LF로
통일하므로 별도의 Git 설정이 필요하지 않습니다.

## 2. 필요한 ROS 2 패키지 설치

처음 한 번만 실행합니다.

```bash
sudo apt update
sudo apt install ros-humble-desktop ros-humble-ros2run ros-humble-turtlesim python3-colcon-common-extensions python3-rosdep -y
```

## 3. `core` 패키지 빌드

최초 실행 또는 패키지 구성 변경 후 빌드합니다.

```bash
cd /mnt/c/S15P11E102/robot/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select core
```

## 4. 두 터미널의 환경 준비

Ubuntu 터미널을 두 개 열고, 각 터미널에서 다음 명령을 실행합니다.

```bash
source /opt/ros/humble/setup.bash
source /mnt/c/S15P11E102/robot/ros2_ws/install/setup.bash
```

## 5. 첫 번째 터미널에서 turtlesim 실행

```bash
ros2 run turtlesim turtlesim_node
```

## 6. 두 번째 터미널에서 키보드 제어 실행

```bash
ros2 run core keyboard_teleop --ros-args -r /cmd_vel:=/turtle1/cmd_vel
```

`keyboard_teleop`은 기본적으로 `/cmd_vel`에 명령을 발행하지만, turtlesim은
`/turtle1/cmd_vel`을 구독합니다. 따라서 위 명령의 토픽 remap이 필요합니다.

## 조작키

| 키 | 동작 |
| --- | --- |
| `w` | 전진 |
| `s` | 후진 |
| `a` | 왼쪽 회전 |
| `d` | 오른쪽 회전 |
| `q` / `e` | 전진하면서 왼쪽 / 오른쪽 회전 |
| `z` / `c` | 후진하면서 왼쪽 / 오른쪽 회전 |
| `Space` | 정지 |
| `x` | 키보드 제어 종료 |

종료할 때는 두 번째 터미널에서 `x`를 눌러 키보드 제어를 종료하고,
첫 번째 터미널에서 `Ctrl+C`를 눌러 turtlesim을 종료합니다.
