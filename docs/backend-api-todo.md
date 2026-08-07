# 보호자 웹 — 앞으로 필요한 백엔드 API

> 프론트(`frontend/`)는 2026-08-07 기준으로 **mock 데이터를 완전히 제거**하고
> 백엔드 API 응답만 화면에 노출합니다. 백엔드에 엔드포인트가 없는 기능은
> 서비스 계층(`src/services/bomiService.ts`)과 화면 양쪽에서 함께 제거했습니다.
>
> 아래는 그때 잘라낸 기능을 되살리기 위해 **백엔드에 만들어야 하는 API 목록**이며,
> 그대로 작업 지시 프롬프트로 사용할 수 있게 작성했습니다.

---

## 현재 연동 상태 (참고)

프론트가 실제로 호출 중인 엔드포인트 — 여기는 건드릴 필요 없습니다.

| 화면 | 호출 |
| --- | --- |
| 오늘(대시보드) | `GET /api/v1/guardian/dashboard` |
| 어르신 정보 | `GET /api/v1/elders/profile`, `GET /api/v1/memories`, `GET /api/v1/known-persons` |
| 공유된 생활 정보 | `GET /api/v1/memories` |
| 확인할 일 | `GET /api/v1/confirmation-requests`, `POST /{id}/resolve`, `POST /{id}/undo` |
| 복약 관리 | `GET/POST /api/v1/care-records/medications`, `PUT /{id}`, `POST /{id}/toggle-status`, `POST /{id}/toggle-reminder`, `DELETE /{id}`, `GET /api/v1/care-records/medication-responses` |
| 일정 관리 | `GET/POST /api/v1/care-records/schedules`, `PUT /{id}` |

---

## 작업 프롬프트

BOMI 백엔드(`backend/`, Spring Boot, `com.ssafy.bomi`)에 아래 API를 추가해 주세요.
기존 가디언 API 컨벤션을 그대로 따릅니다 — 단일 어르신 전제(P0)라 경로에 `elderId` 없음,
`/api/v1/...` 접두, `@Tag` 로 Swagger 그룹 지정, DTO 는 `web/dto` 패키지에 record 로 정의.
각 항목의 "FE 계약"은 프론트가 되살릴 때 기대하는 요청/응답 모양입니다.

### 1. (P0 · 보안) 보호자 인증과 어르신 스코프

**문제**: 현재 모든 `/api/v1/guardian`, `/api/v1/elders`, `/api/v1/memories`,
`/api/v1/care-records`, `/api/v1/known-persons`, `/api/v1/confirmation-requests` 엔드포인트가
인증 없이 열려 있고 어르신 1명을 전역 전제로 조회합니다. 로봇 채널(`RobotChannelAuthFilter`)과
운영자 채널(`OperatorChannelAuthFilter`)에는 필터가 있지만 보호자 채널에는 없습니다.

**요청**
- 보호자 채널 인증 필터/시큐리티 설정 추가 (`config/GuardianChannelAuthFilter` 등).
- 인증된 보호자 → `care_relationship` 조회 → 접근 가능한 어르신으로 모든 질의를 제한.
- 다른 보호자의 어르신 리소스 접근 시 403.
- 다중 어르신 대응 시 `GET /api/v1/guardian/elders` (내가 볼 수 있는 어르신 목록)와
  선택된 어르신을 지정하는 방법(헤더 `X-Elder-Id` 또는 경로 파라미터)을 함께 정의.

> 프론트에는 원래 `VITE_GUARDIAN_API_AUTH_READY` 플래그가 있었고, 이 항목이 끝나기 전까지
> 실 API 호출을 막는 용도였습니다. 지금은 제거했으므로 이 API가 **가장 먼저** 필요합니다.

---

### 2. (P1) 대화 정보(memory) 쓰기 API

**현황**: `MemoryController` 에 `GET /api/v1/memories` **조회만** 있습니다.
그래서 "공유된 생활 정보" 화면은 읽기 전용이고, 보호자가 정보를 직접 추가·수정·삭제하거나
대화 활용을 끄는 기능이 프론트에서 제거된 상태입니다.

**요청**
- `POST /api/v1/memories` — 보호자가 직접 추가
- `PUT /api/v1/memories/{id}` — 내용/키워드/공개범위 수정
- `DELETE /api/v1/memories/{id}` — soft delete (`lifecycle_status = DELETED`)
- `POST /api/v1/memories/{id}/toggle-enabled` — 대화 활용 on/off

**스키마 선행 작업**: `memory` 테이블에 프론트가 쓰는 두 컬럼이 없습니다.
- `title` — 지금은 FE 가 `keywords[0]` 또는 `content` 앞 20자로 임의 생성 중
- `is_enabled` — 지금은 FE 가 `lifecycle_status === 'ACTIVE'` 로 대체 중
둘 중 하나를 고르세요: (a) 컬럼 추가, (b) 파생 규칙을 서버 응답에 명시적으로 포함.

**FE 계약**
```
POST /api/v1/memories
{ "memoryType": "PREFERENCE|HOBBY|DAILY_ROUTINE|PERSONAL_RELATIONSHIP|LIFE_EVENT|FAMILY_MEMORY|OTHER",
  "title": "string", "content": "string", "keywords": ["string"],
  "visibility": "PRIVATE|SHARED_WITH_PRIMARY|SHARED_WITH_GUARDIANS" }
→ 200 MemoryDto (GET /v1/memories 와 동일 스키마)
```
`source` 는 서버가 `GUARDIAN`, `verificationStatus` 는 `GUARDIAN_CONFIRMED` 로 세팅.

---

### 3. (P1) 어르신 기본정보 · 대화 설정 저장 API

**현황**: `ElderProfileController` 에 `GET /api/v1/elders/profile` **조회만** 있습니다.
"어르신 정보" 화면은 전부 읽기 전용이고 저장 버튼이 없습니다.

**요청**
- `PUT /api/v1/elders/profile` — 호칭(`preferredName`)과 대화 설정 저장

**FE 계약**
```
PUT /api/v1/elders/profile
{ "preferredName": "string",
  "conversationPreferences": {
      "speechRate": "SLOW|NORMAL|FAST",
      "volume": "QUIET|NORMAL|LOUD",
      "repeatWhenUnclear": true } }
→ 200 ElderProfileDto (GET 과 동일 스키마)
```
`conversationPreferences` 는 `app_user` 의 JSON 컬럼을 그대로 씁니다.
저장 즉시 로봇 대화 문맥(`ConversationContextService`)에 반영되는지 확인 필요.

---

### 4. (P2) 명부(known-persons) 화면용 — 백엔드는 이미 완료

`KnownPersonController` 에 `GET/POST/PUT/DELETE /api/v1/known-persons` 가 **이미 있습니다.**
프론트는 현재 조회만 사용해 어르신 정보 화면의 "중요한 사람"을 채우고 있고,
등록·수정·삭제 화면이 없습니다. **백엔드 작업 불필요** — FE 티켓입니다.

다만 확인할 것 한 가지: `deceasedNote` 는 보호자 화면 전용 내부 메모이며
대화 문맥 API에 실리면 안 됩니다(CLAUDE.md §8 — 회피는 정보가 아니라 금지문으로).
프론트가 이 값을 "중요한 사람" 카드 메모에 노출하므로, 노출 범위가 의도한 대로인지 검토해 주세요.

---

### 5. (P2) 어르신 건강 프로필

**현황**: 프론트 `ElderProfile.healthProfile`(지병 `conditions`, 알레르기 `allergies`,
신체 제약 `physicalLimitations`, 관찰 기록 `observations`)이 타입에는 있으나
DB 스키마가 없어 매퍼가 빈 배열로 채우고 화면에서 감춰져 있습니다.

**요청**
- 스키마 설계 후 `GET/PUT /api/v1/elders/health-profile`
- 관찰 기록은 `GET /api/v1/elders/health-observations` (기간 필터 + 페이징)
- 확인요청(`FactCandidate`)의 `HEALTH` 종류가 확정되면 여기에 반영되도록 연결

건강 데이터는 `healthDataConsentStatus === GRANTED` 인 경우에만 응답에 포함해야 합니다.

---

### 6. (P2) 생활 기록 조회 API (페이징)

**현황**: "생활 기록" 화면이 `GET /v1/guardian/dashboard` 응답 안의
`recentActivities` 배열에만 의존합니다. 대시보드가 주는 만큼만 볼 수 있고
과거 기록 탐색·기간 필터가 불가능합니다.

**요청**
```
GET /api/v1/guardian/activities?from=2026-08-01&to=2026-08-07&cursor=...&size=20
→ { "items": [ActivitySummaryDto], "nextCursor": "string|null" }
```
공개 범위가 `SHARED_WITH_PRIMARY` 또는 `SHARED_WITH_GUARDIANS` 인 항목만 반환.

---

### 7. (P3) 프론트 미사용 중인 기존 API

백엔드에는 있으나 보호자 웹이 아직 호출하지 않는 것 — 화면 기획이 정해지면 연결합니다.

- `POST /api/v1/guardian/walk-requests` — 보호자가 산책을 요청
- `POST /api/v1/operator/robots/{deviceId}/mode-recoveries` — 운영자 전용, 보호자 웹 대상 아님

---

## 프론트 재연결 방법 (백엔드 완료 후)

1. `frontend/src/services/bomiService.ts` 의 `API_ENDPOINTS` 에 새 경로 추가
2. `BomiService` 인터페이스에 메서드 추가 → `HttpBomiService` 에 구현
3. 응답 DTO → 도메인 타입 변환은 `src/services/mappers/` 에 파일 단위로 추가
4. `src/state/BomiContext.tsx` 에 액션 추가 (`runAction` 으로 감싸면 토스트·로딩 처리 자동)
5. 해당 화면에 UI 복구

mock 서비스는 존재하지 않습니다. 새 기능은 반드시 실 API 를 붙여야 화면에 나옵니다.
