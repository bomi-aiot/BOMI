# BOMI AI Chat

BOMI 로봇의 음성 대화를 처리하는 Python 패키지다. 마이크 입력을 RTZR
STT로 변환하고, 의료 여부와 날씨 요청을 판별한 뒤 Gemini 2.5 Flash Lite로
답변을 생성해 Typecast 음성으로 재생한다.

현재 런타임은 Gemini 단일 API 체제다. Ollama나 Jetson 로컬 LLM은 사용하지
않는다.

## 현재 동작

한 차례의 대화는 다음 순서로 실행된다.

1. PortAudio 호환 마이크에서 WAV 음성을 녹음한다.
2. RTZR STT가 음성을 텍스트로 변환한다.
3. `jhgan/ko-sroberta-multitask` 임베딩 모델이 의료 조회 여부를 판별한다.
4. 의료 요청은 Gemini function calling과 PostgreSQL의 `hospital`,
   `pharmacy`, `drug_permit` 데이터를 사용한다.
5. 일반 요청은 Gemini가 답변하며, 지원 도시의 날씨 질문에는 기상청
   단기예보 결과를 함께 제공한다.
6. Typecast가 답변을 WAV로 만들고 선택한 스피커로 재생한다.

외부 연동 실패는 단계별로 기록한다. TTS 또는 스피커 재생이 실패해도 생성된
텍스트 답변은 보존된다. `--once` 없이 실행하면 실패한 차례 이후에도 다음
대화를 계속 받는다.

## 디렉터리 구조

```text
src/bomi_ai_chat/
├─ audio_io/   laptop/robot 오디오 어댑터와 공통 sounddevice 백엔드
├─ db/         direct/SSH PostgreSQL 연결과 의료 조회
├─ llm/        Gemini 일반 대화, 의료 도구 호출, 의료·날씨 의도 규칙
├─ stt/        RTZR 인증·업로드·제한 폴링
├─ tts/        Typecast WAV 생성
├─ weather/    기상청 단기예보 조회
├─ graph/      대화 런타임 판단·생성 노드 (게이트, 트리아지, 핸들러, 출력)
├─ jobs/       주기 작업 (침묵 틱, 현관 감시, outbox flush, 일일 요약)
├─ localstore/ 로봇 로컬 SQLite (운영 상태, 발화 제안 큐, 발신 큐, 캐시 오디오)
├─ notify/     보호자 알림 채널 어댑터 (채널 교체는 여기 한 곳)
├─ audio/      에코 억제·비블로킹 재생·barge-in 판단 (audio_io 위의 '판단' 계층)
├─ clock.py    주입 가능한 시계. 실제 시계를 읽는 유일한 파일
├─ policy.py   대화 정책 상수 (우선순위 행렬, 쿨다운, TTL, 사다리 임계치)
├─ state.py    ConvState 스키마와 SpeechProposal
├─ config.py   환경변수 로딩과 기능별 검증
├─ pipeline.py 한 차례 및 반복 대화 조율
└─ main.py     CLI 옵션과 의존성 조립
tests/         네트워크·DB·오디오 장치 없이 실행하는 단위 테스트
tests/manual/  운영자가 직접 실행하는 외부 연동 점검
```

`graph/`와 `jobs/`는 현재 배선과 상태 스키마만 동작하는 뼈대다. 실제 로직은
후속 티켓에서 채운다. 설계 권위 문서는 저장소 루트 `CLAUDE.md`이고, 한글 근거는
[`docs/design/care-bot-design.md`](../../docs/design/care-bot-design.md)에 있다.

### config.py 와 policy.py 를 합치지 않는다

성격과 수명이 다르다.

| 파일 | 무엇이 들어가나 | 언제 바뀌나 |
|---|---|---|
| `config.py` | 환경변수 로딩과 검증 (API 키, DB 주소, 장치 선택자) | 배포 환경을 옮길 때 |
| `policy.py` | 정책 상수 (우선순위 행렬, 쿨다운, TTL, 침묵 사다리 임계치) | "로봇이 너무 잔소리한다" 같은 제품 판단이 바뀔 때 |

모든 임계치는 `policy.py`에 두고 함수 본문에 박지 않는다. 상수마다 "올리면/내리면"
어떻게 되는지 주석으로 적는다(CLAUDE.md §21).

## 요구 사항

- Python 3.10 이상 3.13 미만
- PortAudio 호환 마이크와 스피커
- RTZR, SSAFY GMS Gemini, Typecast 자격증명
- 날씨 기능 사용 시 기상청 API 키
- 의료 조회 사용 시 현재 스키마의 PostgreSQL 데이터베이스
  - `hospital`, `pharmacy`, `drug_permit` 테이블
  - 의약품 유사 검색을 위한 `pg_trgm`의 `word_similarity`

의료·날씨 의도 판정은 로컬 결정 규칙이라 모델 다운로드나 네트워크가 필요 없다.
제거한 SentenceTransformer 라우터와 비교 평가할 때만 `router-eval` 선택 의존성을
설치하고 `evals/evaluate_router.py --legacy-model`을 실행한다.

## 설치

명령은 저장소의 `robot/ai_chat`에서 실행한다.

### Windows PowerShell

```powershell
cd robot\ai_chat
py -3.10 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,mqtt]"
Copy-Item .env.example .env
```

### Ubuntu 22.04 / Jetson

```bash
cd robot/ai_chat
sudo apt-get update
sudo apt-get install -y python3.10-venv libportaudio2
python3.10 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev,mqtt]"
cp .env.example .env
```

### Jetson(aarch64) 설치 주의

Jetson 의 CPU 는 ARM 64비트(aarch64)이고 개발 PC 는 x86 이다. **컴파일된 프로그램은
두 아키텍처 사이에서 호환되지 않는다.** 실무적으로 두 가지 결과가 따라온다.

- pip 는 보통 미리 컴파일된 **휠(wheel)** 을 설치한다. ARM 휠이 없으면 소스에서
  컴파일하는데, 느리고 빌드 의존성이 없으면 그냥 실패한다.
- 네이티브 확장은 패키지 매니저 한 줄이 아니라 `make && make install` 이 필요할 수 있다.

그래서 **`pip install -e .` 을 실기(Jetson)에서 반드시 한 번 돌린다.** "내 노트북에서는
됐는데"를 늦게 발견하면 비싸다. 이 저장소에서 특히 확인할 것:

| 패키지 | 확인 이유 |
|---|---|
| `psycopg2-binary` | aarch64 휠이 없으면 `libpq-dev` + 소스 빌드로 넘어간다 |
| `sounddevice` | `libportaudio2` 시스템 패키지가 먼저 있어야 한다 |
| `numpy`, `noisereduce` | 소스 빌드로 떨어지면 빌드가 오래 걸린다 |

`sentence-transformers`는 운영 의존성이 아니다. 비교 평가용 `router-eval` 옵션을
Jetson에 설치하면 torch가 필요하므로, 평가는 개발 PC에서 수행한다.

설치가 끝나면 임포트까지 확인한다. 설치 성공과 임포트 성공은 다른 문제다.

```bash
python -c "import bomi_ai_chat, langgraph, apscheduler; print('ok')"
```

설치 로그는 남겨둔다. aarch64 에서 어떤 패키지가 소스 빌드로 떨어졌는지가
이후 배포 시간을 결정한다.

## 환경변수

`.env.example`을 복사한 `.env`에 실제 값을 넣는다. 다른 파일을 사용하려면
`AI_CHAT_ENV_FILE`에 경로를 지정한다.

### 기본 대화

| 변수 | 필요 조건 | 기본값/설명 |
|---|---|---|
| `RTZR_CLIENT_ID` | 시작 시 필수 | RTZR STT 클라이언트 ID |
| `RTZR_CLIENT_SECRET` | 시작 시 필수 | RTZR STT 클라이언트 시크릿 |
| `GEMINI_API_KEY` | 시작 시 필수 | SSAFY GMS Gemini API 키 |
| `TYPECAST_API_KEY` | 시작 시 필수 | Typecast API 키 |
| `TYPECAST_VOICE_ID` | 선택 | 코드에 정의된 BOMI 기본 음성 |
| `KMA_API_KEY` | 날씨 조회 시 필수 | 기상청 단기예보 서비스 키 |

### 오디오

| 변수 | 기본값 | 설명 |
|---|---:|---|
| `AUDIO_MODE` | `laptop` | `laptop` 또는 `robot` |
| `AUDIO_INPUT_DEVICE` | OS 기본 장치 | PortAudio 입력 인덱스 또는 장치명 일부 |
| `AUDIO_OUTPUT_DEVICE` | OS 기본 장치 | PortAudio 출력 인덱스 또는 장치명 일부 |
| `AUDIO_SAMPLE_RATE` | `16000` | 녹음 샘플레이트 |
| `AUDIO_CHANNELS` | `1` | 녹음 채널 수 |
| `AUDIO_CHUNK_SECONDS` | `0.5` | 음량을 확인하는 청크 길이 |
| `AUDIO_SILENCE_THRESHOLD` | `300` | 이 값 미만을 무음으로 판단 |
| `AUDIO_SILENCE_LIMIT_SECONDS` | `3` | 연속 무음 후 녹음 종료 시간 |
| `AUDIO_MAX_SECONDS` | `15` | 한 차례의 최대 녹음 시간 |

`laptop`은 장치 선택자를 비워두면 운영체제 기본값을 사용한다. `robot`은
잘못된 기본 장치로 실행되는 것을 막기 위해 입력과 출력 장치를 모두
명시해야 한다.

대상 장치에서 PortAudio 목록을 확인한다.

```bash
python -c "import sounddevice as sd; print(sd.query_devices())"
```

확인한 인덱스 또는 고유한 장치명 일부를 `.env`에 넣는다.

```dotenv
AUDIO_MODE=robot
AUDIO_INPUT_DEVICE=1
AUDIO_OUTPUT_DEVICE=USB Audio
```

특정 Jetson 장치명은 저장소에 고정하지 않는다. 실제 마이크·스피커와
ALSA/PortAudio 구성을 대상 장치에서 확인해야 한다.

### 외부 호출

| 변수 | 기본값 | 설명 |
|---|---:|---|
| `HTTP_TIMEOUT_SECONDS` | `10` | 개별 HTTP 요청 제한시간 |
| `HTTP_MAX_ATTEMPTS` | `3` | 일시 장애를 포함한 최대 시도 횟수 |
| `HTTP_BACKOFF_SECONDS` | `0.5` | 첫 재시도 대기시간 |
| `HTTP_MAX_BACKOFF_SECONDS` | `2` | 재시도 대기시간 상한 |
| `STT_POLL_INTERVAL_SECONDS` | `0.5` | RTZR 결과 확인 간격 |
| `STT_POLL_TIMEOUT_SECONDS` | `60` | RTZR 전체 폴링 제한시간 |
| `STT_TOKEN_TTL_SECONDS` | `3000` | RTZR 인증 토큰 재사용 시간 |

### 의료 데이터베이스

의료 요청이 실제 DB 조회 단계에 도달할 때 연결 설정을 검증한다.

| 변수 | 필요 조건 | 기본값/설명 |
|---|---|---|
| `DB_CONNECTION_MODE` | 항상 | `ssh`; 로컬/직접 연결은 `direct` |
| `DATABASE_URL` | direct 선택 방식 | 전체 PostgreSQL URL |
| `DB_HOST` | direct 개별 설정 | `localhost` |
| `DB_PORT` | direct 개별 설정 | `5432` |
| `DB_NAME` | URL 미사용 또는 ssh | 필수 |
| `DB_USER` | URL 미사용 또는 ssh | 필수 |
| `DB_PASSWORD` | URL 미사용 또는 ssh | 필수 |
| `EC2_HOST` | ssh | SSH 서버 주소 |
| `EC2_SSH_USER` | ssh | `ec2-user` |
| `SSH_KEY_PATH` | ssh | SSH 개인키 경로 |
| `REMOTE_DB_HOST` | ssh | `localhost` |
| `REMOTE_DB_PORT` | ssh | `5432` |

direct 모드는 `DATABASE_URL` 하나를 사용하거나 `DB_HOST`부터
`DB_PASSWORD`까지 개별 값을 사용한다. ssh 모드는 SSH 터널을 연 뒤 로컬
포트로 PostgreSQL에 연결한다.

## 실행

한 차례만 실행:

```bash
python -m bomi_ai_chat --once
```

`Ctrl+C`를 누를 때까지 반복 실행:

```bash
python -m bomi_ai_chat
```

editable 설치 후 생성되는 명령도 동일하다.

```bash
bomi-ai-chat --once
```

필수 API 키 또는 robot 장치 설정이 없으면 오디오 장치를 불러오기
전에 설정 오류로 종료한다.

## 로컬 저장소와 보호자 알림 큐

### 무엇이 로컬에 사는가

로봇은 **운영 상태**만 로컬에 둔다. **사실(fact)** 은 백엔드 Postgres 가 권위다.

| 계층 | 소유 | 내용 |
|---|---|---|
| 사실 | 백엔드 Postgres | 프로필, 기억, 복약, 돌봄 기록, 동의 |
| 운영 상태 | **로봇 로컬 SQLite** | 발화 제안 큐, `silence_level`, `occupancy`, `last_spoke_at`, LangGraph checkpointer, 캐시 TTS 오디오, 보호자 알림 발신 큐 |

복약 스케줄의 진실이 두 곳에 있으면 품질 문제가 아니라 안전 버그다. 그래서 핸들러와
그래프 노드는 `sqlite3` 를 직접 만지지 않고 `localstore/` 를 통한다.

### DB 파일이 두 개인 이유

저장 매체가 microSD 라서 쓰기 내구성을 의도적으로 완화했다. 크래시 시 마지막 몇 초의
운영 상태를 잃는데, 그건 괜찮다. 그런데 **큐에 든 응급 알림은 잃으면 안 된다.**
SQLite 의 `synchronous` 는 DB 단위 설정이라 한 파일에서 테이블별로 나눌 수 없으므로
파일을 나눴다.

| 파일 | synchronous | 내용 |
|---|---|---|
| `runtime.sqlite` | `NORMAL` | 운영 상태, 제안 큐, checkpointer, 캐시 오디오 등록부 |
| `outbox.sqlite` | **`FULL`** | 보호자 알림 발신 큐 |

둘 다 WAL 모드다. 작은 쓰기 개수가 줄고, 읽기가 쓰기를 막지 않는다(재생 스레드와
스케줄러 틱이 동시에 접근한다).

### 보호자 알림은 항상 큐를 거친다

**전송보다 저장이 먼저다.** 끊긴 연결로 발사한 T1 알림은 그냥 사라지고, 하필 그
순간이 알림이 가장 중요한 순간일 수 있다.

```python
from bomi_ai_chat.localstore import outbox

outbox.enqueue("T1", {"reason": "no_response"})   # 동기 쓰기. 여기서 반환되면 살아남는다
```

전송은 `jobs.ticks.outbox_flush` 가 주기적으로 시도한다. 실패하면 백오프를 걸어
재시도하고, 늦게 도착한 알림은 **'지연됨'으로 표시**해서 보낸다 — 보호자가 "지금
벌어지는 일"과 "와이파이가 끊긴 두 시간 전 일"을 구분해야 한다.

**T1 은 시도 횟수로 포기하지 않는다.** T2·T3 는 `policy.OUTBOX_MAX_ATTEMPTS` 를
넘기면 포기하지만(어제의 요약을 영원히 재시도할 이유는 없다), 생명 안전 알림은 그
목록에 없다.

실제 채널(웹앱 푸시·SMS)은 후속 티켓이다. 지금은 `notify/` 의 로그 전용 어댑터가
자리를 지키며, 채널이 없다는 사실을 로그로 요란하게 남긴다(T1 은 WARNING).

### 일일 백업

카드는 언젠가 죽는다. 하루 한 번 복사해두면 잃는 것이 최대 하루치가 된다.

```bash
python -m bomi_ai_chat.localstore.dump /mnt/usb/bomi-backup
```

파일 복사(`cp`)를 쓰지 않는 이유는 WAL 때문이다. 방금 커밋된 내용이 아직 `-wal`
파일에만 있을 수 있어서, `.sqlite` 만 복사하면 최근 쓰기가 빠지거나 손상된 사본이
된다. 이 스크립트는 SQLite 백업 API 를 써서 프로세스를 멈추지 않고 일관된 사본을
만든다. cron 이나 systemd timer 로 하루 한 번 돌린다.

## 에코 억제와 barge-in

### ⚠️ 실기 검증이 남아 있습니다

판단 로직(에코 가드, 맞장구 판별, 재생 취소, 잔여분 재큐)은 하드웨어 없이 구현·검증했고
자동 테스트 20건이 고정하고 있습니다. 하지만 **임계치 두 개는 추정치이고 실측이
필요합니다.**

| 상수 | 현재값 | 상태 |
|---|---|---|
| `ECHO_GUARD_SEC` | 0.3 | 추정치 — 실측 필요 |
| `ECHO_VAD_THRESHOLD_MULTIPLIER` | 2.5 | 추정치 — 실측 필요 |

**이 값들을 실측하기 전에 능동 발화(206)를 실기에서 테스트하지 마십시오.** 에코를 안
잡은 상태에서는 모든 버그 리포트가 실제로는 에코이고, 게이트 버그로 오진하게 됩니다.

남은 항목 전체: [`docs/hardware/audio-echo-bargein-verification.md`](../../docs/hardware/audio-echo-bargein-verification.md)

### 두 겹으로 막는다

1. 재생 직후 `ECHO_GUARD_SEC` 동안은 입력을 아예 버린다
2. 재생이 이어지는 동안에는 VAD 임계치를 올린다 — **막지는 않는다**

2번이 핵심입니다. "재생 중에는 듣지 않는다"가 아니라 **"재생 중에는 더 크게 말해야
들린다"** 입니다. 완전히 막으면 barge-in 이 원리적으로 불가능해지고, 청력이 떨어진
어르신은 로봇이 말하는 중인 줄 모르고 말을 시작합니다.

### 진행 상황의 권위는 재생 핸들입니다

`speaking`·`spoken_prefix` 는 주인이 둘입니다 — 재생 스레드와 checkpoint 된 state.
CLAUDE.md 가 "시스템에서 동기화 버그가 가장 나기 쉬운 지점"이라고 못박은 곳입니다.

경계를 이렇게 고정했습니다:

- **재생 핸들(`SpeechPlayback`) = 진행 상황의 권위**
- **`ConvState` = 그 순간의 스냅샷**

barge-in 이 나면 `note_interaction` 은 state 가 아니라 **핸들에게** 몇 문장까지
말했는지 묻습니다. state 값은 그래프 실행 시점에 찍힌 것이라 이미 낡았을 수 있고,
낡은 값을 믿으면 이미 말한 문장을 다시 말합니다.

### critical 프로브는 재개하지 않습니다

생존 확인 프로브 중에 어르신이 끼어들면 **끼어든 것 자체가 답입니다.** 나머지를
일부러 버리고 침묵 사다리만 리셋합니다. 재개하면 방금 대답한 사람에게
"괜찮으세요?"를 다시 묻는 로봇이 됩니다.

## 주입 시계와 SimClock

이 패키지에서 **실제 시계를 읽는 파일은 `clock.py` 하나뿐이다.** 다른 곳에서
`time.time()` 이나 `datetime.now()` 를 호출하지 않는다(CLAUDE.md §15, §23).

### 왜 이 제약이 있나

침묵 사다리는 "3시간 무응답 → 45분 → 20분" 단위로 동작하고 일일 요약은 하루 단위다.
실제 시계로 검증하면 테스트 한 번에 몇 시간에서 하루가 걸려서 개발도 시연도 불가능하다.
시계를 주입할 수 있으면 하루가 10초에 흐르고, 둘 다 평범한 단위 테스트가 된다.

나중에 넣는 건 훨씬 어렵다. 그때는 이미 수십 곳에서 시계를 직접 읽고 있다.

### 쓰는 방법

시간을 읽어야 하면 `clock` 싱글톤을 import 한다.

```python
from bomi_ai_chat.clock import clock

elapsed = clock.now() - state["last_spoke_at"]   # POSIX 초(float), UTC
today = clock.now_dt()                            # tz-aware datetime
```

### 압축 시계 (시연)

`speed` 배율로 가상 시간을 빠르게 흘린다. 8640 이면 하루가 10초다.

```python
from bomi_ai_chat.clock import SimClock, clock, install_clock

previous = install_clock(SimClock(start=clock.now(), speed=8640))
# ... 이제 clock.now() 는 실제 10초에 하루씩 전진한다
install_clock(previous)   # 끝나면 실제 시계를 복원한다
```

### 점프 (단위 테스트)

`advance()` 는 기다림 없이 검증하고 싶은 시점으로 즉시 점프한다. 테스트에서는
`speed` 보다 이 방식이 낫다. 실제 경과 시간에 의존하지 않아 결과가 흔들리지 않는다.

```python
sim = SimClock(start=1_700_000_000.0)
previous = install_clock(sim)
try:
    sim.advance(3 * 3600)      # 3시간 뒤로 점프. sleep 없음
    # 침묵 사다리 1단계 판정을 여기서 확인한다
finally:
    install_clock(previous)    # 전역 상태이므로 복원은 필수다
```

### 주의사항

- **APScheduler 는 여전히 실제 시간에 발동한다.** SimClock 을 빠르게 해도 스케줄
  작업이 빨라지지 않는다. 압축 시계 검증은 `jobs/ticks.py` 의 틱 함수를 직접 호출한다.
  그래서 주기 작업은 스케줄러 경로와 수동 틱 경로를 처음부터 함께 설계한다.
- `clock` 은 모듈 전역이다. 테스트가 교체했으면 **반드시 복원한다.** 안 하면 이후
  테스트가 가짜 시계를 물려받는다.
- 다른 기계에서 온 타임스탬프(현관 라즈베리파이)를 그대로 섞지 않는다. 도착 시점에
  `clock.now()` 로 정규화한다. 그러지 않으면 한 계산에 두 개의 시간축이 섞인다.

## 테스트

기본 검증은 실제 네트워크, DB, 마이크, 스피커를 사용하지 않는다.

```bash
python -m pytest -m "not integration and not manual"
python -m ruff check src tests
```

실제 연동은 필요한 항목만 운영자가 실행한다. 명령과 주의사항은
[`tests/manual/README.md`](tests/manual/README.md)를 참고한다. 실행하지 않은
외부 점검은 통과로 기록하지 않는다.

## 의료 안내 안전 정책

- 지역명이나 정확한 시설명이 없는 병원·약국 요청은 DB를 조회하지 않고
  위치를 다시 묻는다.
- 부분 일치 시설은 주소나 전화번호를 안내하기 전에 시설명을 확인한다.
- 보정된 약 이름은 상세 성분을 안내하기 전에 사용자 확인을 받는다.
- DB 결과가 없을 때 Gemini의 사전지식으로 의료 정보를 보충하지 않는다.
- 검색 결과 없음과 DB 장애를 서로 다른 상태로 처리한다.

## 범위

### MVP

- RTZR STT → Gemini 일반/의료 응답 → Typecast TTS
- 기상청 지원 도시 날씨
- direct/SSH PostgreSQL 의료 조회
- 위치·부분 일치·약 이름 보정 안전장치
- 단발 및 복구 가능한 반복 대화
- laptop/robot PortAudio 어댑터
- 외부 장치 없이 실행하는 단위 테스트

### FUTURE

- ROS 노드와 토픽 연결
- MQTT·백엔드 대화 계약
- 사용자별 장기 기억과 대화 이력 저장
- GPS 기반 실제 거리순 의료기관 검색
- 스트리밍 STT·LLM·TTS
- 다중 사용자·동시 요청 처리

공공 의료데이터 수집은 현재 AI Chat 런타임의 책임이 아니다. 데이터 갱신이
필요하면 별도 적재 파이프라인과 소유권을 먼저 정의한다.
