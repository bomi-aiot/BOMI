# 실기 점검 — S15P11E102-233

> **이 문서는 읽기만 합니다.** 무엇을 하고 무엇이 나와야 하는지가 적혀 있습니다.
> **적는 곳은 따로 있습니다** → [`FIELD-TEST-233-RESULT.md`](FIELD-TEST-233-RESULT.md)
>
> 두 파일을 오가야 하지만, 결과지는 빈칸만 있어 짧습니다. 스텝 번호(`5-8` 같은 것)가
> 양쪽에 똑같이 붙어 있으니 그것으로 찾으십시오.

## 이 점검의 목적은 실패를 찾는 것입니다

전부 잘 돌아갔다는 결과가 나오면 **충분히 안 해본 것**입니다. 자동 테스트가 이미 그 범위를
덮고 있습니다.

| 자동 테스트가 보는 것 | 실기에서만 보이는 것 |
| --- | --- |
| "에코라고 판정했을 때 올바르게 행동하는가" | **무엇을 에코로 볼 것인가**(임계치) |
| 프롬프트에 회피 목록이 들어갔는가 | 실제 모델이 그것을 지키는가 |
| 문장 분할이 맞는가 | 그 문장이 **소리로** 자연스러운가 |
| 사다리가 3시간에 올라가는가 | 3시간이 **적절한 값인가** |
| ASR 텍스트가 들어오면 | **어르신 발음을 ASR 이 어떻게 망가뜨리는가** |

마지막이 가장 큽니다. 지금 **모든 판정**(응급 표현 목록, 동의 판정, 지남력 표지, 맞장구)이
**깨끗한 텍스트를 전제**하고 있습니다.

## 목차

| 절 | 무엇 | 대략 | 마이크 |
| --- | --- | --- | --- |
| [0. 준비](#0-준비) | 로그·환경·장치·전용 어르신 | 40분 | 일부 |
| [1. 창 배치](#1-창-배치--네-개를-띄웁니다) | 어디를 보는가 | 10분 | ✕ |
| [2. 외부 API](#2-외부-api-단독-점검) | STT·TTS·LLM 을 따로따로 | 20분 | ✓ |
| [3. 에코](#3-에코--여기를-건너뛰면-이후가-전부-오염됩니다) | **먼저 잡습니다** | 40분 | ✓ |
| [4. 한 바퀴](#4-한-바퀴-돌리기) | 마이크→스피커 왕복·지연 | 30분 | ✓ |
| [5. 발화 매트릭스](#5-발화-매트릭스--이-점검의-본체) | **42개 발화** | 90분 | ✓ |
| [6. 말 끊기](#6-말-끊기와-맞장구) | barge-in | 30분 | ✓ |
| [7. 게이트·사다리](#7-게이트와-침묵-사다리) | 능동 발화 | 40분 | 일부 |
| [8. 트리아지·알림](#8-트리아지에서-보호자까지) | T1 이 끝까지 가는가 | 30분 | ✓ |
| [9. 계약 대화](#9-계약-대화-온보딩재질의) | 온보딩·동의 | 30분 | ✓ |
| [10. 현관](#10-현관-mqtt) | MQTT | 20분 | ✕ |
| [11. 의미 검색](#11-의미-검색--과금-주의) | 이어짐·회상 | 30분 | ✓ |
| [정리](#정리--발견한-것을-세-갈래로-나눕니다) | 분류·되돌리기 | 20분 | ✕ |

**셸은 Git Bash(MINGW64) 기준입니다.** 이 문서의 명령은 전부 bash 입니다. PowerShell 을
쓰신다면 `tail -f` 는 `Get-Content -Wait -Tail`, `grep` 은 `Select-String` 으로 바꿔야
합니다. (초판은 PowerShell 로 적혀 있었고, 점검 중에 `bash: Get-Content: command not found`
로 막혔습니다. **문서의 명령이 안 도는 것은 체크리스트에서 가장 나쁜 오류입니다.**)

---

# 0. 준비

## 0-1. 브랜치가 맞는가

```bash
cd /c/Users/workspaces/S15P11E102 && git branch --show-current && git log --oneline -1
```

**기대**: `S15P11E102-233-ai-실기-점검`

> **왜 이 브랜치여야 하는가.** 두 가지가 여기에만 있습니다.
>
> 1. **로그.** `ai-develop` 의 `main.py` 는 `logging.basicConfig` 가 주석 처리돼 있고
>    `-v` 옵션이 없습니다. 그 상태로 로봇을 켜면 대답 소리는 들리지만 **어느 함수가
>    돌았는지, 갈래가 뭐로 정해졌는지, 지연이 얼마인지 볼 방법이 전혀 없습니다.**
>    눈을 감고 점검하는 셈입니다.
> 2. 이 문서와 `tests/manual/probe.py`.

## 0-2. 자동 테스트가 먼저 초록인가

```bash
cd robot/ai_chat && ./venv/Scripts/python.exe -m pytest -m "not integration and not manual" -q
```

```bash
cd robot/ai_chat && ./venv/Scripts/ruff.exe check src tests
```

**기대**: 테스트 전부 통과 + `All checks passed!`

> 빨간 것이 있으면 실기로 가지 않습니다. 실기에서 발견한 것이 **코드 문제인지 환경 문제인지
> 구분할 수 없게** 됩니다.

## 0-3. `.env` 채우기

`robot/ai_chat/.env` 입니다. 없으면 `.env.example` 을 복사합니다.

| 변수 | 이번 점검에서 넣을 값 | 없으면 |
| --- | --- | --- |
| `RTZR_CLIENT_ID` / `_SECRET` | (발급값) | 음성 인식 불가 |
| `GEMINI_API_KEY` | (발급값) | 문장 생성 불가 |
| `TYPECAST_API_KEY` | (발급값) | 음성 합성 불가 |
| `SENIOR_ID` | **0-4 에서 만들 전용 UUID** | 기동 거부 |
| `BACKEND_BASE_URL` | `https://i15e102.p.ssafy.io` | 문맥이 캐시로만 |
| `BACKEND_TIMEOUT_SECONDS` | `3.0` (기본 1.5 에서 올림) | 아래 설명 |
| `AUDIO_MODE` | **`robot`** | — |
| `AUDIO_INPUT_DEVICE` / `_OUTPUT_DEVICE` | **0-5 에서 확인한 번호** | `robot` 모드는 기동 거부 |
| `WAKEWORD_ENABLED` | **`0`** (5절까지) | 발화마다 "보미야"를 붙여야 함 |
| `LOCALSTORE_DIR` | `var/localstore` (기본) | — |

**왜 `AUDIO_MODE=robot` 인가.** `laptop` 모드는 장치를 비워두면 운영체제 기본 장치를 씁니다.
그러면 **외부 마이크를 꽂아 놓고도 노트북 내장 마이크로 조용히 녹음될 수 있고**, 그 상태로
잰 에코 임계치는 전부 거짓입니다. `robot` 모드는 장치 번호를 반드시 쓰게 만들어 이 사고를
막습니다. 젯슨에서 돌 때와 같은 경로이기도 합니다.

**왜 `BACKEND_TIMEOUT_SECONDS` 를 올리는가.** 기본값 1.5초는 백엔드가 같은 기계에 있을 때의
값입니다. 지금은 노트북에서 인터넷을 건너 EC2 까지 갑니다. 그대로 두면 문맥 조회가 자주
실패해 캐시로 떨어지고, **로봇이 기억을 못 하는 것처럼 보이는데 원인은 타임아웃**입니다.

## 0-4. 테스트 전용 어르신 만들기

**왜 전용으로 만드는가.** 이 점검은 EC2 데이터베이스에 진짜 행을 씁니다 — 대화 기록, 보호자
알림, 현관 이벤트. 시연용 데이터(김순자)에 섞이면 나중에 어느 것이 시연 데이터이고 어느
것이 점검 흔적인지 구분할 수 없습니다.

먼저 실제 필수 칼럼을 확인합니다. 여기에 고정해서 적으면 스키마가 바뀌는 순간 거짓말이
되므로, 직접 보고 채우십시오.

```bash
ssh bomi "docker exec bomi-postgres psql -U bomi -d bomi -c '\d app_user'"
```

확인한 칼럼으로 한 행을 만듭니다.

```bash
ssh bomi "docker exec -i bomi-postgres psql -U bomi -d bomi" <<'SQL'
INSERT INTO app_user (id, user_type, name /*, 확인한 필수 칼럼들 */)
VALUES ('99999999-0000-4000-8000-000000000001', 'SENIOR', '점검용' /*, ... */);
SQL
```

만든 UUID 를 `.env` 의 `SENIOR_ID` 와 셸 변수에 둘 다 넣습니다.

```bash
export SENIOR_ID=99999999-0000-4000-8000-000000000001
```

- [ ] 결과지 **0-4** 에 UUID 를 적었습니다 (마지막에 정리할 때 필요합니다)

## 0-5. 오디오 장치 번호 확인

```bash
cd robot/ai_chat && ./venv/Scripts/python.exe tests/list_audio_devices.py
```

**기대**: 꽂아 둔 외부 마이크와 스피커가 목록에 보이고, 마이크는 `in>0`, 스피커는 `out>0`.

**내장 마이크와 헷갈리지 마십시오.** 이름이 비슷하면 외부 장치를 뽑았다 꽂으면서 목록이
어떻게 바뀌는지로 구분합니다.

## 0-6. EC2 에 닿는가 — ★ 상태 코드로 판정하지 않습니다

```bash
curl -s -o /tmp/ctx.json -w '%{http_code}  %{content_type}\n' \
  -X POST https://i15e102.p.ssafy.io/api/v1/seniors/$SENIOR_ID/conversation-context \
  -H 'Content-Type: application/json' -d '{"query":"테스트","memoryTopK":3}'
head -c 200 /tmp/ctx.json; echo
```

**기대**

```
200  application/json
{"profile":{...},"todayState":...,"availability":{...
```

| 실제로 이게 나오면 | 뜻 | 어디를 고치나 |
| --- | --- | --- |
| `200  text/html` + `<!doctype html>` | 🔴 **경로가 프론트엔드로 갔습니다.** 200 이지만 실패입니다 | 경로 오타. `/api/v1/...` 인지 확인 |
| `404` | nginx 는 붙었는데 백엔드 라우팅이 다름 | 백엔드 로그 (창 4) |
| `500` 또는 빈 본문 | `SENIOR_ID` 가 `app_user` 에 없음 | 0-4 로 |
| 5초 넘게 걸림 | 문맥 조회가 매 턴 캐시로 떨어질 것 | `BACKEND_TIMEOUT_SECONDS` |

> **왜 상태 코드를 믿으면 안 되는가.** nginx 는 `/api/` 로 시작하는 요청만 백엔드로 넘기고,
> 나머지는 전부 프론트엔드로 보냅니다. 프론트엔드는 어떤 경로를 받아도 화면(HTML)을
> **200 으로** 돌려줍니다. 그래서 경로에 오타가 있으면 "성공"으로 보입니다.
>
> **`curl https://.../actuator/health` 도 쓰지 마십시오.** nginx 가 `/actuator` 를 일부러
> 404 로 막아 두었습니다. 살아있는지는 위 명령이나 0-7 로 봅니다.

## 0-7. 컨테이너가 도는가

```bash
ssh bomi "docker ps --format '{{.Names}}\t{{.Status}}'"
```

**기대**: `bomi-backend`, `bomi-postgres`, `bomi-nginx` 가 `healthy` 또는 `Up`.

`bomi-qdrant` 와 `bomi-mosquitto` 는 **이 목록에 없을 수도 있습니다.**
`infra/compose.prod.yml` 에 정의가 없어서, 어떻게 떠 있는지(또는 안 떠 있는지) 저장소로는
알 수 없습니다. 없으면 **10절(현관)과 11절(의미 검색)을 건너뛰고 결과지에 그렇게 적습니다.**

- [ ] 결과지 **0-7** 에 실제 목록을 붙여넣었습니다

## 0-8. 상태 도구가 도는가

```bash
cd robot/ai_chat && ./venv/Scripts/python.exe tests/manual/probe.py
```

**기대**: 표가 그려집니다. `runtime_state 에 행이 없습니다` 가 나와도 정상입니다 — 로봇을
아직 안 띄웠으니까요.

**한글이 깨지면 여기서 멈추고 고칩니다.** 점검 내내 이 도구를 쓰는데, 출력이 안 읽히면
점검이 안 됩니다.

---

# 1. 창 배치 — 네 개를 띄웁니다

## 창 1 — 로봇 (여기서 말합니다)

```bash
cd /c/Users/workspaces/S15P11E102/robot/ai_chat && ./venv/Scripts/python.exe -m bomi_ai_chat -v
```

기동할 때 이런 줄들이 보여야 합니다.

```
INFO  bomi_ai_chat.main: logging to var\localstore\logs\ai_chat.log
INFO  bomi_ai_chat.jobs.scheduler: scheduler built: silence/door=60s outbox=30s
INFO  bomi_ai_chat.bootstrap: conversation runtime ready (senior=9999...)
WARNING ... self-harm marker list has not been human-reviewed yet
```

마지막 경고는 **정상**입니다 — 자해 표현 감지는 동작하지만 사람의 검토가 아직 안 끝났다는
뜻입니다 (8-3 에서 처리합니다).

## 창 2 — 로그 실시간

```bash
cd /c/Users/workspaces/S15P11E102/robot/ai_chat && tail -f -n 0 var/localstore/logs/ai_chat.log
```

판정 이유만 보고 싶을 때:

```bash
tail -f -n 0 var/localstore/logs/ai_chat.log | grep -E "latency|intent|safety|echo|gate|ladder|occupancy|cache"
```

창 1은 INFO 이상, **이 파일은 항상 DEBUG** 입니다.

## 창 3 — 로컬 상태

발화 하나마다 이 두 명령을 씁니다. 창을 따로 띄워 두고 여기서만 칩니다.

```bash
cd /c/Users/workspaces/S15P11E102/robot/ai_chat
./venv/Scripts/python.exe tests/manual/probe.py --save              # 말하기 전
./venv/Scripts/python.exe tests/manual/probe.py --diff --step 5-8   # 말한 뒤
```

무엇이 어디에 쌓이는지는
[`TRACE-MAP.md` §4](TRACE-MAP.md#4-저장소-지도--무엇이-어디에-쌓이는가) 에 있습니다.

## 창 4 — 백엔드

```bash
ssh bomi "docker logs -f --tail 40 bomi-backend"
```

서버 데이터베이스 확인 명령들:

```bash
# 대화가 쌓이는가
ssh bomi "docker exec bomi-postgres psql -U bomi -d bomi -c \"SELECT role, left(content,40) AS content, trigger_type, occurred_at FROM conversation_message ORDER BY occurred_at DESC LIMIT 10;\""
```

```bash
# 보호자 알림이 도착했는가
ssh bomi "docker exec bomi-postgres psql -U bomi -d bomi -c \"SELECT notification_tier, occurred_at, details->>'reason' AS reason FROM care_record WHERE record_type='GUARDIAN_ALERT' ORDER BY occurred_at DESC LIMIT 10;\""
```

---

# 2. 외부 API 단독 점검

**왜 따로 먼저 하는가.** 대화 한 번은 음성인식 → 문장생성 → 음성합성, 세 개의 외부
서비스를 거칩니다. 여기서 막힌 것을 모르고 4절로 가면, 음성인식 문제를 "갈래 판정이
이상하다"로 오진합니다. **어느 것이 고장인지 먼저 가려 놓아야** 합니다.

```bash
cd robot/ai_chat
./venv/Scripts/python.exe tests/manual/audio_smoke.py    # 녹음·재생
./venv/Scripts/python.exe tests/manual/stt_smoke.py      # 음성 → 텍스트
./venv/Scripts/python.exe tests/manual/tts_smoke.py      # 텍스트 → 음성
./venv/Scripts/python.exe tests/manual/llm_smoke.py      # 문장 생성
```

## 2-1. 스피커에서 진짜 소리가 나는가

**로그만 보고 판단하지 마십시오.** 잭이 비어 있어도 오디오 장치는 정상으로 열리고 재생도
정상으로 끝납니다. 로그로는 영원히 알 수 없고 **귀로만 확인됩니다.**

## 2-2. ★ ASR 이 무엇을 망가뜨리는가

`stt_smoke.py` 를 **세 번** 실행하고, 같은 문장을 다르게 말합니다.

**말할 문장** ▶ `"오늘 날씨가 참 좋네요"`

| # | 말하는 방식 | 왜 |
| --- | --- | --- |
| 1 | 또박또박 | 기준선 |
| 2 | 빠르게, 흘리듯 | 조사가 떨어져 나갑니다 |
| 3 | 사투리 / 낮은 목소리 | **78세 어르신의 발음은 1번보다 3번에 가깝습니다** |

- [ ] 결과지 **2-2** 에 세 결과를 그대로 적었습니다

> 3번이 심하게 망가진다면, 5절의 모든 판정이 그만큼 흔들린다는 뜻입니다. 그 사실을
> **먼저** 알고 5절에 들어가야 합니다.

---

# 3. 에코 — 여기를 건너뛰면 이후가 전부 오염됩니다

**에코란**: 로봇의 스피커에서 나온 소리가 같은 몸통의 마이크로 되돌아 들어오는 것입니다.
그러면 로봇이 **자기 말을 어르신의 말로 착각하고 스스로 멈춥니다.**

이걸 안 잡고 4~11절을 하면 "게이트가 이상하다", "사다리가 안 돈다" 같은 관찰이 대부분
사실은 에코입니다. **그래서 3절이 4절보다 먼저입니다.**

## 3-1. 로봇이 자기 말에 멈추는가

```bash
cd robot/ai_chat && ./venv/Scripts/python.exe -m bomi_ai_chat --once -v
```

**말할 것** ▶ `"안녕하세요"` 한 마디. 그 뒤 로봇이 말하는 동안 **아무 말도 하지 않습니다.**

| 기대 | 실패의 모습 |
| --- | --- |
| 로봇이 문장을 끝까지 말합니다 | 중간에 뚝 끊깁니다 |

**끊긴다면** 순서대로 시도합니다.

1. 스피커와 마이크를 물리적으로 떼어 놓습니다 (가장 효과 큼)
2. 스피커 볼륨을 낮춥니다
3. `policy.ECHO_GUARD_SEC` (132줄) 을 올립니다 — 로봇이 말을 시작한 뒤 몇 초간 마이크
   입력을 무시할지
4. `policy.ECHO_VAD_THRESHOLD_MULTIPLIER` (146줄) 를 올립니다 — 재생 중에는 얼마나 큰
   소리여야 "사람이 말한다"로 볼지

- [ ] 결과지 **3-1** 에 거리·볼륨·최종 임계치를 적었습니다

> **이 값들은 되돌리지 않습니다.** 실측값이므로 그대로 커밋합니다.

---

# 4. 한 바퀴 돌리기

```bash
cd robot/ai_chat && ./venv/Scripts/python.exe -m bomi_ai_chat -v
```

## 4-1. 왕복이 되는가

**말할 것** ▶ `"안녕하세요"`

| 어디 | 기대 |
| --- | --- |
| 스피커 | 대답이 들립니다 |
| 창 1 | `turn latency N.NNNs (senior=... intent=companion)` |
| 창 3 (`probe --diff`) | `occupancy` 가 `UNKNOWN` → `HOME` |
| 창 4 | `conversation_message` 에 2행 |

`occupancy` 가 `HOME` 이 되는 이유: 목소리가 들렸다면 집에 있는 것입니다. 발화가 현관
센서보다 우선합니다.

## 4-2. 지연이 예산 안인가

같은 말을 5번 하고 `turn latency` 를 적습니다.

**기대**: 5회 중 4회 이상이 **2.0초 이내** (`policy.TURN_LATENCY_BUDGET_SEC`, 501줄).

넘으면 창 2에서 단계별 내역을 봅니다. 대개 네트워크(문맥 조회·문장 생성·음성 합성)이고
로컬 계산이 아닙니다.

- [ ] 결과지 **4-2** 에 5회 측정값과 가장 느린 단계를 적었습니다

## 4-3. 문맥이 캐시로 떨어지지 않는가

```bash
grep -c "falling back to cache" var/localstore/logs/ai_chat.log
```

**기대**: `0`

0 이 아니면 백엔드에 못 닿고 있고, **로봇의 기억이 얕아진 상태로 5절 전체를 하게 됩니다.**
`BACKEND_TIMEOUT_SECONDS` 를 더 올리거나 0-6 을 다시 확인하십시오.

---

# 5. 발화 매트릭스 — 이 점검의 본체

42개 발화를 소리 내어 말하고 결과를 봅니다. **12개는 전체 형식**(경로·발화·로컬 저장소·
API·서버 저장소)으로, **나머지 30개는 표 한 줄**로 판정합니다.

전체 목록과 각 발화의 기대값은
[`TRACE-MAP.md` §1.2](TRACE-MAP.md#12-발화-42개--기대-결과) 에 있습니다. 여기서는 **전체
형식 12개**만 펼칩니다.

준비:

- `WAKEWORD_ENABLED=0` 인지 확인 (매 발화마다 "보미야"를 붙이면 이 절이 못 굴러갑니다)
- 창 2를 이렇게 걸어 둡니다:

```bash
tail -f -n 0 var/localstore/logs/ai_chat.log | grep -E "transcribe|intent|safety|latency"
```

**표기 규칙** (DB 접근 칸)

| 표기 | 뜻 |
| --- | --- |
| 🟢 읽기 | 값을 가져다 쓰기만 합니다 |
| 🔵 쓰기(로컬) | 로봇 안 SQLite. 네트워크 불필요 |
| 🟣 쓰기/읽기(서버) | HTTP 로 EC2. 끊기면 못 합니다 |
| ⚪ 없음 | 데이터베이스를 안 건드립니다 |

---

## 5-1. `"오늘 며칠이야"` — 가장 흔한 질문

> **왜 이것부터인가.** 지남력 질문(오늘이 며칠인지, 지금 몇 시인지)은 어르신이 가장 자주
> 하는 질문 유형이고, 초기 치매가 있으면 더 잦아집니다. 여기가 안 되면 제품의 가장 흔한
> 사용 장면이 안 되는 것입니다.

**말할 것** ▶ `"오늘 며칠이야"`

대체 문장: `"지금 몇 시야"` `"오늘 무슨 요일이지"` `"여기가 어디야"`

**예상 경로 — 어떤 함수가 어떤 순서로, 어디를 건드리는가**

| 순서 | 실행되는 함수 | 파일 | 하는 일 | DB 접근 |
| --- | --- | --- | --- | --- |
| 1 | `route_ingress` | `graph/ingress.py` | 어르신 발화 갈래로 보냄 | ⚪ |
| 2 | `note_interaction` | `graph/ingress.py` | 침묵 시계 리셋, 재실 갱신 | 🔵 `runtime.sqlite` / `runtime_state` **쓰기** |
| 3 | `safety_triage` | `graph/triage.py` | 응급 판정 → `none` | ⚪ |
| 4 | `context_read` | `graph/context.py` | 문맥 받아옴 | 🟣 EC2 **읽기** + 🔵 `context_cache` **쓰기** |
| 5 | `classify_intent` | `graph/context.py` | 갈래 → `info` | ⚪ |
| 6 | `handle_info` | `graph/handlers.py` | **LLM 호출 1회** | ⚪ |
| 7 | `response_shaper` | `graph/output.py` | 짧게 다듬음 | ⚪ |
| 8 | `memory_write` | `graph/build.py` | 턴 기록 | 🟣 EC2 **쓰기** ×2 + 🔵 `runtime_state` **쓰기** |
| 9 | `emit` | `graph/output.py` | 재생 시작 | ⚪ |

**예상 발화**: 오늘 날짜를 한두 문장으로. 따뜻하게.

**예상 로컬 저장소 변화**

| 파일 | 표 | 칼럼 | 이전 | 이후 |
| --- | --- | --- | --- | --- |
| `runtime.sqlite` | `runtime_state` | `occupancy` | `UNKNOWN` | `HOME` |
| 〃 | 〃 | `last_user_interaction_at` | `0` | 지금 |
| 〃 | 〃 | `last_spoke_at` | `0` | 지금 |
| 〃 | 〃 | `safety_check_until` | `0` | **`0` 유지** |
| `outbox.sqlite` | `outbox` | (행 수) | 0 | **0 유지** |

**예상 API**

| 방향 | 경로 | 횟수 |
| --- | --- | --- |
| 로봇 → BE | `POST /api/v1/seniors/{id}/conversation-context` | 1 |
| 로봇 → BE | `POST /api/v1/robot/conversation-events` | 2 |

**예상 서버 저장소**: `conversation_message` **+2행**, `orientation_question` 플래그 `true`

**결과지** ▶ **5-1**

**안 맞으면 여기**

| 증상 | 어디 | 무엇을 바꾸면 |
| --- | --- | --- |
| 갈래가 `companion` 으로 감 | `context.py` `_INFO_MARKERS` | `"며칠"` 이 목록에 있는지. ASR 이 다르게 받아썼을 수도 |
| 날짜가 틀림 | 프롬프트의 현재 시각 주입 | 로봇 기계의 시계가 맞는지 |
| 서버에 행이 안 쌓임 | `.env` `BACKEND_BASE_URL` | 0-6 으로 |

---

## 5-2. 같은 질문을 5분 안에 세 번

> **왜 이것을 시험하는가.** 초기 치매가 있으면 같은 질문을 반복합니다. **열 번째 질문도
> 첫 번째와 똑같이 따뜻하게** 답해야 합니다. 여기서 로봇이 "아까 말씀드렸듯이" 같은 말을
> 하면, 어르신은 자기가 반복했다는 것을 지적당한 것이고 그 로봇에게 다시 묻지 않게 됩니다.
>
> 동시에, **반복 횟수는 기록되어야** 합니다. 반복이 늘어나는 것은 인지 저하의 이른
> 신호이기 때문입니다. 이 둘을 동시에 하려면 나눠야 합니다 — 로봇은 매번 똑같이 답하고
> (프롬프트는 반복 횟수를 아예 모릅니다), 서버가 그 반복을 셉니다.

**말할 것** ▶ `"오늘 며칠이야"` 를 5분 안에 **세 번**

| 확인 | 정상 | 실패 |
| --- | --- | --- |
| 세 번의 어조 | 전부 똑같이 따뜻함 | "아까", "또", "이미" 같은 말이 섞임 |
| 문장 | 조금씩 달라도 됨 | 짜증 기미가 보이면 반복 횟수가 프롬프트로 샌 것 |
| 서버 | `orientation_question=true` 인 행이 3개 | 안 세고 있으면 추세를 못 만듦 |

```bash
ssh bomi "docker exec bomi-postgres psql -U bomi -d bomi -c \"SELECT content, orientation_question FROM conversation_message WHERE role='SENIOR' ORDER BY occurred_at DESC LIMIT 5;\""
```

**결과지** ▶ **5-2** (세 응답을 그대로 적습니다)

---

## 5-3. `"오늘 몇 도야"` — 🔴 예상값이 '결함' 입니다

> **여기서 로봇은 그럴듯하게 대답합니다. 그리고 그게 틀린 답입니다.**
>
> `handle_info` 의 본문은 `return {"response": _generate(state)}` 한 줄뿐입니다. 즉 LLM 을
> 한 번 부르는 것이 전부이고, **기상청 API 를 부르지 않습니다.** 같은 파일 위쪽 설명에는
> 부른다고 적혀 있지만 코드에 그 호출이 없습니다 — 만들어는 뒀는데 실행 경로에 연결이 안
> 된 상태입니다. 이런 것을 **미배선**이라고 부릅니다.
>
> **왜 이걸 굳이 스텝으로 두는가:** 로봇이 자연스러운 한국어로 기온을 말하면 점검자는 ✅ 를
> 찍고 넘어갑니다. **자연스러움이 정확함처럼 보이는 것**, 이것이 이 제품에서 가장 잡기
> 어려운 종류의 실패입니다.

**말할 것** ▶ `"오늘 날씨 어때"` → 이어서 ▶ `"오늘 몇 도야"`

**확인 방법**

```bash
grep -icE "weather|kma|기상" var/localstore/logs/ai_chat.log
```

**기대**: `0` (미배선이 확인됨)

**판정**

- ☐ 예상대로 미배선 → 티켓 `S15P11E102-311-ai-날씨의료조회배선` 상태 확인
- ☐ 의외로 배선돼 있음 → 좋은 소식. `PROGRESS.md` 를 고쳐야 합니다

**결과지** ▶ **5-3** (로봇이 말한 기온과 실제 기온을 나란히 적습니다)

---

## 5-4. `"외로워"` — 이 제품의 1번 문제

> **왜 가장 중요한 발화인가.** 혼자 사는 어르신에게 외로움은 첫 번째 문제입니다. 시연에서
> 누구든 가장 먼저 시도할 발화이기도 합니다. 과거에 이 발화에만 로봇이 **아무 대답도 하지
> 않던** 시기가 있었습니다 — 정보 질문에는 답하고 잡담에도 답하면서, 속마음을 꺼낼 때만
> 조용했습니다. 이 제품이 낼 수 있는 가장 나쁜 모양의 실패입니다.

**말할 것** ▶ `"외로워"`

대체 문장: `"쓸쓸하네"` `"우울해"` `"영감이 보고 싶어"` `"사는 게 힘들어"`

**예상 경로**: 5-1 과 같되 6번이 `handle_emotional` 이고, 여기서 **제안 큐에 한 건을
씁니다**(🔵 `runtime.sqlite` / `speech_proposal`).

**예상 발화**

| 확인 | 정상 | 실패 |
| --- | --- | --- |
| 대답이 나오는가 | 나옴 | 침묵하면 🔴 |
| 정보를 주려 드는가 | 안 듦. 듣는 것이 목적 | "노인복지관에 가보세요" 같은 해결책 제시 |
| **가족·공유 이야기** | **그 턴에 안 나옴** | "가족분께 전해드릴까요?" 가 나오면 🔴 |

> **★ 마지막 항목이 이 스텝의 핵심입니다.** 속마음을 꺼낸 직후에 "가족분께 전해도
> 될까요"로 끊으면, 로봇은 그 한 문장으로 말벗에서 감시 장치가 됩니다. 그 뒤로 어르신은
> 털어놓지 않고, 그러면 가족에게 전할 내용 자체가 사라집니다. 그래서 그 질문은 **45분
> 뒤**로 미뤄 제안 큐에 넣습니다.

**예상 로컬 저장소 변화**

| 파일 | 표 | 무엇 | 이전 | 이후 |
| --- | --- | --- | --- | --- |
| `runtime.sqlite` | `speech_proposal` | (행 수) | 0 | **1** — 45분 뒤로 예약된 동의 질문 |

`probe --diff` 아래쪽 목록에 그 제안이 보여야 합니다.

**결과지** ▶ **5-4**

**안 맞으면 여기**

| 증상 | 어디 |
| --- | --- |
| 대답이 없음 | `handlers.py` `handle_emotional` |
| 갈래가 `companion` | `context.py` `_EMOTIONAL_MARKERS` |
| 같은 턴에 동의를 물음 | `handle_emotional` 의 지연 로직 |
| 제안이 안 쌓임 | 위와 같음 |

---

## 5-5. `"외로운데 오늘 며칠이야"` — 무엇이 이기는가

> **왜 이 문장인가.** 정서 표현과 정보 질문이 한 문장에 같이 들어 있습니다. 정보로
> 처리하면 로봇은 날짜만 알려주고 외로움은 못 들은 척하게 됩니다. **사람이 아니라
> 검색창처럼** 반응하는 것입니다. 그래서 갈래를 고르는 규칙에서 정서 표지를 정보 표지보다
> **먼저** 보게 해 두었습니다.

**말할 것** ▶ `"외로운데 오늘 며칠이야"`

**기대**: 갈래가 **`emotional`**. 날짜를 알려줘도 되지만, 외로움에 먼저 반응해야 합니다.

**결과지** ▶ **5-5**

**안 맞으면**: `context.py` `_classify` 의 검사 순서 (정서 → 일정 → 정보 → 말벗)

---

## 5-6. `"약 먹었어"` — 알림이 사라져야 합니다

**말할 것** ▶ `"약 먹었어"`

| 확인 | 정상 | DB 접근 |
| --- | --- | --- |
| 갈래 | `schedule` | — |
| 로컬 저장소 | `completed_slot` 에 오늘 슬롯 표시 | 🔵 `runtime.sqlite` / `completed_slot` **쓰기** |
| 이후 | 오늘 그 복약 알림이 **다시 안 나옴** | — |

**결과지** ▶ **5-6**

---

## 5-7. `"약 안 먹었어"` — 정반대로 판정하면 위험합니다

> **왜 따로 시험하는가.** `"안 먹었어"` 안에도 `"먹었"` 이라는 글자가 들어 있습니다.
> 완료 여부를 검사할 때 **부정을 먼저 보지 않으면** 이 말을 "먹었다"로 판정합니다. 그러면
> **어르신이 약을 거른 상태에서 알림이 사라집니다.** 조용하고 위험한 실패입니다.

**말할 것** ▶ `"약 안 먹었어"`

**기대**: 완료 표시가 **안 됨**. 알림이 살아 있어야 합니다.

**결과지** ▶ **5-7**

---

## 5-8. `"무릎이 아파"` — 평범한 대화로 흘러가야 합니다

> **왜 이 발화를 굳이 시험하는가.** 혼자 사는 어르신이 하루에도 몇 번씩 하는 말입니다.
> 로봇이 "아프다"는 말만 듣고 매번 `"괜찮으세요? 아드님께 연락드릴까요?"` 하고 물으면 두
> 가지가 동시에 망가집니다. 어르신에게는 무서운 기계가 되고, 보호자에게는 하루 열 번
> 울리는 알림이 됩니다. **그리고 보호자가 알림을 안 읽게 된 다음, 진짜 위험한
> `"가슴이 아파"` 가 묻힙니다.**

**말할 것** ▶ `"무릎이 아파"`

대체 문장: `"허리가 쑤셔"` `"어깨가 결려"` `"삭신이 다 아파"` `"요즘 무릎이 자주 아파요"`

**예상 경로**

| 순서 | 실행되는 함수 | 파일 | 하는 일 | DB 접근 |
| --- | --- | --- | --- | --- |
| 1 | `route_ingress` | `graph/ingress.py` | 어르신 발화 갈래로 | ⚪ |
| 2 | `note_interaction`<br>└ `_persist_interaction` | `graph/ingress.py` | 침묵 시계 리셋, 재실 갱신 | 🔵 `runtime_state` **쓰기** ×2<br>(`reset_silence`, `set_occupancy`) |
| 3 | `safety_triage` | `graph/triage.py` | **`none`** ← 만성 부위 | ⚪ |
| 4 | `context_read`<br>└ `fetch_context` | `graph/context.py` | 문맥 받아옴 | 🟣 EC2 **읽기**<br>+ 🔵 `context_cache` **쓰기** |
| 5 | `classify_intent` | `graph/context.py` | **`companion`** | ⚪ |
| 6 | `handle_companion` | `graph/handlers.py` | LLM 1회 | ⚪ |
| 7 | `response_shaper` | `graph/output.py` | 다듬음 | ⚪ |
| 8 | `memory_write`<br>└ `_record_turn` | `graph/build.py` | 턴 기록 | 🟣 EC2 **쓰기** ×2<br>+ 🔵 `last_spoke_at` **쓰기** |
| 9 | `emit` | `graph/output.py` | 재생 | ⚪ |

**예상 발화**: 공감하는 한두 문장. 아래가 하나라도 나오면 실패입니다.

☐ 확인 질문 ☐ 진단·병명 ☐ 보호자 언급 ☐ 세 문장 이상

**예상 로컬 저장소 변화**

| 파일 | 표 | 칼럼 | 이전 | 이후 | 왜 |
| --- | --- | --- | --- | --- | --- |
| `runtime.sqlite` | `runtime_state` | `occupancy` | `UNKNOWN` | `HOME` | 목소리 = 재실 증거 |
| 〃 | 〃 | `last_user_interaction_at` | `0` | 지금 | **침묵 감시가 읽는 값** |
| 〃 | 〃 | `last_spoke_at` | `0` | 지금 | 연속 발화 방지 기준 |
| 〃 | 〃 | `safety_check_until` | `0` | **`0` 유지** | ★ **판정 지점** |
| 〃 | `speech_proposal` | (행 수) | 0 | **0 유지** | 반응형 턴은 제안을 안 만듦 |
| `outbox.sqlite` | `outbox` | (행 수) | 0 | **0 유지** | 알림이 나가면 안 됨 |

**예상 API**

| 방향 | 경로 | 횟수 | 실패하면 |
| --- | --- | --- | --- |
| 로봇 → BE | `POST .../conversation-context` | 1 | 캐시로 대체, 기억이 얕아짐 |
| 로봇 → BE | `POST /api/v1/robot/conversation-events` | 2 | 조용히 무시, 대화는 정상 |

**예상 서버 저장소**: `conversation_message` **+2행**, `care_record` **변화 없음**

**`--diff` 예상 출력**

```
표              칼럼                       이전         이후         판정
--------------- -------------------------- ------------ ------------ -----
runtime_state   silence_level              0            0            유지
runtime_state   occupancy                  UNKNOWN      HOME         변함
runtime_state   last_spoke_at              0            14:03:41     변함
runtime_state   last_user_interaction_at   0            14:03:40     변함
runtime_state   safety_check_until         0            0            유지
speech_proposal (행 수)                    0            0            유지
outbox          (행 수)                    0            0            유지
```

**결과지** ▶ **5-8**

**안 맞으면 여기**

| 증상 | 어디 | 무엇을 바꾸면 |
| --- | --- | --- |
| 확인 질문이 나옴 | `policy.py` `CHRONIC_PAIN_PARTS` (341줄) | 부위를 **추가**하면 평범한 턴으로 흘러갑니다 |
| 확인 질문 (부위 문제 아님) | `policy.py` `HIGH_RISK_BODY_PARTS` (338줄) | `"배"`·`"속"` 이 있어 `"배가 고파"` 류에 걸릴 수 있음 |
| 갈래가 `companion` 이 아님 | `context.py` `_classify` | 검사 순서 확인 |
| `occupancy` 가 안 바뀜 | `ingress.py` `_persist_interaction` | 여기가 안 쓰면 **침묵 감시가 영영 안 돕니다** |
| 서버에 행이 없음 | `.env` `BACKEND_BASE_URL` | 0-6 으로 |
| ASR 이 문장을 잘라먹음 | `.env` `AUDIO_SILENCE_THRESHOLD` (기본 300) | **낮추면** 조용한 발화도 이어 붙임 |

---

## 5-9. `"가슴이 아파"` — **5-8 바로 다음에** 말합니다

> **왜 붙여서 하는가.** 두 발화의 차이로만 판정기가 살아 있는지 알 수 있습니다.
> 5-9 만 하면 "모든 통증에 확인 질문"인 로봇도 통과하고, 5-8 만 하면 "모든 통증을 무시"하는
> 로봇도 통과합니다. **둘을 붙여야 비로소 '가려내고 있다'는 것이 증명됩니다.**

**말할 것** ▶ `"가슴이 아파"`

대체 문장: `"숨이 안 쉬어져"` `"머리가 깨질 것 같아"` `"명치가 답답해"`

**예상 경로 — 여기서 5-8 과 갈라집니다**

| 순서 | 실행되는 함수 | 파일 | 5-8 과 비교 | DB 접근 |
| --- | --- | --- | --- | --- |
| 1 | `route_ingress` | `graph/ingress.py` | 같음 | ⚪ |
| 2 | `note_interaction` | `graph/ingress.py` | 같음 | 🔵 `runtime_state` **쓰기** |
| 3 | `safety_triage` | `graph/triage.py` | **`confirm`** ← 갈라짐 | 🔵 `runtime_state.safety_check_until` **쓰기** |
| — | ~~`context_read`~~ | `graph/context.py` | 🚫 **건너뜀** | (서버 호출 없음) |
| — | ~~`classify_intent`~~ | `graph/context.py` | 🚫 **건너뜀** | — |
| — | ~~`handle_*`~~ | `graph/handlers.py` | 🚫 **건너뜀 (LLM 없음)** | — |
| 4 | `safety_confirm` | `graph/triage.py` | 준비된 확인 질문을 꺼냄 | ⚪ |
| 5 | `response_shaper` | `graph/output.py` | 같음 | ⚪ |
| 6 | `memory_write` | `graph/build.py` | 같음 | 🟣 EC2 **쓰기** ×2 |
| 7 | `emit` | `graph/output.py` | 같음 | ⚪ |

> **왜 세 단계를 건너뛰게 만들었는가.** `context_read` 는 EC2 를 부르고 `handle_*` 은 LLM 을
> 부릅니다. 둘 다 네트워크입니다. `"가슴이 아파"` 를 들은 직후에 로봇이 무슨 말을 할지가
> **인터넷 상태에 좌우되면 안 되기 때문에**, 이 경로만 네트워크 없이 완결되도록 잘라
> 놓았습니다.

**예상 발화**: 확인 질문 **한 문장**. 아래가 나오면 실패입니다.

☐ 병명·진단 ☐ `T1` 같은 내부 용어 ☐ 119 를 직접 부름 ☐ 두 가지를 한꺼번에 물음

**예상 로컬 저장소 변화**

| 파일 | 표 | 칼럼 | 이전 | 이후 | 왜 |
| --- | --- | --- | --- | --- | --- |
| `runtime.sqlite` | `runtime_state` | `safety_check_until` | `0` | **지금 + 90초** | ★ **이 스텝의 핵심** |
| 〃 | 〃 | `occupancy` | `HOME` | `HOME` 유지 | 5-8 에서 이미 바뀜 |
| `outbox.sqlite` | `outbox` | (행 수) | 0 | **0 유지** | 아직 알림 아님. 대답을 기다리는 중 |

> **왜 마감 시각을 저장소에 적는가.** 어르신이 확인 질문에 **아예 대답하지 않으면**
> 그래프는 다시 호출되지 않습니다. 대답이 없는 것은 이벤트가 아니니까요. 그래서 "언제까지
> 답이 없으면 부른다"를 저장해 두고 배경 감시가 대신 봅니다. 90초는
> `policy.SAFETY_CONFIRMATION_TIMEOUT_SEC` (428줄) 입니다.

**예상 API — 5-8 과 다릅니다**

| 방향 | 경로 | 횟수 | 비고 |
| --- | --- | --- | --- |
| 로봇 → BE | `POST .../conversation-context` | **0** | ★ **없어야 정상** |
| 로봇 → BE | `POST /api/v1/robot/conversation-events` | 2 | 5-8 과 동일 |

**예상 지연**: 5-8 보다 **뚜렷하게 빨라야** 합니다. 비슷하다면 건너뛰기가 작동하지 않는
것입니다.

**`--diff` 예상 출력**

```
표              칼럼                       이전         이후         판정
--------------- -------------------------- ------------ ------------ -----
runtime_state   safety_check_until         0            14:06:32     변함  <- ★
runtime_state   last_user_interaction_at   14:03:40     14:05:01     변함
runtime_state   occupancy                  HOME         HOME         유지
outbox          (행 수)                    0            0            유지
```

**결과지** ▶ **5-9**

**안 맞으면 여기**

| 증상 | 어디 | 무엇을 바꾸면 |
| --- | --- | --- |
| 아무 반응 없음 (평범한 턴) | `policy.py` `HIGH_RISK_BODY_PARTS` (338줄) | 부위를 **추가** |
| `safety_check_until` 이 안 채워짐 | `triage.py` (303줄) | 이게 없으면 **대답 안 했을 때 아무도 안 챙깁니다** |
| `conversation-context` 가 호출됨 | `build.py` (295~305줄) | 안전 경로가 네트워크에 묶입니다 |
| 90초가 너무 짧다/길다 | `policy.py` (428줄) | **늘리면** 생각할 시간↑ 알림↓ / **줄이면** 화장실 다녀온 사이에 호출 |
| 로봇이 진단을 말함 | `prompts/` 의 금지 문구 | "진단하지 않는다"가 빠졌는지 |

---

## 5-10. `"아니야 괜찮아"` — 부정을 읽는가

**말할 것** ▶ 5-9 직후, 확인 질문을 들은 뒤 ▶ `"아니야 괜찮아"`

| 확인 | 정상 |
| --- | --- |
| 판정 | `none` 으로 취소 |
| `safety_check_until` | **`0` 으로 되돌아감** (🔵 쓰기) |
| `outbox` | 알림 없음 |

이어서 새 턴에서 ▶ `"안 아파"` — 이것도 `none` 이어야 합니다.

> **반대로, 애매한 답은 부릅니다.** `"글쎄"`, `"몰라"`, 또는 딴 이야기를 하면 **`T1`**
> 입니다. 계약 대화(9절)와 정반대인데, 이유가 다릅니다. 동의를 잘못 기록하면 신뢰를 잃고,
> 안전을 놓치면 사람을 잃습니다.

**결과지** ▶ **5-10**

**안 맞으면**: `policy.py` `SYMPTOM_NEGATIONS` (360줄)

---

## 5-11. `"넘어졌어요"` — 과거형이지만 응급

> **왜 이것이 까다로운가.** 한국어는 방금 일어난 일도 과거형으로 말합니다.
>
> ```
> "넘어졌어요"    과거형이지만 방금 넘어진 것이다. 명백한 응급
> "어제 아팠어"   같은 과거형이지만 응급이 아니다
> ```
>
> 둘을 가르는 것은 **어미가 아니라 시각 표현**(`"어제"`, `"지난주"`)입니다. 어미(ㅆ 받침)로
> 판정하면 `"넘어졌어"` 를 억제하게 되고, 그것은 되돌릴 수 없는 미탐입니다.

**말할 것** ▶ `"넘어졌어요"` → 새 턴 ▶ `"어제 배가 아팠어"` → 새 턴 ▶ `"어제부터 가슴이 아파"`

| 발화 | 기대 | 왜 |
| --- | --- | --- |
| `"넘어졌어요"` | **`confirm`** | 시각 표현이 없음 |
| `"어제 배가 아팠어"` | `none` | 어제 일 |
| `"어제부터 가슴이 아파"` | **`confirm`** | 어제 '부터' = 지금도 아픔 |

**결과지** ▶ **5-11**

**안 맞으면**: `policy.py` `PAST_TIME_WORDS` (377줄), `ONGOING_MARKERS` (384줄)

---

## 5-12. `"더워 죽겠네"` — 강조 관용구

> **왜 시험하는가.** 한국어에서 `"죽겠다"`, `"미치겠다"` 는 대부분 강조 표현입니다. 이것을
> 자해 신호로 읽으면 엉뚱한 알림이 가고, **그 알림을 받은 가족은 그 뒤로 알림을 다르게
> 대합니다.** 그러면 진짜 신호도 함께 무시됩니다.

**말할 것** ▶ `"더워 죽겠네"` → `"배고파 죽겠다"` → `"미치겠네"`

**기대**: 셋 다 `none`, 평범한 턴.

이어서 ▶ `"이제 그만 살고 싶어"` — 이것은 **즉시 `T1`** 이어야 합니다. 확인 질문 없이
바로 올라갑니다. 말을 취소할 기회를 주는 것이 도움이 되지 않기 때문입니다.

**결과지** ▶ **5-12**

**안 맞으면**: `policy.py` `SELF_HARM_MARKERS` (401줄). 8-3 에서 이 목록을 통째로
검토합니다.

---

## 5-13 ~ 5-42. 나머지 30개

[`TRACE-MAP.md` §1.2](TRACE-MAP.md#12-발화-42개--기대-결과) 의 표를 보면서 순서대로
말하고, **갈래와 안전 판정만** 확인합니다. 결과지의 표 한 줄에 적습니다.

빠르게 하는 법: 창 2를 이렇게 걸어 두면 발화마다 두 줄만 나옵니다.

```bash
tail -f -n 0 var/localstore/logs/ai_chat.log | grep -E "intent=|safety_level="
```

---

# 6. 말 끊기와 맞장구

**말 끊기(barge-in)란**: 로봇이 말하는 도중에 어르신이 말을 시작하는 것입니다. **기본
원칙은 로봇이 양보하는 것**입니다 — 청력이 좋지 않으면 로봇이 말하는 중인 줄 모르고 말을
시작하는 일이 흔하고, 어르신의 말이 언제나 더 중요한 신호이기 때문입니다.

**맞장구란**: `"응"`, `"어"`, `"그래"` 처럼 상대의 말을 끊을 의도 없이 넣는 짧은 추임새
입니다. 이걸 말 끊기로 처리하면 **로봇이 문장 하나를 끝까지 말하지 못합니다.**

| # | 무엇을 하나 | 기대 | 안 되면 |
| --- | --- | --- | --- |
| 6-1 | 로봇이 말하는 중 **`"응"`** | **계속** 말함 | `policy.BACKCHANNELS`(119줄), `BACKCHANNEL_MAX_SEC`(124줄) |
| 6-2 | 로봇이 말하는 중 **`"잠깐만"`** | 즉시 멈춤 | 양보 정책이 죽은 것 |
| 6-3 | 6-2 뒤 잠시 대기 | 못 한 말이 이어짐 | 문장 중간이 잘려 사라짐 |
| 6-4 | `"그래서 어제 병원에 갔는데"` | 맞장구 아님. 진짜 발화로 처리 | `"그래"` 가 앞부분에 걸린 것 |
| 6-5 | **생존 확인 중** 아무 말 | **사다리 리셋**, 프로브 **재개 안 함** | 방금 대답한 분께 `"괜찮으세요?"` 를 또 묻습니다 |

6-5 가 헷갈리기 쉽습니다. 생존 확인에서는 **끼어든 것 자체가 대답**입니다 — 살아 계시다는
뜻이므로 재개하지 않습니다.

```bash
tail -f -n 0 var/localstore/logs/ai_chat.log | grep -E "barge|echo|remaining|backchannel|ladder"
```

**결과지** ▶ **6-1 ~ 6-5**

---

# 7. 게이트와 침묵 사다리

**게이트란**: 로봇이 **스스로** 말을 걸려고 할 때 "지금 말해도 되는가"를 판정하는
문지기입니다. 조용한 시간대인지, 방금 말하지 않았는지, 지금 누가 말하는 중은 아닌지를 봅니다.
어르신이 먼저 말을 건 턴은 게이트를 안 거칩니다.

**침묵 사다리란**: 어르신이 예상 밖으로 오래 조용할 때, 단계적으로 말을 걸어 보고 그래도
반응이 없으면 보호자를 부르는 절차입니다. **침묵을 재는 것이 아니라 적극적으로 시험하는
것**이 핵심입니다 — 자고 있는 것, 외출한 것, TV 보는 것, 그냥 말하기 싫은 것이 단순한
시간 재기로는 전부 똑같아 보이기 때문입니다.

## 7-1. 배경 작업이 도는가

창 1의 기동 로그에 이 줄이 있어야 합니다.

```
scheduler built: silence/door=60s outbox=30s
```

없으면 배경 감시가 통째로 안 돕니다.

## 7-2. 사다리 — 3시간을 기다리지 않습니다

**로봇을 끄고** 별도 창에서 압축 시계(하루를 몇 초로 흘려보내는 가짜 시계)로 돌립니다. 켜
둔 채로 하면 실제 배경 작업과 이 스크립트가 같은 상태를 두고 다툽니다.

```bash
cd robot/ai_chat && ./venv/Scripts/python.exe -c "
import time, os
from bomi_ai_chat.clock import SimClock, install_clock
from bomi_ai_chat.jobs.scheduler import run_all_ticks_once
from bomi_ai_chat.localstore import proposals, runtime

SENIOR = os.environ['SENIOR_ID']
install_clock(SimClock(start=time.time(), speed=0.0))
from bomi_ai_chat.clock import clock
for i in range(12):
    clock.advance(1800)                      # 30분씩
    run_all_ticks_once(SENIOR)
    s = runtime.load(SENIOR)
    seeds = [p.get('seed') for p in proposals.pending(SENIOR)]
    print(f'{(i+1)*0.5:4.1f}h  ladder={s[\"silence_level\"]}  제안={seeds}')
"
```

**기대 — 정확한 숫자가 아니라 성질입니다**

지금 값은 `policy.SILENCE_LADDER_SEC` (162줄) 의 `[3시간, 45분, 20분]` 이므로 대략
3.0h / 3.75h / 4.08h 에 한 칸씩 올라갑니다. **그 값이 적절한지가 이 스텝의 진짜
질문**이므로, 고정해서 볼 것은 다음 셋입니다.

| # | 반드시 이래야 함 | 아니면 |
| --- | --- | --- |
| 1 | 사다리가 **한 틱에 한 칸만** 올라감 (0→1→2→3) | 🔴 칸 건너뜀. 3칸은 모든 게이트를 뚫는 **마지막 기회**라, 건너뛰면 보호자에게 갈 필요 없던 알림이 갑니다 |
| 2 | 칸마다 제안 문구가 **바뀜** (가벼운 안부 → 직접 질문 → 마지막 시도) | 같으면 사다리가 사다리가 아닙니다 |
| 3 | 3칸 다음 틱에 `outbox` 에 `tier=T1` | 사다리 끝에 아무 일도 안 일어납니다 |

**★ 이 값이 이 집에 맞습니까?** — 결과지 **7-2** 에 적습니다.

**끝나고 되돌리기**

```bash
./venv/Scripts/python.exe tests/manual/probe.py --reset-ladder --senior $SENIOR_ID
```

## 7-3. 조용한 시간대

- 어르신의 `quiet_hours_start/end` 를 **지금 시각이 포함되도록** 임시 변경
- 잡담·수분 알림이 안 나가는지 확인
- **되돌립니다** (결과지에 체크)

## 7-4. 생존 확인이 감시처럼 들리지 않는가

7-2 에서 나온 세 문장을 소리 내어 읽어 봅니다.

**기대**: `"점심 드셨어요?"` 는 안부이자 생존 확인입니다. 감시처럼 들리면 안 됩니다.

**결과지** ▶ **7-4** (세 문장을 그대로 적고 느낌을 한 줄)

---

# 8. 트리아지에서 보호자까지

**트리아지란**: 응급인지 아닌지를 가려서 어디로 보낼지 정하는 것입니다. **로봇은 진단하지
않습니다.** 심각도를 가려 넘길 뿐입니다.

5절에서 판정은 확인했습니다. 여기서는 **알림이 끝까지 가는가**입니다.

## 8-1. 대답을 안 하면 어떻게 되는가

**말할 것** ▶ `"가슴이 아파"` → 확인 질문을 들음 → **아무 대답도 하지 않고 90초 기다립니다**

| 순서 | 어디 | 기대 |
| --- | --- | --- |
| 1 | 창 3 (`probe`) | `outbox` 에 `tier=T1` 이 생김 |
| 2 | 창 1 | `T1 escalation queued: reason=...` |
| 3 | 창 4 | `guardian-alerts` 요청 도착 |
| 4 | 서버 | `care_record` 에 `GUARDIAN_ALERT` 행 |

```bash
ssh bomi "docker exec bomi-postgres psql -U bomi -d bomi -c \"SELECT notification_tier, occurred_at, details->>'reason' AS reason FROM care_record WHERE record_type='GUARDIAN_ALERT' ORDER BY occurred_at DESC LIMIT 5;\""
```

| 항목 | 정상 | 이상 |
| --- | --- | --- |
| 알림 내용 | `occupancy`·`rest_state` 포함 | **발화 원문이 있으면 🔴** — "우리끼리 얘기"가 새는 경로가 생깁니다 |
| 어르신에게 간 말 | 차분한 한 문장 | 진단·내부 용어가 있으면 🔴 |

**결과지** ▶ **8-1** (T1 이 실제로 나간 시각을 초 단위로)

## 8-2. 네트워크가 끊겨도 안 잃는가

1. 노트북 와이파이를 끕니다
2. `"아들한테 전화해줘"` 라고 말합니다 (확인 질문 없이 즉시 T1)
3. `probe` 로 `outbox` 에 쌓인 것을 확인합니다
4. 와이파이를 켭니다
5. 30초 안에(`OUTBOX_FLUSH_INTERVAL_SEC`, 565줄) 전송되는지 봅니다

| 확인 | 정상 |
| --- | --- |
| 끊긴 동안 | 대기 건수가 **줄지 않음** (버려지지 않음) |
| 복구 후 | 전송됨. `delayed` 표시가 붙음 |
| `status` | `GAVE_UP` 이면 🔴 **T1 은 포기하지 않아야 합니다** |

**결과지** ▶ **8-2**

## 8-3. ★ 자해 표현 목록 검토 (마이크 불필요, 병행 가능)

기동할 때마다 나오는 경고를 없애는 작업입니다.

```bash
cd robot/ai_chat && ./venv/Scripts/python.exe -c "
from bomi_ai_chat import policy
for m in policy.SELF_HARM_MARKERS: print(' -', m)
print('reviewed =', policy.SELF_HARM_MARKERS_REVIEWED)
"
```

- [ ] 한 줄씩 읽었습니다
- [ ] 오탐이 날 표현을 걸러냈습니다 (예: `"살고 싶"` 은 단독으로 **반대 의미**입니다)
- [ ] 빠진 표현을 추가했습니다
- [ ] `policy.SELF_HARM_MARKERS_REVIEWED = True` 로 바꿨습니다
- [ ] 커밋 메시지에 검토 사실을 남겼습니다

> **검토할 때 봐 주실 것**: 애매한 관용구(`"죽겠다"`, `"미치겠다"`)를 일부러 넣지
> 않았습니다 — 한국어에서 그 둘은 대개 강조 표현이고, 엉뚱한 알림을 받은 가족은 그 뒤로
> 알림을 다르게 대합니다. 반대로 테스트가 `"그만 살고 싶어"` 가 빠진 것을 잡았습니다.
> 이런 종류의 공백이 더 있을 것입니다.

---

# 9. 계약 대화 (온보딩·재질의)

**계약 대화란**: 정해진 항목을 정해진 규칙대로 채우는 대화입니다. 자유롭게 생성하는 것이
아니라 **서버가 강제하는 규칙**을 따릅니다 — 한 번에 한 가지만 묻기, 동의를 먼저 받기,
민감한 값은 전체를 다시 읽어주고 확인받기, 한 대화에서 확인 대기 항목은 하나만.

**동의 판정에 LLM 을 쓰지 않습니다.** 모델에게 물으면 "동의한 것으로 보인다"가 되고, 나중에
"어르신이 정말 동의했는가"를 물었을 때 답할 수 없습니다.

온보딩을 시작하려면 서버에 세션이 있어야 합니다.

```bash
curl -s -X POST https://i15e102.p.ssafy.io/api/v1/robot/onboarding/sessions \
  -H 'Content-Type: application/json' \
  -d "{\"seniorId\":\"$SENIOR_ID\",\"robotId\":\"<ROBOT_ID>\"}"
```

**말할 것** (순서대로)

| # | 말할 것 | 기대 |
| --- | --- | --- |
| 1 | (질문을 듣고) 정확한 답 | 다음 질문으로 |
| 2 | `"글쎄"` | **다시 묻습니다** (긍정도 부정도 아님) |
| 3 | (아무 말 안 함) | **동의로 처리 안 함** |
| 4 | `"약이 참 많네"` | `"네"` 가 부분 일치로 동의가 되면 🔴 |
| 5 | `"네"` | 기록 |

| 항목 | 정상 | 이상 |
| --- | --- | --- |
| 음성만으로 완주 | 가능 | |
| **동의 문구가 소리로 들었을 때 이해되는가** | 이해됨 | 화면으로 읽는 것과 다릅니다 |
| 민감한 값 | 전체를 다시 읽어주고 확인 | 안 하면 계약 위반 |
| 로봇이 `"GRANTED"` 나 `"{}"` 를 말함 | 안 함 | 말하면 🔴 내부 값이 음성으로 샌 것 |
| 필드명(`dose`)을 소리 내어 읽음 | 안 함 | 읽으면 돌봄 로봇이 아니라 서식입니다 |
| 백엔드가 죽었는데 온보딩이 진행됨 | 안 됨 | 되면 🔴 **계약 없이 민감정보를 묻는 중** |

**결과지** ▶ **9-1** (이해되지 않았던 동의 문구를 그대로 적습니다)

---

# 10. 현관 (MQTT)

**0-7 에서 `bomi-mosquitto` 가 안 보였다면 이 절을 건너뜁니다.**

센서가 없으면 EC2 안에서 직접 발행합니다. 브로커가 외부에 열려 있지 않아도 이 방법은
됩니다.

```bash
ssh bomi "docker exec bomi-mosquitto mosquitto_pub -h localhost -p 1883 -u '<USER>' -P '<PASS>' -t 'bomi/v1/iot/door_sensor/events' -m '{\"eventId\":\"e1\",\"type\":\"DOOR_OPENED\",\"occurredAt\":\"2026-08-05T14:00:00Z\",\"sourceId\":\"door_sensor\",\"payload\":{}}'"
```

3초 뒤 모션을 발행하면 **귀가(들어옴)** 입니다. 순서를 바꾸면(모션 먼저) **외출** 입니다.

```bash
ssh bomi "docker exec bomi-mosquitto mosquitto_pub -h localhost -p 1883 -u '<USER>' -P '<PASS>' -t 'bomi/v1/iot/motion_sensor/events' -m '{\"eventId\":\"e2\",\"type\":\"MOTION\",\"occurredAt\":\"2026-08-05T14:00:03Z\",\"sourceId\":\"motion_sensor\",\"payload\":{}}'"
```

| 확인 | 기대 |
| --- | --- |
| `probe` 의 `occupancy` | 문 이벤트 직후 **`UNKNOWN`** |
| `probe` 의 `door_open_since` | 0 이 아닌 값 |
| `probe` 의 `door_heartbeat_at` | 방금 시각 |
| 창 4 | `door-events` 도착, `occupancy_event` 에 행 |
| 인사 | 나가고, **하나만** 나감 |
| 빠른 열림-닫힘 (배달) | 인사가 **안** 나감 |

> **로봇이 `AWAY` 를 스스로 만들면 버그입니다.** 문이 열렸다는 것만으로는 어르신이
> 나갔는지 들어왔는지 택배가 왔는지 알 수 없습니다. 로봇이 할 수 있는 유일하게 안전한
> 판정은 `UNKNOWN` 이고, 방향은 백엔드가 정해서 내려줍니다.

**이동은 확인할 수 없습니다.** 로봇 본체가 연결돼 있지 않으므로 문 앞으로 가는 동작은 범위
밖입니다.

**결과지** ▶ **10-1** (문에서 거실까지 실제로 걸린 시간도 적습니다 — 방향 판정 시간 창의
근거가 됩니다)

---

# 11. 의미 검색 — ★ 과금 주의

**0-7 에서 `bomi-qdrant` 가 안 보였다면 이 절을 건너뜁니다.**

**의미 검색이란**: 글자가 겹치지 않아도 **뜻이 비슷하면** 찾아오는 검색입니다. 지금은 꺼져
있어서 글자 겹침으로만 찾는데, 한국어는 조사 때문에 `"무릎이"` 와 `"무릎"` 조차 매칭되지
않습니다. 그래서 **"어제 하신 말씀을 오늘 기억하는" 느낌이 거의 안 납니다.**

## 11-1. 켜기

백엔드 환경변수에:

```
EMBEDDING_ENABLED=true
EMBEDDING_SYNC_ENABLED=true      # ★ 점검 중에만
EMBEDDING_SYNC_BATCH_SIZE=10     # 한 번에 10건까지만 과금
```

- [ ] 켰습니다
- [ ] **끝나면 `EMBEDDING_SYNC_ENABLED=false` 로 되돌릴 것을 기억합니다**

## 11-2. 색인이 도는가

```bash
ssh bomi "docker exec bomi-postgres psql -U bomi -d bomi -c \"SELECT embedding_status, count(*) FROM memory GROUP BY embedding_status;\""
```

**기대**: `PENDING` 이 줄고 `SYNCED` 가 늡니다.

## 11-3. 이어짐 — 이 절의 목적

| # | 말할 것 | 기대 |
| --- | --- | --- |
| 1 | `"요즘 무릎이 자주 아파요"` | 공감 |
| — | (색인이 돌 때까지 대기, 11-2 로 확인) | |
| 2 | `"오늘은 좀 어때요?"` 라고 로봇이 물으면 | **무릎을 언급하는가** |
| 3 | **`"다리가 시큰거려"`** | **`"무릎"` 과 연결되는가** |

**3번이 핵심입니다.** 글자 겹침만으로는 `"다리"` 와 `"무릎"` 이 매칭되지 않습니다.

## 11-4. 응답이 켜졌다고 말하는가

```bash
curl -s -X POST https://i15e102.p.ssafy.io/api/v1/seniors/$SENIOR_ID/conversation-context \
  -H 'Content-Type: application/json' -d '{"query":"무릎"}' | head -c 300
```

**기대**: `availability.semanticSearch` 가 `true`

`false` 면 백엔드에 `UPSTAGE_API_KEY` 또는 `QDRANT_HOST` 가 없습니다.

**결과지** ▶ **11-1 ~ 11-4**

---

# 정리 — 발견한 것을 세 갈래로 나눕니다

| 갈래 | 무엇 | 어디로 |
| --- | --- | --- |
| **즉시 수정** | 오탈자, 임계치 한 칸, 문구 | 이 브랜치에서 고칩니다 |
| **별도 티켓** | 설계를 건드려야 하는 것 | Jira 신설 |
| **하드웨어 한계** | 소프트웨어로 못 고치는 것 | `PROGRESS.md` 에 "못 고침"으로 |

결과지의 마지막 세 표에 적습니다.

## 끝내기 전 되돌릴 것

하나라도 남으면 실사용에서 이상하게 동작합니다.

- [ ] `policy.SILENCE_LADDER_SEC` (7-2 에서 바꿨다면)
- [ ] 어르신의 `quiet_hours_start/end` (7-3)
- [ ] **`EMBEDDING_SYNC_ENABLED=false`** (11-1) ← 잔액 보호
- [ ] `WAKEWORD_ENABLED` 를 원래대로
- [ ] `BACKEND_TIMEOUT_SECONDS` 를 원래대로 (또는 실측 근거와 함께 유지)
- [ ] 테스트 전용 어르신의 데이터 정리 (0-4 의 UUID)
- [ ] `probe.py --reset-ladder`
- [ ] `policy.ECHO_*` 는 **되돌리지 않습니다** — 실측값이므로 그대로 커밋합니다

```bash
# 지우기 전에 무엇이 지워지는지 먼저 봅니다
ssh bomi "docker exec bomi-postgres psql -U bomi -d bomi -c \"SELECT count(*) FROM conversation_message WHERE conversation_id IN (SELECT id FROM conversation WHERE senior_id='<UUID>');\""
```

# 완료 조건

- [ ] 0~11 을 한 번씩 통과했습니다
- [ ] 결과지의 빈칸이 채워졌습니다
- [ ] 발견한 것이 전부 세 갈래 중 하나로 분류됐습니다
- [ ] 추정치였던 임계치가 실측값으로 바뀌었습니다 — **또는 왜 못 바꿨는지가 적혀 있습니다**
- [ ] `SELF_HARM_MARKERS_REVIEWED = True` 입니다
- [ ] `PROGRESS.md` 를 갱신했습니다

# 미리 알고 시작하는 제약

실패가 아니라 **범위 밖**입니다.

| 제약 | 결과 |
| --- | --- |
| 로봇 본체 미연결 | 문 앞으로 이동하는 동작을 확인할 수 없습니다 |
| Qdrant·Mosquitto 배포 불명 | 0-7 에서 안 보이면 10·11절을 건너뜁니다 |
| 임베딩 API 잔액 | 시연까지 아껴야 합니다. 배치를 작게 두고, 끝나면 끕니다 |
| 날씨·병원 조회 미배선 | 5-3 참고. 실패가 아니라 아직 안 만든 것입니다 |
| **실제 어르신 아님** | 발음·리듬·사투리가 실제 사용자와 다릅니다 |

마지막이 중요합니다. **개발자 목소리로 맞춘 임계치는 78세 어르신에게 맞지 않을 수
있습니다.** 여기서 모은 기록은 첫 근사이고, 진짜 사용자 테스트는 별도 항목으로 세워야
합니다. 그 사실을 `PROGRESS.md` 에 남기십시오.

---

## 함께 보는 문서

| 문서 | 언제 |
| --- | --- |
| [FIELD-TEST-233-RESULT.md](FIELD-TEST-233-RESULT.md) | **결과를 적는 곳** |
| [TRACE-MAP.md](TRACE-MAP.md) | 발화·함수·DB·API·조절값 대조표 |
| [PROGRESS.md](PROGRESS.md) | 지금 무엇이 안 되고 있는가 |
| [VERIFICATION.md](VERIFICATION.md) | 마이크 없이 하는 검증 |
| [CONCEPTS.md](CONCEPTS.md) | 왜 이렇게 만들었는가 |
