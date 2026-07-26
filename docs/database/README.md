# Database

## 기술 선택

BOMI의 중앙 데이터베이스는 PostgreSQL 17과 pgvector를 사용합니다.

- 관계형 데이터와 트랜잭션: PostgreSQL
- 임베딩 저장 및 유사도 검색: pgvector
- 운영 이미지: `pgvector/pgvector:0.8.5-pg17`
- 문자 인코딩: UTF-8
- 저장 시각 기준: UTC

귀가 환영 및 맞춤 대화 MVP의 1차 물리 모델은
[`mvp-erd.md`](./mvp-erd.md)에 정의합니다. 현재 ERD는 기존 8개 도메인 테이블에
온보딩 처리 원장 2개를 추가한 10개 테이블이며,
벡터 차원은 임베딩 모델 확정 전까지 `<EMBEDDING_DIM>` 자리표시자로 유지합니다.
전체 PostgreSQL DDL과 JPA Entity는 아직 이 문서의 범위가 아닙니다.

초기 설문 적용 판단, 동의 게이트, 휴식 상태 인지와 온습도 저장 경계는
[`onboarding-rest-environment-design.md`](./onboarding-rest-environment-design.md)에
정리합니다. `onboarding_session`과 `onboarding_answer`는 진행·검증·수정·멱등 반영
원장이며 프로필 조회 원본은 아닙니다. 확인된 최종 사실은 `app_user`, `memory`,
`care_record`에 반영하고, 휴식·온습도는 별도 센서 시계열 테이블 없이 최신 상태와
의미 있는 사건만 저장합니다.

## 연결 원칙

- 운영 DB는 인터넷에 공개하지 않습니다.
- Spring Backend만 Docker 내부 네트워크에서 DB에 접근합니다.
- 운영 접속 주소는 `jdbc:postgresql://postgres:5432/bomi`입니다.
- 로컬 개발에서만 `127.0.0.1:5432`를 사용합니다.
- 실제 비밀번호는 Git에 저장하지 않습니다.

## 스키마 관리

현재는 초기 인프라 단계이므로 pgvector 확장만 최초 초기화 SQL로 활성화합니다.
업무 테이블이 추가되기 시작하면 Flyway를 도입하여 다음 항목을 버전 관리합니다.

- 테이블과 인덱스 생성
- 제약조건 변경
- pgvector 컬럼과 벡터 인덱스
- 기준 데이터 변경

운영 환경에서 Hibernate가 임의로 스키마를 변경하지 않도록
`spring.jpa.hibernate.ddl-auto=validate`를 유지합니다.

## pgvector 사용 원칙

벡터 컬럼의 차원은 사용할 임베딩 모델이 확정된 후 정합니다. 모델이 달라지면 벡터
차원과 의미가 달라질 수 있으므로 각 임베딩에는 최소한 다음 정보를 함께 관리합니다.

- 임베딩 모델 이름과 버전
- 벡터 차원
- 원본 데이터 식별자
- 생성 시각
- 재생성 여부를 판단할 버전 정보

초기 데이터가 적을 때는 정확 검색을 우선하고, 데이터 규모와 조회 패턴을 측정한 뒤
HNSW 또는 IVFFlat 인덱스를 선택합니다.

## 영속성 및 백업

- 운영 데이터 경로: `/home/ubuntu/bomi/data/postgres`
- 논리 백업 형식: `pg_dump -Fc`
- 백업 경로: `/home/ubuntu/bomi/backup`
- 컨테이너 삭제와 데이터 삭제를 별개의 작업으로 취급합니다.
- 백업 성공 여부뿐 아니라 실제 복구 가능 여부를 정기적으로 검증합니다.

실행, 점검, 백업 절차는 `infra/README.md`를 따릅니다.
