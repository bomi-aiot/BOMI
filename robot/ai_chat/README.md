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
├─ llm/        Gemini 일반 대화, 의료 도구 호출, 임베딩 라우터
├─ stt/        RTZR 인증·업로드·제한 폴링
├─ tts/        Typecast WAV 생성
├─ weather/    기상청 단기예보 조회
├─ config.py   환경변수 로딩과 기능별 검증
├─ pipeline.py 한 차례 및 반복 대화 조율
└─ main.py     CLI 옵션과 의존성 조립
tests/         네트워크·DB·오디오 장치 없이 실행하는 단위 테스트
tests/manual/  운영자가 직접 실행하는 외부 연동 점검
```

## 요구 사항

- Python 3.10 이상 3.13 미만
- PortAudio 호환 마이크와 스피커
- RTZR, SSAFY GMS Gemini, Typecast 자격증명
- 날씨 기능 사용 시 기상청 API 키
- 의료 조회 사용 시 현재 스키마의 PostgreSQL 데이터베이스
  - `hospital`, `pharmacy`, `drug_permit` 테이블
  - 의약품 유사 검색을 위한 `pg_trgm`의 `word_similarity`

`sentence-transformers` 모델이 로컬에 없다면 첫 의료 판별 시 모델 다운로드를
위한 네트워크가 필요하다. 운영 장치에서는 배포 단계에서 모델을 미리
캐시하는 편이 안전하다.

## 설치

명령은 저장소의 `robot/ai_chat`에서 실행한다.

### Windows PowerShell

```powershell
cd robot\ai_chat
py -3.10 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
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
python -m pip install -e ".[dev]"
cp .env.example .env
```

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

필수 API 키 또는 robot 장치 설정이 없으면 오디오·임베딩 모델을 불러오기
전에 설정 오류로 종료한다.

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
