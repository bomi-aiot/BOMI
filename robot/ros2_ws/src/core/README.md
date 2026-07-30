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