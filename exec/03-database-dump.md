# BOMI 포팅 매뉴얼 ③ — DB 덤프

> 제출용 DB 덤프 파일의 생성·검증·복원 절차입니다.
> **덤프 파일 자체는 제출 직전 마지막에 한 번 생성합니다.** (아래 §2 타이밍 참고)

- 덤프 파일: `exec/bomi-dump-[YYYYMMDD-HHMM].sql` ← **생성 후 실제 파일명 기입**
- 생성 스크립트: `exec/scripts/dump-db.sh`
- 기준 커밋: `[머지 후 기입]` / 생성일: `2026-08-__`

---

## 1. 덤프 파일 사양

| 항목 | 값 | 이유 |
| --- | --- | --- |
| 형식 | **평문 SQL** (`-Fc` 아님) | `pg_restore` 없이 `psql -f` 한 줄로 복원 가능 |
| 범위 | 스키마 + 데이터 (전체) | 시연 재현에 시드 데이터가 필요 |
| 소유자 | `--no-owner` | 복원 대상의 롤 이름이 달라도 복원됨 |
| 권한 | `--no-privileges` | 같은 이유로 GRANT/REVOKE 제거 |
| 기존 객체 | `--clean --if-exists` | 재복원 시 멱등 |
| 식별자 | `--quote-all-identifiers` | 예약어 충돌 방지 |
| 포함 | `flyway_schema_history` 테이블 | **복원 후 Flyway 가 마이그레이션을 재실행하지 않게 함** |
| 포함 | `CREATE EXTENSION IF NOT EXISTS "vector"` | pg_dump 가 자동 생성 |
| 미포함 | API 키·비밀번호 | 시크릿은 DB가 아니라 `production.env` 에만 존재 |

파일 맨 앞에 메타 헤더가 자동으로 붙습니다.

```sql
-- ============================================================
-- BOMI DB 덤프
--   생성 시각   : 2026-08-10T03:12:44+09:00
--   기준 커밋   : a1b2c3d4e5f6
--   PostgreSQL  : 17.x
--   pgvector    : 0.8.5
--   Flyway 최종 : 20
-- ...
```

> ⚠️ **`--clean` 이므로 복원 시 대상 DB의 기존 테이블을 DROP 합니다.**
> 운영 DB에 실수로 실행하지 않도록 주의하세요.

---

## 2. 언제 뜨는가 — 타이밍

덤프는 **가장 마지막**입니다. 앞의 어느 단계가 바뀌어도 덤프를 다시 떠야 하기 때문입니다.

```
  코드 최종 머지 (main)
        ↓
  배포 성공 확인 (deploy-production.sh 통과)
        ↓
  Flyway 마이그레이션 반영 확인   ← 새 V*.sql 이 있으면 여기서 스키마가 바뀐다
        ↓
  마지막 시연 리허설 (4개 시나리오)
        ↓
  ★ 여기서 덤프 ★                ← reset 적용 후, 시연 가능한 상태로
        ↓
  exec/ 커밋 & push
```

**왜 리허설 뒤인가** — 리허설을 돌리면 시나리오가 `NAVIGATING` 으로 남거나 로봇이 `SAFE_STOP`
으로 잠길 수 있습니다. 그 상태로 덤프를 뜨면 심사자가 복원했을 때 **로봇이 처음부터 잠긴 채로
시작**합니다. `--reset` 옵션이 `scripts/dev/reset-demo.sql` 을 적용해 이걸 풀고 덤프합니다.

---

## 3. ★ 최후의 순간 실행 절차 (복붙용)

### 3-1. EC2 접속 후 최신 소스 확인

```bash
ssh -i <키파일>.pem ubuntu@i15e102.p.ssafy.io
cd /home/ubuntu/bomi/deploy/source
git checkout main && git pull
git rev-parse --short=12 HEAD        # ← 이 값을 문서 3곳의 [머지 후 기입]에 넣는다
```

### 3-2. 덤프 생성 + 자동 검증 (한 줄)

```bash
chmod +x exec/scripts/dump-db.sh
exec/scripts/dump-db.sh --reset
```

정상 출력 예시:

```
[dump] 대상: 컨테이너=bomi-postgres  DB=bomi  사용자=bomi
[dump] reset-demo.sql 적용 (SAFE_STOP 해제 + 잔여 시나리오 정리)
[dump] 덤프 생성 중 → bomi-dump-20260810-0312.sql
[dump] 생성 완료: /home/ubuntu/.../exec/bomi-dump-20260810-0312.sql (２.１M)
[dump] 복원 검증 시작 → 임시 DB bomi_dumpcheck_12345

  ── 검증 결과 ──────────────────────────────
  테이블 수              원본 34 / 복원 34
  pgvector 확장          0.8.5
  Flyway 최종 버전       20
  app_user               원본 3      복원 3      OK
  memory                 원본 128    복원 128    OK
  ...
  ───────────────────────────────────────────

[dump] ✅ 복원 검증 통과
[dump] 제출 파일: .../exec/bomi-dump-20260810-0312.sql
```

> **`✅ 복원 검증 통과` 가 안 보이면 그 덤프는 제출하지 않습니다.**
> 스크립트가 임시 DB에 실제로 복원해 보고 테이블 수·행 수·pgvector·Flyway 버전을
> 대조합니다. 실패 시 종료코드가 0이 아니고, 임시 DB는 자동 삭제됩니다.

### 3-3. 파일을 로컬로 가져오기

```bash
# 로컬(Windows PowerShell)에서
scp -i <키파일>.pem ubuntu@i15e102.p.ssafy.io:/home/ubuntu/bomi/deploy/source/exec/bomi-dump-*.sql C:\BOMI\exec\
```

### 3-4. 문서의 자리표시자 채우기

| 파일 | 채울 것 |
| --- | --- |
| `exec/01-build-deploy.md` 9행 | `작성 기준 커밋`, `작성일` |
| `exec/01-build-deploy.md` 부록 A | 검증 체크리스트 15줄 |
| `exec/02-external-services.md` 8행 | `작성 기준 커밋`, `작성일` |
| `exec/03-database-dump.md` (이 문서) | 덤프 **파일명**, 기준 커밋, 생성일 |

### 3-5. 커밋

```bash
cd C:\BOMI
git checkout main && git pull
git add exec/
git commit -m "[docs] 포팅 매뉴얼(exec) 추가"
git push
```

> ①번 문서에서 정한 대로, `exec/` 는 그때까지 **untracked 상태로 두고 커밋하지 않습니다.**
> `git clean -fd` 와 `git stash -u` 만 피하면 브랜치를 옮겨다녀도 살아남습니다.

---

## 4. 스크립트가 자동으로 확인하는 것

| # | 검사 | 실패 시 |
| --- | --- | --- |
| 1 | `bomi-postgres` 컨테이너 존재·healthy | 중단 |
| 2 | `POSTGRES_USER`/`POSTGRES_DB` 읽기 | 중단 |
| 3 | 덤프 파일이 비어 있지 않음 | 중단 |
| 4 | 임시 DB에 `ON_ERROR_STOP=1` 로 실제 복원 | 중단 + 오류 로그 20줄 출력 |
| 5 | 원본 ↔ 복원 **테이블 수** 일치 | 중단 |
| 6 | 복원본에 **pgvector 확장** 존재 | 중단 |
| 7 | 주요 테이블 **행 수** 일치 | 중단 |
| 8 | 임시 DB 삭제 | (항상 실행) |

> ④번의 `ON_ERROR_STOP=1` 이 핵심입니다. 이게 없으면 절반이 실패해도 `psql` 종료코드가 0이라
> **"복원됐다"고 착각**합니다.

---

## 5. 심사자용 복원 절차 (문서에 안내할 내용)

### 5-1. Docker Compose 로 (권장)

```bash
# pgvector 가 포함된 이미지로 DB 기동
docker compose up -d postgres

# 덤프 복원
docker exec -i bomi-postgres psql -v ON_ERROR_STOP=1 -U bomi -d bomi \
  < exec/bomi-dump-[YYYYMMDD-HHMM].sql

# 확인
docker exec bomi-postgres psql -U bomi -d bomi -tAc \
  "SELECT extversion FROM pg_extension WHERE extname='vector';"
docker exec bomi-postgres psql -U bomi -d bomi -tAc \
  "SELECT version FROM flyway_schema_history WHERE success ORDER BY installed_rank DESC LIMIT 1;"
```

### 5-2. 로컬 PostgreSQL 로

```bash
# 전제: PostgreSQL 17 + pgvector 0.8.5 설치되어 있을 것
createdb -U bomi bomi
psql -U bomi -d bomi -v ON_ERROR_STOP=1 -f exec/bomi-dump-[YYYYMMDD-HHMM].sql
```

> **전제 조건**: 대상 서버에 **pgvector 확장 바이너리**가 설치돼 있어야 합니다.
> 덤프 안의 `CREATE EXTENSION vector` 는 확장을 *등록*할 뿐 *설치*하지 않습니다.
> `pgvector/pgvector:0.8.5-pg17` 이미지를 쓰면 자동 충족됩니다.

### 5-3. 복원 후 Backend 기동

Flyway 이력이 덤프에 포함돼 있으므로 **마이그레이션이 재실행되지 않습니다.**
Backend는 스키마 검증만 하고 정상 기동합니다.

```bash
docker compose -f infra/compose.prod.yml up -d backend
docker exec bomi-backend curl -s http://localhost:8080/actuator/health
```

---

## 6. 문제 해결

| 증상 | 원인 | 조치 |
| --- | --- | --- |
| `type "vector" does not exist` | 대상 서버에 pgvector 바이너리 없음 | `pgvector/pgvector:0.8.5-pg17` 이미지 사용, 또는 `apt install postgresql-17-pgvector` |
| `extension "vector" has no installation script for version "0.8.5"` | pgvector 버전 불일치 | 이미지 태그를 `0.8.5-pg17` 로 맞춤 |
| 복원 후 Backend 기동 시 Flyway 오류 | `flyway_schema_history` 누락 | 덤프를 전체 범위로 다시 생성 (`--schema-only` 쓰지 말 것) |
| 복원 후 로봇이 움직이지 않음 | `SAFE_STOP` 상태로 덤프됨 | `--reset` 옵션으로 다시 덤프, 또는 복원 후 `scripts/dev/reset-demo.sql` 적용 |
| `ACTIVE_SCENARIO_EXISTS` 로 시나리오 차단 | 리허설 잔여 시나리오가 `NAVIGATING` | 위와 동일 |
| 스크립트가 `컨테이너를 찾을 수 없습니다` | 컨테이너명 다름 | `BOMI_PG_CONTAINER=<이름> exec/scripts/dump-db.sh` |

---

## 7. 개인정보 확인 (제출 전 1회)

덤프에는 시연용 시드 데이터(`scripts/dev/seed-kim-sunja.sql`)와 리허설 중 생성된 대화 기록이
들어갑니다. 제출 전 아래를 확인합니다.

```bash
# 실제 팀원 이름·연락처가 들어갔는지 확인
grep -iE '010-[0-9]{4}|@(gmail|naver|daum)' exec/bomi-dump-*.sql | head

# API 키 형태 문자열이 섞였는지 확인 (원칙상 DB에는 없어야 함)
grep -iE 'sk-|api[_-]?key|secret' exec/bomi-dump-*.sql | head
```

- 출력이 없으면 정상입니다.
- 실제 개인 연락처가 나오면 시드 값으로 치환한 뒤 다시 덤프합니다.

---

## 8. 관련 파일

| 파일 | 역할 |
| --- | --- |
| `exec/scripts/dump-db.sh` | 덤프 생성 + 복원 검증 |
| `scripts/dev/reset-demo.sql` | SAFE_STOP 해제 + 잔여 시나리오 정리 |
| `scripts/dev/seed-kim-sunja.sql` | 시연용 어르신 시드 데이터 |
| `backend/src/main/resources/db/migration/V*.sql` | Flyway 스키마 정의 (V1~V20) |
| `infra/docker/postgres/init/001-enable-vector.sql` | 컨테이너 최초 기동 시 pgvector 활성화 |
| `docs/database/mvp-erd.md` | ERD |
| `docs/database/column-definition/BOMI_컬럼정의서.xlsx` | 컬럼 정의서 |
| `docs/database/flyway-guide.md` | Flyway 운영 가이드 |
