# 수동 연동 점검

이 디렉터리의 스크립트는 실제 자격증명, 네트워크, 데이터베이스,
마이크 또는 스피커를 사용한다. `pyproject.toml`의
`norecursedirs = ["manual"]`이 이 디렉터리를 pytest 수집 대상에서 통째로
빼므로, 기본 실행에서는 마커와 무관하게 절대 수집되지 않는다.

> **하드웨어 점검은 운영자가 지켜보는 상태에서 실행한다.** 그리고 실행하지 않은
> 점검은 통과로 기록하지 않는다. 각 스크립트는 첫 외부 동작 전에 필수 설정을
> 확인한다.

## 준비

`robot/ai_chat`에서 venv를 활성화한 뒤 설치한다. MQTT 점검까지 하려면 `mqtt`
추가 의존성이 필요하다 — paho는 선택 의존성이라 `".[dev]"`만으로는 MQTT 경로를
점검할 수 없다.

Windows PowerShell:

```powershell
cd robot\ai_chat
.\venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,mqtt]"
```

Ubuntu / Jetson:

```bash
cd robot/ai_chat
source venv/bin/activate
python -m pip install -e ".[dev,mqtt]"
```

## 점검 순서

점검에는 의존관계가 있다. 아래 순서대로 올라가면 실패 지점이 바로 좁혀진다.

| 스크립트 | 확인 대상 | 선행 |
|---|---|---|
| `mic_level_check.py` | 마이크 입력 레벨과 장치 인덱스, `AUDIO_SILENCE_THRESHOLD` 실측 | — |
| `speaker_probe.py` | 출력 장치에서 실제로 소리가 나는지 (귀로 확인) | — |
| `audio_smoke.py` | `AUDIO_MODE` 기준 녹음·재생 왕복 | 위 둘 |
| `rtzr_token_smoke.py` | RTZR 인증 토큰 발급 | — |
| `stt_smoke.py` | 음성 → 텍스트 | `rtzr_token_smoke` |
| `tts_smoke.py` | 텍스트 → WAV 재생 | `speaker_probe` |
| `llm_smoke.py` | Gemini 응답 | — |
| `weather_smoke.py` | 기상청 단기예보 | — |
| `db_connection_smoke.py` | direct/SSH PostgreSQL 연결 | — |
| `ec2_query_smoke.py` | 원격 DB 조회 | `db_connection_smoke` |
| `medical_flow_smoke.py` | 의료 조회 전체 흐름 | `ec2_query_smoke`, `llm_smoke` |
| `probe.py` | 로컬 SQLite 운영 상태 스냅샷·비교 | — |

`robot/ai_chat`에서 필요한 점검만 하나씩 실행한다.

```bash
python tests/manual/mic_level_check.py
python tests/manual/speaker_probe.py
python tests/manual/audio_smoke.py
python tests/manual/rtzr_token_smoke.py
python tests/manual/stt_smoke.py
python tests/manual/tts_smoke.py
python tests/manual/llm_smoke.py
python tests/manual/weather_smoke.py
python tests/manual/db_connection_smoke.py
python tests/manual/ec2_query_smoke.py
python tests/manual/medical_flow_smoke.py
python tests/manual/probe.py
```

**젯슨에서는 `env -u PYTHONPATH` 를 앞에 붙인다.** ROS 2 환경이 주입한
`PYTHONPATH`의 lark·numpy가 파이썬을 죽인다(루트 `CLAUDE.md` §6).

```bash
env -u PYTHONPATH python tests/manual/audio_smoke.py
```

## 오디오 점검의 함정

**젯슨의 오디오 장치 인덱스는 재부팅마다 바뀐다.** 실기에서 24↔25가 뒤바뀌는 것을
확인했고, `AUDIO_INPUT_DEVICE=1` 은 젯슨에서 HDMI다. `mic_level_check.py` 가
존재하는 이유가 바로 이것이다 — 부팅 후 인덱스를 다시 확인하거나 장치명 일부를 쓴다.

`speaker_probe.py` 는 로그로 알 수 없는 것을 확인한다. PortAudio는 "존재하는 장치"를
열어 줄 뿐 그 장치가 실제로 스피커에 연결돼 있는지는 알려주지 않는다. 잭에 아무것도
안 꽂힌 출력도 정상으로 열리고 정상으로 재생을 마친다 — 조용할 뿐이다.

`audio_smoke.py`는 `.env`의 `AUDIO_MODE`를 따른다. `laptop`은 장치를
비워두면 운영체제 기본 장치를 사용한다. `robot`은 대상 Jetson에서 확인한
`AUDIO_INPUT_DEVICE`와 `AUDIO_OUTPUT_DEVICE`를 반드시 지정해야 한다.

`probe.py` 는 `bomi_ai_chat` 을 import 하지 않고 SQLite 파일을 경로로 직접 연다.
런타임이 망가졌을 때 가장 필요한 도구라, 설정 검증에 걸려 진단 도구까지 죽는 일을
피하기 위해서다.

## 아직 없는 점검

다음 두 가지는 이 디렉터리에 스크립트가 없다. 필요하면 저장소 루트
`scripts/dev/publish_event.py` 로 수동 발행해 확인한다.

- **웨이크워드 실기 점검** — `models/bomiya.onnx` 로드, 임계값 조정, 오탐·미탐 확인.
  현재는 앱을 띄우고 로그의 `wakeword score=… hits=n/m` 을 읽는 방법뿐이다.
- **MQTT 왕복 점검** — `START_CONVERSATION` 수신과 `CONVERSATION_STARTED` 발행.

## 범위 밖

공공 의료데이터 수집 코드는 AI Chat 런타임 소유가 아니므로 제거했다.
원천 데이터 갱신이 다시 필요하면 별도 적재 작업과 소유자를 정한 뒤
AI Chat 패키지 밖에서 운영한다.
