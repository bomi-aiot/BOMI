# BOMI 포팅 매뉴얼 ② — 외부 서비스

> 프로젝트가 사용하는 외부 서비스의 **가입 경로·발급 방법·설정 위치**를 정리한 문서입니다.
> **실제 API 키·비밀번호 값은 이 문서에 기재하지 않습니다.** 값은 서버의
> `/home/ubuntu/bomi/secrets/production.env` 와 각 장치의 `.env` 에만 존재합니다.

- 작성 기준 커밋: `[머지 후 기입]` / 작성일: `2026-08-__`

---

## 0. 전체 요약

| # | 서비스 | 용도 | 사용 주체 | 과금 | 필수 여부 |
| --- | --- | --- | --- | --- | --- |
| 1 | **RTZR (VITO Speech)** | STT — 어르신 발화 → 텍스트 | 로봇 `ai_chat` | 유료(무료 크레딧) | **필수** (없으면 대화 불가) |
| 2 | **Typecast** | TTS — 응답 텍스트 → 음성 | 로봇 `ai_chat` | 유료(무료 크레딧) | **필수** (없으면 응답 무음) |
| 3 | **Google Gemini (SSAFY GMS 프록시)** | 대화 응답 생성 · 대화 요약 | 로봇 `ai_chat` + Backend | 유료 | **필수** |
| 4 | **Upstage Embeddings** | 의미 검색용 4096차원 임베딩 | Backend | 유료 | 선택 (없으면 키워드 검색으로 폴백) |
| 5 | **기상청 단기예보 (공공데이터포털)** | 날씨 안부 대화 | 로봇 `ai_chat` | 무료 | 선택 |
| 6 | **Let's Encrypt** | HTTPS 인증서 | EC2 Nginx | 무료 | **필수** (운영 도메인) |
| 7 | **AWS EC2 (SSAFY 제공)** | 서버 호스팅 | 인프라 | SSAFY 제공 | **필수** |
| 8 | **GitLab (SSAFY)** | 형상 관리 · Jenkins 연동 | CI/CD | SSAFY 제공 | **필수** |

### 사용하지 않는 외부 서비스 (명시)

| 항목 | 사용 여부 | 비고 |
| --- | --- | --- |
| 소셜 로그인 (OAuth — Google/Kakao/Naver 등) | **사용하지 않음** | 보호자 웹은 현재 인증 미적용. 단기 접근 제어는 Nginx Basic 인증(htpasswd)으로 처리 |
| Photon Cloud 등 실시간 멀티플레이 | **사용하지 않음** | — |
| 외부 코드 컴파일/실행 서비스 | **사용하지 않음** | — |
| 외부 벡터 DB SaaS (Qdrant Cloud, Pinecone 등) | **사용하지 않음** | Qdrant를 **자체 호스팅** (`qdrant/qdrant:v1.18.3` 컨테이너). 가입 불필요 |
| 클라우드 객체 스토리지 (S3 등) | **사용하지 않음** | 파일은 EC2 로컬 볼륨 |
| 외부 푸시/SMS/이메일 발송 서비스 | **사용하지 않음** | 보호자 알림은 로봇 로컬 큐 + 웹 대시보드 |
| 외부 비전 API | **사용하지 않음** | `ai_vision` 은 로컬 모델로 추론, 네트워크 호출 없음 |

---

## 1. RTZR (VITO Speech) — STT

| 항목 | 내용 |
| --- | --- |
| 제공사 | 리턴제로 (Return Zero) |
| 서비스명 | VITO Speech / RTZR STT OpenAPI |
| 가입·발급 | <https://developers.rtzr.ai/> |
| 문서 | <https://developers.rtzr.ai/docs/> |
| 발급 결과 | `CLIENT_ID`, `CLIENT_SECRET` 쌍 |
| 인증 방식 | Client ID/Secret → 토큰 발급 → Bearer 토큰 (코드가 캐시) |
| 사용 모델 | `sommers`, 언어 `ko` |

**호출 엔드포인트**

| 목적 | URL |
| --- | --- |
| 토큰 발급 | `https://openapi.vito.ai/v1/authenticate` |
| 전사 요청·결과 폴링 | `https://openapi.vito.ai/v1/transcribe` |

**설정 위치** — `robot/ai_chat/.env`

```dotenv
RTZR_CLIENT_ID=<발급받은 client id>
RTZR_CLIENT_SECRET=<발급받은 client secret>
```

**관련 튜닝값** (`robot/ai_chat/.env`)

| 변수 | 기본 | 설명 |
| --- | --- | --- |
| `STT_POLL_INTERVAL_SECONDS` | `0.5` | 전사 결과 폴링 주기 |
| `STT_POLL_TIMEOUT_SECONDS` | `60` | 폴링 최대 대기 |
| `STT_TOKEN_TTL_SECONDS` | `3000` | 인증 토큰 캐시 수명 (재발급 호출 절감) |

**미설정 시 동작** — 음성 인식이 실패해 대화가 진행되지 않습니다. 웨이크워드 감지(openWakeWord)는
로컬 모델이라 계속 동작하므로, "보미야"에는 반응하지만 그 뒤 발화를 못 알아듣는 형태로 나타납니다.

---

## 2. Typecast — TTS

| 항목 | 내용 |
| --- | --- |
| 제공사 | 네오사피엔스 (Neosapience) |
| 가입·발급 | <https://typecast.ai/developers/api> |
| 문서 | <https://docs.typecast.ai/> |
| 발급 결과 | API Key (+ 사용할 **Voice ID**) |
| 인증 방식 | HTTP 헤더 `X-API-KEY` |
| 엔드포인트 | `https://api.typecast.ai/v1/text-to-speech` (POST, JSON) |

**설정 위치** — `robot/ai_chat/.env`

```dotenv
TYPECAST_API_KEY=<발급받은 API 키>
TYPECAST_VOICE_ID=<사용할 목소리 ID>
```

> ⚠️ `TYPECAST_VOICE_ID` 는 API 키와 **별개로 지정해야 합니다.** 콘솔에서 목소리를 고른 뒤
> 그 목소리의 ID를 복사해 넣습니다. 키만 넣고 Voice ID를 비우면 합성 요청이 거부됩니다.

**미설정 시 동작** — 로봇이 응답을 생성해도 소리를 내지 않습니다. 합성 결과는
`LOCALSTORE_DIR` 아래에 캐시되므로, 이미 합성된 문장은 키 없이도 재생될 수 있습니다.

---

## 3. Google Gemini — SSAFY GMS 프록시 경유

| 항목 | 내용 |
| --- | --- |
| 실제 제공사 | Google (Generative Language API) |
| **접속 경로** | **SSAFY GMS 프록시** — Google에 직접 붙지 않습니다 |
| 프록시 base URL | `https://gms.ssafy.io/gmsapi/generativelanguage.googleapis.com` |
| 키 발급 | SSAFY GMS 포털에서 발급받은 키를 사용합니다 (Google AI Studio 키가 아님) |
| 사용 모델 | `gemini-2.5-flash-lite` |

> ★ **Google AI Studio에서 직접 발급한 키로는 동작하지 않습니다.** base URL이 GMS 프록시로
> 고정되어 있으므로, 반드시 SSAFY GMS에서 발급한 키를 사용해야 합니다.
> 외부 환경에서 재현하려면 `LLM_BASE_URL` 과 `robot/ai_chat` 의 호출 URL을
> Google 공식 엔드포인트로 바꾸고 Google 키를 사용해야 합니다.

### 3.1 로봇 (`ai_chat`) — 대화 응답 생성

**설정 위치** — `robot/ai_chat/.env`

```dotenv
GEMINI_API_KEY=<GMS 발급 키>
```

호출 URL: `.../v1beta/models/gemini-2.5-flash-lite:generateContent`

### 3.2 Backend — 대화 요약 생성

**설정 위치** — `/home/ubuntu/bomi/secrets/production.env`

```dotenv
GEMINI_API_KEY=<GMS 발급 키>
LLM_ENABLED=true
```

> ★★ **`GEMINI_API_KEY` 만 넣으면 켜지지 않습니다.** `application.yml` 의 기본값
> `${LLM_ENABLED:false}` 가 조용히 이겨서 요약이 영원히 생성되지 않습니다.
> **두 줄을 항상 함께** 설정합니다. (이 실패는 `UPSTAGE_API_KEY` 에서 실제로 한 번 겪었습니다.)

**Backend 측 관련 설정** (`application.yml` 기본값)

| 프로퍼티 | 환경변수 | 기본값 |
| --- | --- | --- |
| `bomi.llm.enabled` | `LLM_ENABLED` | `false` |
| `bomi.llm.base-url` | `LLM_BASE_URL` | `https://gms.ssafy.io/gmsapi/generativelanguage.googleapis.com` |
| `bomi.llm.model` | `LLM_MODEL` | `gemini-2.5-flash-lite` |
| `bomi.llm.timeout-millis` | `LLM_TIMEOUT_MILLIS` | `8000` |
| `bomi.llm.max-output-tokens` | `LLM_MAX_OUTPUT_TOKENS` | `220` |
| `bomi.llm.max-calls-per-run` | `LLM_MAX_CALLS_PER_RUN` | `20` — **지출 상한** |
| `bomi.llm.sweep-interval-millis` | `LLM_SWEEP_INTERVAL_MILLIS` | `300000` (5분) |

**미설정 시 동작** — 로봇 대화 응답 생성이 불가하고, 백엔드 대화 요약이 생성되지 않습니다.
보호자 대시보드의 요약 영역이 비어 보입니다.

---

## 4. Upstage — 임베딩 (의미 검색)

| 항목 | 내용 |
| --- | --- |
| 제공사 | Upstage |
| 가입·발급 | <https://console.upstage.ai/> |
| 발급 결과 | API Key |
| base URL | `https://api.upstage.ai/v1` |
| 사용 모델 | 저장 `embedding-passage` / 검색 `embedding-query` |
| 출력 차원 | **4096** |

> 저장은 `passage`, 검색은 `query` 모델을 씁니다. 섞어 쓰면 **예외 없이 검색 품질만 조용히**
> 나빠집니다.
>
> 출력이 4096차원이라 pgvector 인덱스를 만들 수 없어 Qdrant를 별도로 둡니다
> (①번 문서 1.5절 참고).

**설정 위치** — `/home/ubuntu/bomi/secrets/production.env`

```dotenv
UPSTAGE_API_KEY=<발급받은 API 키>
EMBEDDING_ENABLED=true
EMBEDDING_SYNC_ENABLED=false     # 최초 색인 때만 true
EMBEDDING_SYNC_BATCH_SIZE=30     # 1회 실행당 과금 호출 상한
```

> ★★ 여기서도 **키만 넣으면 켜지지 않습니다.** `EMBEDDING_ENABLED=true` 를 함께 넣어야 하고,
> `infra/compose.prod.yml` 의 `environment:` 에도 두 변수가 모두 선언돼 있어야 컨테이너에 도달합니다.

**최초 색인 절차 (과금 발생)**

1. `EMBEDDING_ENABLED=true`, `EMBEDDING_SYNC_ENABLED=true`, 작은 `EMBEDDING_SYNC_BATCH_SIZE`(예: 5)로 backend만 재기동
2. `bomi_embedding_billed_calls_total`, `bomi_embedding_rows` 지표를 매 주기 확인
3. 백로그가 0이 되면 **`EMBEDDING_SYNC_ENABLED=false` 로 되돌리고 재기동**
4. 상세 절차·롤백·복구는 `infra/RAG_OPERATIONS.md`

**미설정 시 동작** — 서비스가 죽지 않습니다. 의미 검색만 꺼지고 **키워드·중요도·최근성 랭킹으로
계속 동작**합니다. 꺼졌다는 사실은 기동 로그와 `/actuator/health/rag` 의
`semanticMode=keyword_fallback` 으로 확인합니다.

---

## 5. 기상청 단기예보 — 공공데이터포털

| 항목 | 내용 |
| --- | --- |
| 제공 기관 | 기상청 (공공데이터포털 `data.go.kr`) |
| 서비스명 | 동네예보조회서비스 `VilageFcstInfoService_2.0` |
| 가입·발급 | <https://www.data.go.kr> 회원가입 → 해당 오픈API **활용신청** → 인증키 발급 |
| 요금 | 무료 (일일 트래픽 한도 있음) |
| 엔드포인트 | `https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst` |
| 발표 시각 | 02, 05, 08, 11, 14, 17, 20, 23시 (코드가 최근 발표 시각을 계산) |

**설정 위치** — `robot/ai_chat/.env`

```dotenv
KMA_API_KEY=<공공데이터포털 인증키>
```

> ⚠️ 공공데이터포털은 **일반 인증키(Encoding)** 와 **일반 인증키(Decoding)** 두 가지를 줍니다.
> 잘못 고르면 `SERVICE_KEY_IS_NOT_REGISTERED_ERROR` 가 납니다. 활용신청 승인까지
> 시간이 걸릴 수 있으므로 미리 신청해 둡니다.

**미설정 시 동작** — 날씨 관련 발화만 응답하지 못합니다. 다른 대화는 정상 동작합니다.

---

## 6. Let's Encrypt — TLS 인증서

| 항목 | 내용 |
| --- | --- |
| 제공 기관 | ISRG (Let's Encrypt) |
| 가입 | 계정 가입 불필요. **연락용 이메일만** 등록 |
| 발급 도구 | `certbot/certbot:v5.7.0` 컨테이너 |
| 인증 방식 | HTTP-01 (webroot) |
| 대상 도메인 | `i15e102.p.ssafy.io` |
| 인증서 유효기간 | 90일 (자동 갱신 cron 등록됨) |

**설정 위치** — `/home/ubuntu/bomi/secrets/production.env`

```dotenv
BOMI_DOMAIN=i15e102.p.ssafy.io
LETSENCRYPT_EMAIL=<팀에서 관리하는 실제 이메일>
CERTBOT_CONF_DIR=/home/ubuntu/bomi/data/certbot/conf
CERTBOT_WEBROOT_DIR=/home/ubuntu/bomi/data/certbot/www
```

발급·갱신 절차는 ①번 문서 3.2절과 `infra/README.md` 를 참고합니다.

> ⚠️ Let's Encrypt는 **동일 도메인 주당 발급 횟수 제한**이 있습니다. 절차를 시험할 때는
> `--dry-run` 을 사용합니다.

---

## 7. 자체 호스팅이라 가입이 필요 없는 구성요소

아래는 외부 SaaS가 아니라 **직접 띄우는 컨테이너**입니다. 가입 절차가 없고, 계정/비밀번호는
운영자가 직접 만듭니다.

| 구성요소 | 이미지 | 만들어야 하는 자격증명 | 위치 |
| --- | --- | --- | --- |
| **Qdrant** (벡터 DB) | `qdrant/qdrant:v1.18.3` | `QDRANT_API_KEY` (임의의 긴 랜덤 문자열) | `production.env` |
| **PostgreSQL** | `pgvector/pgvector:0.8.5-pg17` | `POSTGRES_USER` / `POSTGRES_PASSWORD` (`openssl rand -hex 32`) | `production.env` |
| **Mosquitto** (MQTT) | `eclipse-mosquitto:2` | 브로커 사용자/비밀번호 (`mosquitto_passwd` 로 생성) | `secrets/mosquitto/passwords` |
| **Jenkins** | `jenkins/jenkins:2.555.3-jdk21` | 초기 관리자 비밀번호 → GitLab 토큰 등록 | Jenkins Credentials |
| **Nginx Basic 인증** | `nginx:1.30.4-alpine` | `htpasswd` 파일 2개 (operator-console, waypoint-editor) | `production.env` 가 경로 지정 |

**MQTT 자격증명 생성 예시**

```bash
# 운영 브로커 사용자 추가
docker run --rm -it -v /home/ubuntu/bomi/secrets/mosquitto:/m eclipse-mosquitto:2 \
  mosquitto_passwd -c /m/passwords <username>

# 헬스체크 전용 계정 (infra/mqtt.env.example 참고)
MQTT_HEALTH_USERNAME=bomi-healthcheck
MQTT_HEALTH_PASSWORD=<긴 랜덤 문자열>
```

**Nginx Basic 인증 파일 생성 예시**

```bash
htpasswd -c /home/ubuntu/bomi/secrets/operator-console.htpasswd <username>
htpasswd -c /home/ubuntu/bomi/secrets/waypoint-editor.htpasswd <username>
```

토픽 접근 제어는 `infra/docker/mosquitto/production/acl` 에 정의되어 있습니다.

---

## 8. SSAFY 제공 인프라

| 항목 | 내용 |
| --- | --- |
| **AWS EC2** | SSAFY 제공 인스턴스. 도메인 `i15e102.p.ssafy.io` 가 이 인스턴스의 공인 IP를 가리킵니다. 접속은 SSAFY 발급 SSH 키 (`.pem`) |
| **GitLab** | SSAFY GitLab. Jenkins가 push 트리거로 연동되며, Jenkins Credentials에 접근 토큰이 등록되어 있습니다 |
| **GMS (Gemini 프록시)** | 3절 참고 |

> SSH 개인키(`.pem`)는 **저장소에 커밋하지 않습니다.** 로봇의 DB SSH 터널 모드에서도
> `SSH_KEY_PATH` 로 로컬 경로만 참조합니다.

---

## 9. 키를 넣는 위치 — 한눈에 보는 매트릭스

| 키 / 자격증명 | `robot/ai_chat/.env` (Jetson) | `secrets/production.env` (EC2) | 기타 |
| --- | :---: | :---: | --- |
| `RTZR_CLIENT_ID` / `RTZR_CLIENT_SECRET` | ● | | |
| `TYPECAST_API_KEY` / `TYPECAST_VOICE_ID` | ● | | |
| `GEMINI_API_KEY` | ● | ● | 양쪽 모두 필요 |
| `LLM_ENABLED` | | ● | Backend 전용 |
| `KMA_API_KEY` | ● | | |
| `UPSTAGE_API_KEY` / `EMBEDDING_ENABLED` | | ● | |
| `QDRANT_API_KEY` | | ● | |
| `POSTGRES_PASSWORD` | | ● | 로봇은 SSH 터널 경유 시 `DB_PASSWORD` |
| `MQTT_USERNAME` / `MQTT_PASSWORD` | ● | ● | 로봇·백엔드·Pi 모두 |
| `ROBOT_SHARED_SECRET` | ●(`BACKEND_SHARED_SECRET`) | ● | **양쪽 값이 같아야 함** |
| `OPERATOR_SHARED_SECRET` | | ● | |
| `LETSENCRYPT_EMAIL` | | ● | |
| htpasswd 파일 | | ●(경로만) | 파일 실체는 EC2 |
| SSH `.pem` | ●(경로만) | | 파일 실체는 로컬 |

> ★ `robot/ai_chat/.env` 의 `BACKEND_SHARED_SECRET` 와 `production.env` 의
> `ROBOT_SHARED_SECRET` 은 **같은 값**이어야 합니다. 로봇이 이 값을
> `X-Robot-Shared-Secret` 헤더로 보내고 백엔드 필터가 검사합니다.
> 백엔드에만 값이 있고 로봇이 비어 있으면 **401** 을 맞습니다.
> 반대로 백엔드가 비어 있으면 **필터가 전부 통과시킵니다.**

---

## 10. 키 미설정 시 동작 정리 (degradation)

| 미설정 키 | 죽는가 | 실제 증상 |
| --- | --- | --- |
| `RTZR_*` | 대화 불가 | 웨이크워드는 반응하나 발화를 인식 못 함 |
| `TYPECAST_*` | 응답 무음 | 캐시된 문장만 재생 |
| `GEMINI_API_KEY` (로봇) | 대화 불가 | 응답 생성 실패 |
| `GEMINI_API_KEY` / `LLM_ENABLED` (BE) | **안 죽음** | 대화 요약만 생성 안 됨 |
| `UPSTAGE_API_KEY` / `EMBEDDING_ENABLED` | **안 죽음** | 의미 검색 OFF, 키워드 검색으로 폴백 |
| `KMA_API_KEY` | **안 죽음** | 날씨 질문만 응답 불가 |
| `QDRANT_API_KEY` | **안 죽음** | 키가 없으면 Qdrant가 인증을 요구하지 않음 (내부망 전용) |
| `MQTT_USERNAME/PASSWORD` | 시나리오 불가 | 현관 인사·복약 알림·온습도 안부가 전혀 시작되지 않음 |
| `ROBOT_SHARED_SECRET` (BE만 설정) | 로봇 호출 차단 | 401, 경고 로그 (캐시 폴백과 구분됨) |
| `ROBOT_DEVICE_ID` | 시나리오 불가 | `UNKNOWN_ROBOT` 으로 **조용히** 차단 (에러 응답 없음, 서버 로그만) |
| Let's Encrypt 인증서 | 배포 실패 | HTTPS Nginx 기동 불가 |

---

## 11. 비용 관리 원칙

과금 외부 API는 **RTZR·Typecast·Gemini·Upstage** 4종이며, 프로젝트 잔액이 시연까지 버텨야 합니다.

| 안전장치 | 위치 | 내용 |
| --- | --- | --- |
| 기본 OFF | `application.yml` | `EMBEDDING_ENABLED`, `EMBEDDING_SYNC_ENABLED`, `LLM_ENABLED` 전부 기본 `false` |
| 1회 실행 호출 상한 | `production.env` | `EMBEDDING_SYNC_BATCH_SIZE=30`, `LLM_MAX_CALLS_PER_RUN=20` — **튜닝값이 아니라 지출 상한** |
| 테스트 분리 | `build.gradle` | `./gradlew test` 는 과금 테스트를 제외. 과금 테스트는 `billedTest` 로 명시 실행 |
| 운영 킬스위치 | `robot/ai_chat/.env` | `T3_CONSENT_ENABLED`, `EXTRACTION_ENABLED` — 재배포 없이 당일 차단 가능 |
| 재시도 상한 | `robot/ai_chat/.env` | `HTTP_MAX_ATTEMPTS=3`, 백오프 0.5~2초 |

> `FAILED` 행 전체를 무조건 주기 재시도하지 않습니다. 같은 영구 오류를 반복 과금할 수 있습니다.
> 원인이 해결되고 대상 행 수를 검토한 경우에만 `STALE` 로 바꿔 재시도합니다.

---

## 12. 보안 원칙

1. **실제 키 값은 저장소에 커밋하지 않습니다.** 저장소에는 `*.example` 파일만 둡니다.
2. 운영 키는 `/home/ubuntu/bomi/secrets/production.env` (권한 **600**) 에만 둡니다.
3. `docker compose config` 출력에는 비밀값이 렌더링됩니다. 결과를 로그·메신저·이슈에 붙이지 않습니다.
4. 비밀번호를 셸 명령줄에 직접 쓰지 않고 편집기로 파일을 수정합니다 (셸 히스토리 방지).
5. `.env` 파일을 Windows에서 편집한 뒤 Jetson/Pi로 옮길 때는 **`dos2unix`** 를 실행합니다.
   CRLF가 남으면 API 키가 조용히 실패합니다.
6. 키가 유출된 경우: 공급자 콘솔에서 **폐기(revoke) 후 재발급** → `production.env` 및 장치 `.env`
   갱신 → 해당 컨테이너/서비스 재기동.

---

## 부록 A. 발급 후 검증 명령

| 서비스 | 검증 방법 |
| --- | --- |
| RTZR | 토큰 발급 응답 200 확인 → `ai_chat` 기동 후 짧은 발화 1회 |
| Typecast | `ai_chat` 기동 후 응답 1회 → 스피커 출력 확인 |
| Gemini (로봇) | 대화 1왕복 |
| Gemini (BE) | `docker logs bomi-backend` 에서 `llm` 활성 로그 확인, 요약 생성 확인 |
| Upstage | `docker exec bomi-backend curl -s http://localhost:8080/actuator/health/rag` → `semanticMode` 확인 |
| 기상청 | 날씨 질문 1회 |
| Let's Encrypt | `curl --fail https://i15e102.p.ssafy.io/api/health` |
| MQTT | `scripts/deploy/verify-mqtt.sh` |
| 공유 시크릿 | 로봇 문맥 조회가 401 없이 성공하는지 로그 확인 |

## 부록 B. 관련 문서

| 문서 | 경로 |
| --- | --- |
| 빌드·배포 매뉴얼 | `exec/01-build-deploy.md` |
| RAG·임베딩·Qdrant 운영 | `infra/RAG_OPERATIONS.md` |
| 인프라 운영 | `infra/README.md` |
| MQTT 배포 | `scripts/deploy/MQTT_DEPLOYMENT.md` |
| MQTT 토픽 규약 | `docs/mqtt/토픽 규약.md` |
| IoT 게이트웨이 | `iot/raspberry-pi/README.md` |
