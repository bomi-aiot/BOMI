# Flyway 마이그레이션 가이드 (백엔드 스키마 관리)

> 대상: 백엔드 개발자 누구나. "엔티티 바꿨는데 DB는 어떻게 반영돼?"에 답하는 문서.
> 관련 설정: `build.gradle`(flyway 의존성), `application.yml`(ddl-auto=validate, flyway), `src/main/resources/db/migration/`

---

## 0. 한 줄 요약

이제 DB 스키마는 **Flyway가 SQL 파일로 만들고**, **Hibernate는 `validate`로 "엔티티와 맞나" 검사만** 합니다. 엔티티를 바꾸면 **마이그레이션 SQL 파일(V2, V3...)을 함께 추가**해야 합니다.

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

`ddl-auto=update`는 편하지만 불투명하고 위험(운영 안티패턴)해서, 스키마가 작은 초기에 Flyway로 전환했습니다.

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
# application-datajpa.yml (H2 슬라이스 테스트)
spring:
  flyway:
    enabled: false               # 테스트는 H2 + Hibernate create-drop 유지
```

> 테스트(H2)에서는 Flyway를 끕니다. V*.sql은 PostgreSQL 문법이라 H2에서 돌리면 깨지기 때문.

## 3. 스키마를 바꾸는 법 (핵심 워크플로우)

엔티티를 바꾸면 **새 마이그레이션 파일을 추가**합니다.

### 규칙

1. **이미 적용된 마이그레이션은 절대 수정 금지.** (`V1__init.sql` 등) Flyway가 체크섬으로 기억하므로, 바꾸면 배포 시 에러.
2. 변경은 **다음 번호 파일을 새로 추가**해서 delta만 작성. (`V2__...`, `V3__...`)
3. **엔티티 변경과 마이그레이션을 같은 PR**에 담는다.
4. 파일명 규약: `V{번호}__{설명}.sql` (밑줄 **2개**). 번호는 순증가.

### 예시 — 로봇에 nickname 컬럼 추가

1) 엔티티 수정:

```java
@Column(name = "nickname", length = 50)
private String nickname;
```

2) 새 파일 `src/main/resources/db/migration/V2__add_robot_nickname.sql`:

```sql
ALTER TABLE robot ADD COLUMN nickname varchar(50);
```

3) 둘을 함께 커밋 → 배포 시 Flyway가 V2 실행 → Hibernate validate 통과.

> 안전장치: 엔티티만 바꾸고 마이그레이션을 깜빡하면, 배포 때 `validate`가 "그 컬럼 DB에 없다"며 앱을 안 띄웁니다. 조용히 어긋나는 사고를 막아줍니다.

## 4. 로컬에서 검증하는 법 (배포 전 리허설)

새 마이그레이션이 엔티티와 맞는지 **실제 PostgreSQL**에 한 번 띄워 확인합니다. (H2 테스트만으론 배열/JSONB/타입 차이를 못 잡음)

빈 Postgres 준비 (Docker; SSAFY에서 Docker Desktop이 막히면 WSL2 안에서 Docker 엔진 사용):

```bash
# WSL 우분투 (repo는 /mnt/c/BOMI)
sudo service docker start
cd /mnt/c/BOMI
sudo docker compose down -v          # 빈 상태 보장
sudo docker compose up -d postgres
```

앱 실행 (윈도우 Git Bash):

```bash
cd /c/BOMI/backend
./gradlew bootRun
```

로그 확인:

- ✅ `Migrating schema "public" to version "N - ..."` → `Started BomiBackendApplication` → validate 통과.
- ❌ `Schema-validation: ...` → 마이그레이션과 엔티티 불일치. 해당 컬럼 수정.

확인 후 `Ctrl+C`.

## 5. 배포 시 주의 (첫 Flyway 배포)

- Flyway V1은 **빈 스키마**에서 실행되어야 합니다. 과거 `ddl-auto=update`로 만들어진 구 테이블이 남아 있으면 `CREATE TABLE`이 충돌합니다.
- 첫 배포 전, 대상 DB가 비어 있지 않으면 비우고 시작:

  ```sql
  DROP SCHEMA public CASCADE;
  CREATE SCHEMA public;
  GRANT ALL ON SCHEMA public TO bomi;
  GRANT ALL ON SCHEMA public TO public;
  ```

- 순서: **DB 비우기 → 곧바로 배포** (구 update 앱이 재기동으로 테이블을 재생성하지 못하게).
- 데이터를 보존해야 하는데 스키마가 이미 있는 경우엔 `baseline-on-migrate: true`가 필요하지만, 구 스키마가 현행 엔티티와 다르면 validate가 깨질 수 있어 권장하지 않습니다(초기엔 비우고 시작이 깔끔).
- **두 번째 배포부터는** 그냥 머지만 하면 Flyway가 새 V파일만 자동 적용합니다.

## 6. 파일 위치·네이밍

```
backend/src/main/resources/db/migration/
  V1__init.sql              # 초기 전체 스키마
  V2__add_robot_nickname.sql
  V3__...
```

- 접두사 `V`, 버전 숫자, 구분자 `__`(밑줄 2개), 설명(공백은 `_`).
- 한 파일 = 하나의 논리적 변경 권장.

## 7. 자주 하는 질문

- **Q. 엔티티 바꿀 때마다 SQL도 써야 해요?**  네. 대신 기존 파일은 두고 새 V파일만 추가.
- **Q. V1을 잘못 썼으면?**  아직 어디에도 적용 전이면 고쳐도 되지만, 공유/배포된 DB에 한 번이라도 적용됐으면 수정 말고 V2로 바로잡기.
- **Q. embedding(VECTOR)/pgvector는?**  **쓰지 않습니다. 계획이 취소되었습니다(S15P11E102-218).** Upstage 임베딩이 4096차원인데 pgvector 0.8.5의 인덱스 상한이 `vector` 2,000 / `halfvec` 4,000차원이라 인덱스를 만들 수 없습니다. 의미 검색은 외부 벡터 스토어(Qdrant)로 옮겼고, 이 DB에는 V5의 부기 컬럼(`embedding_status`/`embedding_synced_at`/`embedding_model`)만 있습니다. **`CREATE EXTENSION vector;` V파일을 추가하지 마십시오** — 검색 경로가 둘이 되고 그중 하나는 인덱스 없는 순차 스캔입니다. `FlywayMigrationValidationTest.pgvectorIsNotUsed`가 확장이 없는 것을 능동적으로 검증합니다.
- **Q. 큰 변경의 DDL 초안을 자동으로 얻고 싶다.**  Hibernate 스키마 생성 스크립트로 초안을 뽑아 참고할 수 있음(팀에 문의).
