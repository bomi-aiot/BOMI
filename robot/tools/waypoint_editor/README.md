# BOMI 웹 웨이포인트 편집기

저장된 ROS 2 점유지도 위를 클릭해 `room_waypoints.yaml`의 순찰 지점을
추가·삭제하고 순서를 정하는 Streamlit 개발 도구입니다. ROS 2 실행이나 실물
로봇 연결은 필요하지 않습니다.

| 다루는 파일 | 경로 |
| --- | --- |
| 지도 (선택 목록) | `robot/ros2_ws/src/mapping/maps/*.yaml` + 그 YAML 의 `image` 가 가리키는 이미지 |
| 웨이포인트 (편집 대상) | `robot/ros2_ws/src/core/config/room_waypoints.yaml` |

웨이포인트 파일은 `core` 패키지 소유이고 `bridge`(목적지→좌표)와
`bomi_map.sh`(매핑 시 자동 갱신)도 같은 파일을 씁니다. 여기서 저장하면 그 셋이
함께 영향을 받습니다. 특히 `bomi_map.sh` 는 매핑 단계에서 이 파일을 덮어쓰므로,
지도를 새로 만든 뒤에 편집해야 결과가 남습니다.

좌표는 저장할 때 소수 3자리로 반올림됩니다 — 실측값(`-0.0754`)을 넣었는데 값이
달라 보이는 이유입니다. 순찰 옵션(`loop`, `waypoint_delay_sec` 등)은 편집기를
거쳐도 원문 그대로 보존됩니다(회귀 테스트 있음).

## WSL 설치 및 실행

```bash
cd /mnt/c/Users/<Windows사용자이름>/workspaces/S15P11E102/robot
python3 -m venv ~/.venvs/bomi-waypoint-editor
source ~/.venvs/bomi-waypoint-editor/bin/activate
pip install -r tools/waypoint_editor/requirements.txt
streamlit run tools/waypoint_editor/app.py
```

이미 가상환경을 만든 뒤 의존성 파일이 변경됐다면 다음 명령으로 패키지를
갱신합니다.

```bash
pip install --upgrade -r tools/waypoint_editor/requirements.txt
```

이 앱은 Streamlit 공식 `components.v2`로 지도 클릭을 처리하므로 별도의 이미지
클릭 컴포넌트를 설치하지 않습니다.

Windows 브라우저에서 <http://localhost:8501>을 엽니다.

## 운영 배포

운영 배포에서는 설치 기사 전용 Basic 인증을 사용하며 다음 주소로 접속합니다.

<https://i15e102.p.ssafy.io/waypoint-editor/>

Docker 이미지는 저장소의 지도와 기본 `room_waypoints.yaml`을 포함합니다. EC2에서
파일을 바꿔도 Jetson에는 자동으로 반영되지 않으므로 운영 화면의 서버 저장 버튼은
비활성화됩니다. 편집 결과를 YAML로 다운로드한 뒤 검토하여 Jetson의 파일에
적용합니다.

배포는 `scripts/deploy/deploy-backend.sh`와 통합 Jenkins 파이프라인에 포함됩니다.
별도의 포트를 인터넷에 공개하지 않고 Nginx가 Docker 네트워크의
`waypoint-editor:8501`로 연결합니다.

> **최초 배포 전 1회만** — 아래 세 블록은 다시 실행하면 기존 인증 파일을
> 덮어씁니다.

최초 배포 전 EC2에서 운영자 콘솔과 별개의 인증 파일을 생성합니다.

```bash
docker run --rm -it \
  -v /home/ubuntu/bomi/secrets:/secrets \
  httpd:2.4-alpine \
  htpasswd -cB /secrets/waypoint-editor.htpasswd bomi-installer

NGINX_GID="$(docker run --rm nginx:1.30.4-alpine id -g nginx)"
sudo chown root:"$NGINX_GID" /home/ubuntu/bomi/secrets/waypoint-editor.htpasswd
sudo chmod 640 /home/ubuntu/bomi/secrets/waypoint-editor.htpasswd
```

`production.env`에는 파일 경로만 기록합니다.

```dotenv
NGINX_WAYPOINT_EDITOR_HTPASSWD_FILE=/home/ubuntu/bomi/secrets/waypoint-editor.htpasswd
```

## 사용 방법

1. 사이드바에서 `mapping/maps`의 지도 YAML을 선택합니다.
2. 지도에서 로봇이 정차할 위치를 클릭합니다.
3. 웨이포인트 이름과 로봇이 바라볼 방향을 입력하고 추가합니다.
4. 순찰 순서를 조정한 뒤 YAML을 다운로드하거나 저장합니다.
5. **로컬 실행에서만** 서버 저장이 가능하며, 저장 전 기존 파일은 같은 경로의
   `room_waypoints.yaml.bak`으로 복사됩니다. 운영 배포
   (<https://i15e102.p.ssafy.io/waypoint-editor/>)에서는 저장 버튼이 비활성이므로
   YAML 을 다운로드해 Jetson 에 직접 적용합니다.

로컬에서도 실수로 덮어쓰고 싶지 않다면 환경변수
`WAYPOINT_EDITOR_ALLOW_SERVER_WRITE=false` 로 실행합니다(기본값은 `true`).
운영 배포는 `infra/compose.prod.yml` 이 이 값을 `false` 로 줍니다.

지도에서 지정한 위치가 실제로 안전하고 Nav2로 도달 가능한지는 실차에서 각
지점을 한 번씩 검증해야 합니다. 지도를 다시 생성하면 새 지도에서 웨이포인트를
다시 지정합니다.

## 테스트

```bash
pip install -r tools/waypoint_editor/requirements-dev.txt
PYTHONPATH=tools/waypoint_editor pytest tools/waypoint_editor/test -q
```
