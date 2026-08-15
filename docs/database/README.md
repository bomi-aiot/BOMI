# Database

## 기술 선택

BOMI의 중앙 데이터베이스는 PostgreSQL 17이고, 의미 검색용 벡터는 이 DB가 아니라
외부 벡터 스토어 Qdrant에 둡니다(S15P11E102-218).

- 관계형 데이터와 트랜잭션: PostgreSQL 17 (권위 있는 원본)
- 임베딩 저장 및 유사도 검색: Qdrant (파생 인덱스, gRPC 6334, 4096차원)
- 운영 이미지: `pgvector/pgvector:0.8.5-pg17` — 확장을 쓰지는 않지만 이미지는 그대로
  둡니다. 바꾸면 초기화 SQL과 기존 데이터 디렉터리의 전제가 함께 흔들립니다.
- 문자 인코딩: UTF-8
- 저장 시각 기준: UTC

도메인과 ERD는 확정됐습니다. 물리 테이블은 19개이고, 각 테이블의 의미와 관계는
[`mvp-erd.md`](mvp-erd.md)가 정본입니다. 벡터 차원은 임베딩 모델(Upstage
`solar-embedding-1-large`)이 정해지면서 4096으로 확정됐습니다.

## 연결 원칙

- 운영 DB는 인터넷에 공개하지 않습니다.
- DB에 직접 붙는 컨테이너는 둘뿐입니다 — Spring Backend(읽기·쓰기)와 `db-viewer`
  (운영 확인용, 연결마다 `default_transaction_read_only`를 켜고 데모 리셋 기능만
  예외적으로 씁니다). 둘 다 `internal: true`인 `backend-net` 안에 있습니다.
  그 밖의 서비스는 Backend API를 거칩니다.
- 운영 접속 주소는 `jdbc:postgresql://postgres:5432/${POSTGRES_DB}`입니다.
  호스트와 포트는 compose가 고정하고, DB 이름만 `production.env`에서 옵니다(예시값 `bomi`).
- 로컬 개발에서만 `127.0.0.1:5432`를 사용합니다.
- 실제 비밀번호는 Git에 저장하지 않습니다.

## 스키마 관리

스키마의 유일한 소유자는 Flyway입니다. 2026-07-28 `V1__init.sql`로 도입해 현재
`V20`까지 왔고(20파일·테이블 19개), Backend 기동 시 자동 적용됩니다.
Flyway가 버전 관리하는 것은 다음과 같습니다.

- 테이블과 인덱스 생성
- 제약조건 변경 (CHECK로 불변식을 DB가 직접 강제하는 것을 선호합니다)
- 임베딩 동기화 부기 컬럼 (`embedding_status`/`embedding_synced_at`/`embedding_model`)
- 기준 데이터 변경과 백필

운영 환경에서 Hibernate가 임의로 스키마를 변경하지 않도록
`spring.jpa.hibernate.ddl-auto=validate`를 유지합니다.

## 벡터 스토어 경계 — 왜 pgvector가 아닌가

임베딩 벡터는 이 DB에 저장하지 않습니다. Upstage `solar-embedding-1-large`의 출력이
4096차원인데, pgvector 0.8.5가 인덱싱할 수 있는 상한은 `vector` 2,000 / `halfvec`
4,000차원입니다. 즉 4096차원은 인덱스를 아예 만들 수 없고 남는 선택지가 인덱스 없는
순차 스캔뿐이었습니다. 한국어 품질 때문에 Upstage를 포기할 수 없다고 판단해,
저장소 쪽을 바꿨습니다(S15P11E102-218).

경계는 다음과 같습니다.

- **PostgreSQL이 권위**입니다. 원문(`conversation_message`), 요약
  (`conversation_summary`), 장기 기억(`memory`)의 정본은 전부 여기 있습니다.
- **Qdrant는 파생 인덱스**입니다. 유실되어도 재색인으로 복구할 수 있어야 합니다.
- 복구를 가능하게 하는 것이 `V5`가 추가한 부기 컬럼 세 개입니다 —
  `embedding_status`(PENDING/SYNCED/STALE/FAILED), `embedding_synced_at`,
  `embedding_model`. 무엇을 다시 임베딩해야 하는지 아는 유일한 단서이고, 이것이
  없으면 복구 수단은 "전체 재색인"밖에 남지 않습니다.
- **`CREATE EXTENSION vector;`를 새 마이그레이션으로 추가하지 마십시오.** 검색
  경로가 둘로 갈라지고, 그중 하나는 인덱스가 없습니다.

운영 컨테이너에는 최초 초기화 SQL(`infra/docker/postgres/init/001-enable-vector.sql`)이
남아 있어 `vector` 확장 자체는 설치돼 있습니다. 쓰지 않을 뿐입니다. 지우지 않는 이유는
기존 데이터 디렉터리를 건드리지 않기 위해서입니다.

## 영속성 및 백업

- 운영 데이터 경로: `/home/ubuntu/bomi/data/postgres`
- 논리 백업 형식: `pg_dump -Fc`
- 백업 경로: `/home/ubuntu/bomi/backup`
- 컨테이너 삭제와 데이터 삭제를 별개의 작업으로 취급합니다.
- 백업 성공 여부뿐 아니라 실제 복구 가능 여부를 정기적으로 검증합니다.

PostgreSQL 컨테이너의 실행·점검·백업 절차는 [`infra/README.md`](../../infra/README.md)를
따릅니다. Qdrant 운영은 [`infra/RAG_OPERATIONS.md`](../../infra/RAG_OPERATIONS.md)가 따로 있습니다.
