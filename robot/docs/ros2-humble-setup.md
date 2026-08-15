# ROS 2 Humble 설치와 개발 환경 설정

ROS 2가 설치되지 않은 새 개발 환경에서 최초 한 번만 진행합니다.
프로젝트는 다음 환경을 기준으로 합니다.

- Ubuntu 22.04 LTS
- ROS 2 Humble
- Python 3.10
- Windows 사용 시 WSL2 + Ubuntu 22.04

## 1. Ubuntu 22.04 확인

Ubuntu 터미널에서 다음 명령을 실행합니다.

```bash
lsb_release -rs
```

결과가 `22.04`여야 합니다. Windows에 Ubuntu 22.04 WSL이 없다면 관리자 권한
PowerShell에서 다음 명령으로 설치합니다.

```powershell
wsl --install -d Ubuntu-22.04
```

설치 후 재부팅하고 Ubuntu 22.04 터미널을 실행합니다. 아래 명령은 PowerShell이
아닌 Ubuntu 터미널에서 실행해야 합니다.

## 2. ROS 2 패키지 저장소 등록

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

## 3. ROS 2 Humble과 개발 도구 설치

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

## 4. 프로젝트 의존성 설치

`rosdep`을 처음 한 번만 초기화하고 데이터를 갱신합니다.

```bash
sudo rosdep init
rosdep update
```

`rosdep sources list file already exists` 메시지가 나오면 이미 초기화된
것이므로 `rosdep update`부터 진행합니다.

저장소 위치가 다르면 아래 경로를 실제 경로로 변경한 뒤 프로젝트 의존성을
설치합니다.

```bash
cd <저장소>/robot/ros2_ws
rosdep install --from-paths src --ignore-src -r -y
```

`rosdep` 이 잡지 못하거나 별도로 필요한 패키지가 셋 있습니다.

| 패키지 | 언제 필요한가 |
| --- | --- |
| `ros-humble-robot-localization` | Nav2 실기 launch 의 기본값 `use_ekf:=true` 가 요구합니다. 없으면 launch 가 즉시 죽습니다(`use_ekf:=false` 로 우회 가능) |
| `ros-humble-nav2-map-server` | 지도를 저장·로드할 때. [`gazebo-slam-mapping.md`](gazebo-slam-mapping.md) 가 따로 설치시킵니다 |
| `ydlidar_ros2_driver` | 실물 LiDAR. `rosdep` 으로 안 잡히는 외부 드라이버라 [`handheld-lidar-mapping.md`](handheld-lidar-mapping.md) 의 안내를 따릅니다 |

이 문서는 x86 WSL 기준입니다. 실제 로봇인 젯슨(aarch64)은 GPU 용 torch 등에서
별도 절차가 필요하며 [`demo-runbook.md`](demo-runbook.md) `## 3` 이 다룹니다.

설치가 끝나면 [`../README.md`](../README.md)의 빌드 절차로 이어집니다.
