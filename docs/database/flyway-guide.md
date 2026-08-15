# Flyway 마이그레이션 가이드 (백엔드 스키마 관리)

> 대상: 백엔드 개발자 누구나. "엔티티 바꿨는데 DB는 어떻게 반영돼?"에 답하는 문서.
> 관련 설정: `build.gradle`(flyway 의존성), `application.yml`(ddl-auto=validate, flyway), `src/main/resources/db/migration/`

---

## 0. 한 줄 요약

DB 스키마는 **Flyway가 SQL 파일로 만들고**, **Hibernate는 `validate`로 "엔티티와 맞나" 검사만** 합니다. 엔티티를 바꾸면 **다음 번호의 마이그레이션 SQL 파일을 함께 추가**해야 합니다. 2026-07-28 `V1`로 시작해 현재 `V20`까지 왔습니다(20파일·1,161줄·테이블 19개).

## 1. 왜 바꿨나 — JPA 자동반영 vs Flyway

DB엔 실제 테이블이 있어야 하고, 누군가 `CREATE TABLE` 같은 DDL을 실행해줘야 합니다. 그 "누가 어떻게"의 차이입니다.

| | JPA `ddl-auto=update` (이전) | Flyway + `validate` (현재) |
| --- | --- | --- |
| 스키마 만드는 주체 | Hibernate가 엔티티 보고 자동 | 개발자가 쓴 SQL 파일 |
| SQL 파일 | 없음 | `V1__init.sql`, `V2__...` 로 관리 |
| 변경 이력 | 없음 | `flyway_schema_history` 장부 + PR |
| 타입변경·삭제·데이터이관 | 못 함(더하기만) | 가능 |
| 리뷰/롤백 | 어려움 | 코드처럼 리뷰 가능 |
| Hibernate 역할 | 몰래 스키마 변경 | 검사만(validate) |

`ddl-auto=update`는 편하지만 불투명하고 위험(운영 안티패턴)해서, 스키마가 작던 2026-07-28에 Flyway로 전환했습니다. 이 표의 "이전" 열은 역사이고, 되돌아갈 계획은 없습니다.

## 2. 현재 구성 (역할 분담)

- **Flyway = 짓는 사람**: `db/migration/V*.sql`을 순서대로 실행해 스키마 생성. `flyway_schema_history` 테이블에 "어디까지 실행했는지" 기록하고, 새 버전만 1회씩 적용.
- **Hibernate = 준공검사관**: `spring.jpa.hibernate.ddl-auto: validate` — 스키마를 바꾸지 않고 "엔티티 ↔ DB가 일치하나"만 확인. 안 맞으면 **앱이 아예 안 뜸**(안전장치).

관련 설정 요약:

```yaml
# application.yml (운영/기본)
spring:
  jpa:
    hibernate:
      ddl-auto: validate
  flyway:
    enabled: true
    baseline-on-migrate: false   # 빈 DB 전제
```

```yaml
# backend/src/test/resources/application-datajpa.yml (H2 슬라이스 테스트)
# backend/src/main/resources/application-docs.yml (docs 프로파일도 같은 이유로 off)
spring:
  flyway:
    enabled: false               # H2 + Hibernate create-drop 유지
```

> H2를 쓰는 두 프로파일(`datajpa`, `docs`)에서만 Flyway를 끕니다. `V*.sql`이 PostgreSQL
> 문법이라 H2에서 돌리면 깨지기 때문입니다.
>
> 그렇다고 마이그레이션이 검증되지 않는 것은 아닙니다. `FlywayMigrationValidationTest`가
> **실제 PostgreSQL**(임베디드, Docker 불필요)에 `V1`부터 전부 적용한 뒤 Hibernate
> `validate`까지 태웁니다 — 자세한 것은 §4.

## 3. 스키마를 바꾸는 법 (핵심 워크플로우)

엔티티를 바꾸면 **새 마이그레이션 파일을 추가**합니다.

### 규칙

1. **이미 적용된 마이그레이션은 절대 수정 금지.** (`V1__init.sql` 등) Flyway가 체크섬으로 기억하므로, 바꾸면 배포 시 에러.
2. 변경은 **다음 번호 파일을 새로 추가**해서 delta만 작성.
3. **번호를 고르기 전에 `git pull` 하고 디렉터리를 확인한다.** 같은 번호가 둘이면 Flyway는
   기동 시점에 `Found more than one migration with version N`으로 죽고, DB가 아예 뜨지
   않습니다. 실제로 `V9`에서 겪었습니다(§5 참고).
4. **엔티티 변경과 마이그레이션을 같은 PR**에 담는다.
5. **`FlywayMigrationValidationTest`의 버전 목록에 새 번호를 추가한다.** 이 테스트가
   "V1부터 지금까지가 순서대로 적용됐는지"를 `containsExactly`로 확인하므로, 목록을
   갱신하지 않으면 실패합니다. 파일만 만들고 검증을 잊는 일을 막으려고 일부러 수동입니다.
6. 파일명 규약: `V{번호}__{설명}.sql` (밑줄 **2개**). 번호는 순증가.
7. **파일 머리에 "왜"를 쓴다.** 이 저장소의 마이그레이션은 컬럼 목록만 있는 것이 아니라
   결정의 근거를 담습니다 — `V4`(NULL과 0은 다르다), `V5`(왜 pgvector가 아닌가),
   `V18`(왜 DB 전용 조작이며 물리 안전 조치가 아닌가)이 본보기입니다.

### 예시 — 로봇에 nickname 컬럼 추가

1) 엔티티 수정:

```java
@Column(name = "nickname", length = 50)
private String nickname;
```

2) 새 파일 — 번호는 **디렉터리의 마지막 번호 다음**을 씁니다. 지금이 `V20`이므로 `V21`입니다:
`src/main/resources/db/migration/V21__add_robot_nickname.sql`

```sql
ALTER TABLE robot ADD COLUMN nickname varchar(50);
```

3) `FlywayMigrationValidationTest`의 버전 목록에 `"21"` 추가 → 셋을 함께 커밋 →
   배포 시 Flyway가 `V21` 실행 → Hibernate validate 통과.

> 안전장치: 엔티티만 바꾸고 마이그레이션을 깜빡하면, 배포 때 `validate`가 "그 컬럼 DB에 없다"며 앱을 안 띄웁니다. 조용히 어긋나는 사고를 막아줍니다.

## 4. 검증하는 법 — 테스트 한 줄

새 마이그레이션이 엔티티와 맞는지는 **테스트가 확인합니다.** Docker도 WSL도 필요 없습니다.

```bash
cd backend
./gradlew test --tests "*FlywayMigrationValidationTest"
```

`FlywayMigrationValidationTest`는 임베디드 **실제 PostgreSQL** 서버를 띄워
(`io.zonky.test:embedded-postgres`) `V1`부터 전부 적용한 뒤 Hibernate `validate`로 엔티티와
대조합니다. H2가 아닌 이유는 분명합니다 — H2로는 배열·JSONB·부분 인덱스 차이를 못 잡고,
H2 슬라이스 테스트는 Hibernate가 만든 스키마를 다시 엔티티로 검사하므로 **엔티티가 자기
자신을 검증하는 셈**이 됩니다. 바로 그 실수를 막으려고 있는 테스트입니다.

이 테스트가 실제로 확인하는 것:

| 확인 항목 | 실패하면 뜻하는 것 |
| --- | --- |
| 모든 V 파일이 성공 적용 + 버전 목록 일치 | 새 V 파일을 추가하고 목록을 갱신하지 않았거나, 번호가 충돌했다 |
| Hibernate `validate` 통과 | 엔티티를 고치고 마이그레이션을 빠뜨렸다 |
| 안전 임계 컬럼의 NOT NULL / NULL 허용 | "모르는 것"을 표현해야 할 컬럼을 NOT NULL로 만들었다 |
| CHECK·부분 유니크 제약 존재 | 불변식을 DB가 아니라 애플리케이션에만 두었다 |
| `vector` 확장·`embedding` 컬럼 부재 | pgvector 경로를 되살렸다(§7 참고) |

실패 로그 읽는 법:

- `Schema-validation: ...` → 마이그레이션과 엔티티 불일치. 해당 컬럼을 맞춥니다.
- Flyway 오류 → SQL 자체가 잘못됐거나, 이미 적용된 파일을 수정해 체크섬이 바뀌었습니다.
- `Found more than one migration with version N` → 번호 충돌. 다음 빈 번호로 옮깁니다.

## 5. 배포와 사고 기록

배포에서 할 일은 없습니다. **머지하면 Backend 기동 시 Flyway가 새 V 파일만 자동 적용합니다.**
`baseline-on-migrate: false`이므로 대상 DB는 Flyway가 관리해 온 DB여야 합니다.

> ⚠️ 운영 DB를 비우는 절차는 이 문서에 두지 않습니다. 첫 배포는 2026-07-28에 끝났고,
> 그 뒤로 `DROP SCHEMA public CASCADE`는 절차가 아니라 사고입니다. `vector` 확장까지
> 함께 사라지는데, 초기화 SQL은 데이터 디렉터리가 빈 최초 1회에만 실행되므로 자동으로
> 복구되지 않습니다.

### 겪은 사고 — `V9` 번호 충돌 (S15P11E102-333)

같은 날 두 티켓이 각자 `V9`를 만들었습니다(`app_user.birth_date`와 AI 대화 런타임).
Flyway는 기동 시점에 `Found more than one migration with version 9`로 실패했고,
**빈 데이터베이스가 아예 뜨지 않았습니다.** 나중에 커밋된 쪽을 `V14`로 옮겨 풀었습니다
(그 경위는 `V14__add_ai_conversation_runtime.sql` 파일 머리에 남아 있습니다).

이 사고가 남긴 두 번째 교훈이 더 중요합니다. 충돌로 `FlywayMigrationValidationTest`가
컨텍스트 로딩 단계에서 죽어 있는 동안 **버전 목록 assertion이 한 번도 실행되지 않았고**,
그래서 목록이 `"1"…"13"`에서 `"1"…"8"`로 되돌아간 회귀를 아무도 보지 못했습니다.
"테스트가 빨간불이 아니다"와 "테스트가 돌았다"는 다릅니다.

### 미해결 — 버전 목록이 `V20`을 담고 있지 않습니다 (2026-08-15 확인)

`FlywayMigrationValidationTest`의 `containsExactly` 목록은 `"1"…"19"`에서 멈춰 있는데,
`db/migration/`에는 `V20__allow_non_navigation_operator_scenario_cancellation.sql`이
있습니다. `V20`은 2026-08-08 커밋 `f2852e9b`로 들어왔고, 테스트 파일의 마지막 갱신은
같은 날 더 이른 커밋 `20120f0a`입니다. 즉 §3 규칙 5(목록 갱신)를 빠뜨린 것으로 보이며,
그렇다면 이 테스트는 지금 실패 상태입니다.

바로 위 사고가 남긴 교훈이 같은 자리에서 반복된 셈입니다. **이 문서는 사실만 기록하고
고치지 않습니다** — 코드 수정은 담당 라인에서 별도 티켓으로 다루십시오.

## 6. 파일 위치·네이밍

```
backend/src/main/resources/db/migration/
  V1__init.sql                        # 초기 전체 스키마 (테이블 12개)
  V2__add_robot_runtime_columns.sql   # 컬럼 보강
  V3__create_occupancy_event.sql      # 테이블 신설
  ...
  V20__allow_non_navigation_operator_scenario_cancellation.sql
```

- 접두사 `V`, 버전 숫자, 구분자 `__`(밑줄 2개), 설명(공백은 `_`).
- 한 파일 = 하나의 논리적 변경 권장.

## 7. 자주 하는 질문

- **Q. 엔티티 바꿀 때마다 SQL도 써야 해요?**  네. 대신 기존 파일은 두고 새 V파일만 추가.
- **Q. V1을 잘못 썼으면?**  아직 어디에도 적용 전이면 고쳐도 되지만, 공유/배포된 DB에 한 번이라도 적용됐으면 수정 말고 V2로 바로잡기.
- **Q. embedding(VECTOR)/pgvector는?**  **쓰지 않습니다. 계획이 취소되었습니다(S15P11E102-218).** Upstage 임베딩이 4096차원인데 pgvector 0.8.5의 인덱스 상한이 `vector` 2,000 / `halfvec` 4,000차원이라 인덱스를 만들 수 없습니다. 의미 검색은 외부 벡터 스토어(Qdrant)로 옮겼고, 이 DB에는 V5의 부기 컬럼(`embedding_status`/`embedding_synced_at`/`embedding_model`)만 있습니다. **`CREATE EXTENSION vector;` V파일을 추가하지 마십시오** — 검색 경로가 둘이 되고 그중 하나는 인덱스 없는 순차 스캔입니다. `FlywayMigrationValidationTest.pgvectorIsNotUsed`가 벡터 컬럼과 확장이 없는 것을 능동적으로 검증합니다.
  다만 **운영 컨테이너의 DB에는 `vector` 확장이 실제로 설치돼 있습니다** — `infra/docker/postgres/init/001-enable-vector.sql`이 최초 초기화 때 한 번 실행하기 때문입니다. 테스트가 보는 임베디드 DB에는 이 초기화 SQL이 돌지 않으므로 둘이 다릅니다. 확장이 남아 있는 것은 무해하지만, "쓰지 않는다"와 "설치돼 있지 않다"를 혼동하지 마십시오.
- **Q. 큰 변경의 DDL 초안을 자동으로 얻고 싶다.**  `docs` 프로파일(H2 + `ddl-auto: create-drop`)로 앱을 띄우면 Hibernate가 현행 엔티티 기준 스키마를 만듭니다. 이것을 **초안으로만** 참고하고, 실제 V 파일은 PostgreSQL 방언으로 직접 씁니다 — H2가 만든 DDL에는 배열·JSONB·부분 인덱스가 그대로 옮겨지지 않습니다.
