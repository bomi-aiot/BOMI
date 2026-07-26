# BOMI Robot

Ubuntu 22.04, ROS 2 Humble, Python 3.10을 기준으로 하는 로봇 워크스페이스입니다.

현재 `robot/ros2_ws/src` 아래에는 이동 명령과 기본 상태 처리를 담당하는 `core` 패키지가 있습니다. `core`는 Mock 단계이며 실제 모터나 조향 서보를 제어하지 않습니다.

| 실행 명령 | 현재 동작 |
| --- | --- |
| `ros2 run core status_publisher` | `/bomi/status`에 `bomi is ready`를 1초마다 발행 |
| `ros2 run core keyboard_teleop` | 키보드 입력을 `/cmd_vel`의 `geometry_msgs/Twist`로 발행 |
| `ros2 run core mock_motor_driver` | `/cmd_vel`을 구독해 값을 로그로 출력 |

현재 차량은 GA25-370 모터 1개와 MG996R 조향 서보 1개를 사용하는 자동차형 구조입니다. 4개 엔코더 모터, MDD10A와 Pico H를 사용하는 차동구동 장비는 개조를 위한 목표 구성으로, 아직 장착 및 검증이 완료되지 않았습니다. 자세한 하드웨어 구성과 안전한 검증 순서는 [`docs/hardware-control.md`](docs/hardware-control.md)를 참고하세요.

## 처음 개발 환경 설정하기

이 절은 ROS 2가 설치되지 않은 새 개발 환경에서 최초 한 번만 진행합니다. 프로젝트는 다음 환경을 기준으로 합니다.

- Ubuntu 22.04 LTS
- ROS 2 Humble
- Python 3.10
- Windows 사용 시 WSL2 + Ubuntu 22.04

### 1. Ubuntu 22.04 확인

Ubuntu 터미널에서 다음 명령을 실행합니다.

```bash
lsb_release -rs
```

결과가 `22.04`여야 합니다. Windows에 Ubuntu 22.04 WSL이 없다면 관리자 권한 PowerShell에서 다음 명령으로 설치합니다.

```powershell
wsl --install -d Ubuntu-22.04
```

설치 후 재부팅하고 Ubuntu 22.04 터미널을 실행합니다. 아래 명령은 PowerShell이 아닌 Ubuntu 터미널에서 실행해야 합니다.

### 2. ROS 2 패키지 저장소 등록

기본 패키지와 UTF-8 환경을 준비합니다.

```bash
sudo apt update
sudo apt install -y locales software-properties-common curl
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
export LANG=en_US.UTF-8
sudo add-apt-repository universe
```

ROS 2 저장소 인증 키와 패키지 저장소를 등록합니다.

```bash
sudo curl -sSL \
  https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  -o /usr/share/keyrings/ros-archive-keyring.gpg
```

```bash
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" \
  | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
```

### 3. ROS 2 Humble과 개발 도구 설치

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y ros-humble-desktop ros-dev-tools python3-colcon-common-extensions python3-rosdep
```

설치된 ROS 2 환경을 현재 터미널과 이후에 여는 터미널에 적용합니다.

```bash
source /opt/ros/humble/setup.bash
echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
source ~/.bashrc
```

설치 결과를 확인합니다.

```bash
printenv ROS_DISTRO
ros2 --help
```

`printenv ROS_DISTRO`의 결과가 `humble`이면 설치가 완료된 것입니다.

### 4. 프로젝트 의존성 설치

`rosdep`을 처음 한 번만 초기화하고 데이터를 갱신합니다.

```bash
sudo rosdep init
rosdep update
```

`rosdep sources list file already exists` 메시지가 나오면 이미 초기화된 것이므로 `rosdep update`부터 진행합니다.

저장소 위치가 다르면 아래 경로를 실제 경로로 변경한 뒤 프로젝트 의존성을 설치합니다.

```bash
cd /mnt/c/ssafy/kh/S15P11E102/robot/ros2_ws
rosdep install --from-paths src --ignore-src -r -y
```

## turtlesim으로 키보드 제어 확인하기

아래 경로는 저장소가 `C:\ssafy\kh\S15P11E102`에 있는 경우를 기준으로 합니다. 저장소 위치가 다르면 `/mnt/c/ssafy/kh/S15P11E102` 부분을 실제 경로에 맞게 바꾸세요.

`turtlesim` 실행은 키 입력과 `/cmd_vel` 발행을 화면에서 확인하기 위한 개발용 테스트입니다. 실제 자동차형 차량의 조향 동작을 재현하거나 하드웨어를 제어하지는 않습니다.

### 1. WSL 실행

Windows 터미널이나 PowerShell에서 Ubuntu 22.04를 실행합니다.

```bash
wsl -d Ubuntu-22.04
```

`robot/` 아래 텍스트 파일의 줄바꿈은 `robot/.gitattributes`에서 LF로 통일하므로 별도의 Git 설정이 필요하지 않습니다.

### 2. 필요한 ROS 2 패키지 설치

처음 한 번만 실행합니다.

```bash
sudo apt update
sudo apt install ros-humble-desktop ros-humble-ros2run ros-humble-turtlesim python3-colcon-common-extensions python3-rosdep -y
```

### 3. `core` 패키지 빌드

최초 실행 또는 패키지 구성 변경 후 빌드합니다.

```bash
cd /mnt/c/ssafy/kh/S15P11E102/robot/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select core
```

### 4. 두 터미널의 환경 준비

Ubuntu 터미널을 두 개 열고, 각 터미널에서 다음 명령을 실행합니다.

```bash
source /opt/ros/humble/setup.bash
source /mnt/c/ssafy/kh/S15P11E102/robot/ros2_ws/install/setup.bash
```

### 5. 첫 번째 터미널에서 turtlesim 실행

```bash
ros2 run turtlesim turtlesim_node
```

### 6. 두 번째 터미널에서 키보드 제어 실행

```bash
ros2 run core keyboard_teleop --ros-args -r /cmd_vel:=/turtle1/cmd_vel
```

`keyboard_teleop`은 기본적으로 `/cmd_vel`에 명령을 발행하지만, turtlesim은 `/turtle1/cmd_vel`을 구독합니다. 따라서 위 명령의 토픽 remap이 필요합니다.

### 조작키

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

종료할 때는 두 번째 터미널에서 `x`를 눌러 키보드 제어를 종료하고, 첫 번째 터미널에서 `Ctrl+C`를 눌러 turtlesim을 종료합니다.

## 다른 Mock 노드 실행

새 터미널에서 ROS 2와 워크스페이스 환경을 준비한 뒤 실행하세요.

```bash
source /opt/ros/humble/setup.bash
source /mnt/c/ssafy/kh/S15P11E102/robot/ros2_ws/install/setup.bash
```

상태 메시지를 발행하려면 다음 명령을 사용합니다.

```bash
ros2 run core status_publisher
```

키보드 명령을 로그로 확인하려면 터미널 두 개에서 `mock_motor_driver`와 `keyboard_teleop`을 각각 실행합니다.

```bash
ros2 run core mock_motor_driver
```

```bash
ros2 run core keyboard_teleop
```
