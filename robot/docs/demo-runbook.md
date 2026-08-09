# 시연 실행 순서

젯슨에서 시연 3개 시나리오를 돌리는 방법과, 실기에서 실제로 겪은 함정들.

`.env`·가상환경·PulseAudio 설정은 저장소에 들어가지 않는다. 젯슨을 새로
설치했거나 다른 체크아웃에서 돌린다면 **§3 을 먼저** 실행해야 한다.

---

## 1. 실행 전 (매번)

EC2의 `production.env`에는 아래 값을 넣고 백엔드 컨테이너를 재시작한다. 센서
관측은 계속 저장되지만 독립 온습도 시나리오가 먼저 로봇을 가져가지 않으며,
최신 값은 귀가 추종 후 대화에서 사용한다.

```bash
WELLNESS_SCENARIO_ENABLED=false
```

```bash
cd ~/S15P11E102
export MQTT_PASSWORD=$(grep -m1 '^MQTT_PASSWORD=' robot/ai_chat/.env | cut -d= -f2-)
export PYTHONPATH=/home/ssafy/S15P11E102/robot/ai_vision/src
export AI_VISION_PYTHON=/home/ssafy/S15P11E102/robot/ai_vision/venv/bin/python
export AI_CHAT_PYTHON=/home/ssafy/S15P11E102/robot/ai_chat/.venv/bin/python
export LD_LIBRARY_PATH=/home/ssafy/S15P11E102/robot/ai_vision/venv/lib/python3.10/site-packages/nvidia/cu12/lib:/usr/local/cuda/lib64:/usr/lib/aarch64-linux-gnu
```

세 줄이 왜 필요한가

| 변수 | 없으면 |
|---|---|
| `AI_CHAT_PYTHON` | ai_chat 가상환경이 `venv` 가 아니라 `.venv` 라 "가상환경이 없습니다"로 종료 |
| `LD_LIBRARY_PATH` | GPU 용 torch 가 `libcudss.so.0` 를 못 찾아 ai_vision 이 즉시 죽고, 전체 스택이 함께 내려감 |
| `AI_VISION_PYTHON` | 다른 체크아웃의 CPU 전용 venv 를 잡으면 추론이 0.04초 → 0.75초로 느려져 추종이 끊긴다 |

---

## 2. 시나리오별 실행

### 현관 출입 → 추종 → 온습도 → 복귀

```bash
HOMECOMING_FOLLOW_SECONDS=10 bash robot/scripts/run-homecoming-follow.sh
```

`[4/4] Nav2 준비 완료` 가 뜬 뒤 문을 연다. 인사에 **실제로 대답**해야 다음
단계로 넘어간다(무응답 15초면 대화가 끝난다).

### "보미야" 호출 → 방향 탐색 → 접근

```bash
source /opt/ros/humble/setup.bash && source robot/ros2_ws/install/setup.bash
ros2 launch core bomi_wake_search.launch.py \
    ai_chat_python:="$AI_CHAT_PYTHON" \
    use_mqtt_bridge:=true robot_id:=bomi-AA001 \
    broker_host:=i15e102.p.ssafy.io broker_port:=8883 use_tls:=true \
    mqtt_username:=bomi-jetson mqtt_password:="$MQTT_PASSWORD"
```

⚠️ `use_mqtt_bridge:=true` 를 빼면 안 된다. `MQTT_ENABLED=true` 상태에서
"보미야"는 백엔드 시나리오를 시작하는데, 브릿지가 없으면 아무도 응답하지
않아 시나리오가 타임아웃되고 **로봇이 SAFE_STOP 으로 잠긴다**(§4 참고).

백엔드 없이 로봇만 볼 때는 `robot/scripts/run-wake-search.sh` 를 쓴다.

---

## 3. 젯슨 최초 설정 (한 번만)

### 스피커

PulseAudio 가 기본 출력을 젯슨 내장 HDMI 로 잡는다. TTS 는 정상인데
스피커에서 아무 소리도 안 난다.

```bash
mkdir -p ~/.config/pulse
cat > ~/.config/pulse/default.pa <<'EOF'
.include /etc/pulse/default.pa
set-default-sink alsa_output.usb-Jieli_Technology_USB_Composite_Device_433135383532342E-00.analog-stereo
EOF
pulseaudio -k   # 다시 시작
```

확인: `pactl info | grep "Default Sink"` 가 `usb-Jieli...` 여야 한다.

### GPU (YOLO 추론 0.75초 → 0.04초)

pip 기본 저장소의 torch 는 Jetson 에서 GPU 를 못 잡는다. JetPack 6.2 용
wheel 을 ai_vision venv 안에만 설치한다.

```bash
V=~/S15P11E102/robot/ai_vision/venv
$V/bin/pip install --no-cache-dir --ignore-installed \
  --index-url https://pypi.jetson-ai-lab.io/jp6/cu126 \
  torch==2.11.0 torchvision==0.26.0
$V/bin/pip install --no-cache-dir \
  --index-url https://pypi.jetson-ai-lab.io/jp6/cu126 \
  nvidia-cudss-cu12 nvidia-cudnn-cu12
$V/bin/pip uninstall -y nvidia-cublas-cu12   # ★ Tegra 는 JetPack cuBLAS 를 써야 한다
$V/bin/pip install --no-cache-dir "numpy<2"  # numpy 2 는 시스템 matplotlib 을 깬다
```

확인:

```bash
PYTHONPATH= LD_LIBRARY_PATH=$V/lib/python3.10/site-packages/nvidia/cu12/lib:/usr/local/cuda/lib64:/usr/lib/aarch64-linux-gnu \
  $V/bin/python -c "import torch; print(torch.cuda.is_available())"   # True
```

주의: 인덱스 도메인은 `.io` 다(`.dev` 는 없는 주소). 설치 후 pip 캐시가 수
GB 쌓이니 `rm -rf ~/.cache/pip` 로 비운다 — 실제로 디스크가 99% 까지 찼다.

### 지도

`~/.bomi_demo_state` 의 `MAP` 이 가리키는 지도 파일이 체크아웃에 있어야 한다.
없으면 "지도 파일이 없습니다"로 즉시 종료한다.

```bash
cat ~/.bomi_demo_state          # MAP=bomi_real_19
ls robot/ros2_ws/src/mapping/maps/bomi_real_19.yaml
```

### `.env` 오디오 값

`robot/ai_chat/.env.example` 기준으로 맞춘다. 특히:

| 키 | 값 | 틀리면 |
|---|---|---|
| `AUDIO_SILENCE_THRESHOLD` | `150` | 300 이면 목소리를 무음으로 처리해 "말 안 함"으로 끝난다 |
| `AUDIO_SILENCE_LIMIT_SECONDS` | `1.5` | 응답 판정이 느려진다 |
| `AUDIO_INPUT_DEVICE` | `reSpeaker` | 마이크가 안 잡힌다 |
| `AUDIO_OUTPUT_DEVICE` | `pulse` | 장치 번호는 재부팅마다 바뀐다 |

---

## 4. 안 될 때

| 증상 | 원인 | 조치 |
|---|---|---|
| 문을 열어도 로봇이 안 움직인다 | 이전 시나리오가 안 끝났거나 `SAFE_STOP` | 운영자 대시보드에서 강제 종료·해제 (`backend/tools/operator_console/README.md`) |
| 말은 하는데 안 들린다 | 기본 출력이 HDMI | §3 스피커 |
| 대답해도 "no speech within 15s" | `AUDIO_SILENCE_THRESHOLD` 가 높다 | §3 `.env` |
| ai_vision 이 뜨자마자 죽는다 | `LD_LIBRARY_PATH` 없음, 또는 이전 실행이 카메라 점유 | §1 export / `fuser -k /dev/video0` |
| `pico_driver` 구독자 0 | ROS 2 디스커버리가 늦다 | 10초 뒤 재실행하면 대개 붙는다 |
| 추종이 자꾸 끊긴다 | CPU 추론으로 돌고 있다 | 로그에 `CUDA initialization` 경고가 있는지 확인 → §3 GPU |

### 운영자 대시보드

EC2 의 `127.0.0.1:8501` 에만 열려 있다. **운영자 PC 에서** 터널을 연다
(EC2 안에서 실행하면 안 된다).

```bash
ssh -N -L 8501:127.0.0.1:8501 <EC2 별칭>
# 브라우저: http://localhost:8501
```

---

## 5. 로그

```bash
tail -f /tmp/bomi_ai_chat.log                        # 대화·웨이크워드·방향
tail -f /tmp/bomi_homecoming_follow/*.log            # 추종·탐색·비전
tail -f /tmp/bomi_wake_search.log                    # run-wake-search.sh 쪽
grep -E 'error|abort|failed' /tmp/bomi_navigation.log | tail -50
```

로봇이 안 움직일 때 먼저 볼 줄:

```
추종 속도 판단: reason=...
```

`person_distance_unavailable`(LiDAR 가 사람을 못 봄) ·
`lidar_not_ready` · `waiting_for_person_resume_distance`(이미 가까움) ·
`movement_not_allowed`(대상 미확정) 이 각각 다른 곳을 가리킨다.
