# Database

## 기준

BOMI의 중앙 데이터베이스는 PostgreSQL 17과 pgvector를 사용한다.

- 관계형 데이터와 트랜잭션: PostgreSQL
- 기억 임베딩 저장과 의미 검색: pgvector
- 운영 이미지: `pgvector/pgvector:0.8.5-pg17`
- 문자 인코딩: UTF-8
- 저장 시각: `TIMESTAMPTZ`, 애플리케이션 저장 기준 UTC

첫 로봇 연동을 위한 물리 모델은 9개 테이블이다.

```text
app_user
care_relationship
robot
onboarding_session
onboarding_answer
scenario
conversation
memory
care_record
```

ENUM 도형은 별도 테이블이 아니라 `VARCHAR` 컬럼의 허용 값 사전이다. 전체 PostgreSQL DDL과 JPA Entity는 아직 이 문서 범위가 아니다.

## 문서별 역할

| 문서 | 답하는 질문 |
|---|---|
| [`mvp-erd.md`](./mvp-erd.md) | 어떤 테이블과 컬럼을 왜 남겼고, 관계와 코드값은 무엇인가? |
| [`onboarding-rest-environment-design.md`](./onboarding-rest-environment-design.md) | 온보딩·휴식·온습도 데이터를 9개 테이블 안에서 어떻게 흐르게 하는가? |
| `column-definition/BOMI_컬럼정의서.xlsx` | 각 컬럼을 언제 어떻게 쓰며 무엇을 넣으면 안 되는가? |
| `column-definition/snapshots/*.csv` | 컬럼정의서 변경을 Git diff로 어떻게 검토하는가? |

엑셀은 사람이 편집하는 원본이고 CSV는 리뷰용 산출물이다. 엑셀에서 DDL이나 Flyway SQL을 자동 생성하지 않는다.

## 저장 경계

중앙 DB에는 업무에 재사용할 최종 상태와 필요한 근거만 저장한다.

- 저장: 사용자·관계, 로봇의 최신 상태, 시나리오, 대화 텍스트, 검증된 기억, 구조화된 돌봄 기록
- 저장하지 않음: 음성·영상 원본, 고빈도 센서 시계열, MQTT 전체 송수신 로그, 외부 API 응답 전문
- 현재 미포함: Outbox, 수신 중복 제거 원장, 감사 로그, AI 실행 추적

미포함 항목은 불필요하다는 뜻이 아니다. 첫 연동에서 실제 장애와 조회 패턴을 확인한 뒤 별도 생명주기가 필요할 때 추가한다.

## 연결 원칙

- 운영 DB는 인터넷에 공개하지 않는다.
- Spring Backend만 Docker 내부 네트워크에서 DB에 접근한다.
- 운영 접속 주소는 `jdbc:postgresql://postgres:5432/bomi`다.
- 로컬 개발에서만 `127.0.0.1:5432`를 사용한다.
- 실제 비밀번호는 Git에 저장하지 않는다.

## 스키마 관리

초기 인프라에서는 pgvector 확장만 최초 초기화 SQL로 활성화한다. 업무 테이블 구현을 시작하면 Flyway로 다음을 버전 관리한다.

- 테이블·컬럼·인덱스
- FK와 확정된 `CHECK` 제약조건
- pgvector 컬럼과 벡터 인덱스
- 코드값 변경에 필요한 마이그레이션

Hibernate가 운영 스키마를 임의 변경하지 않도록 `spring.jpa.hibernate.ddl-auto=validate`를 유지한다.

ERD에 표시되지 않은 이메일 유일성, FK 삭제 정책, 활성 로봇 수 같은 제약은 DDL 작성 전에 결정한다. 컬럼정의서의 미결정 표시를 임의 기본값으로 바꾸지 않는다.

## pgvector 원칙

`memory.embedding`의 모델과 차원은 검색 기능 구현 전에 확정한다. 그 전까지 타입은 `VECTOR`로만 기록한다.

- `memory.content`를 임베딩 원문으로 사용한다.
- `ACTIVE`이고 `REJECTED`가 아닌 기억만 검색 후보로 삼는다.
- 삭제·만료·대체된 기억은 검색에서 제외한다.
- 초기에는 정확 검색을 사용하고, 데이터 규모와 지연시간을 측정한 뒤 HNSW 또는 IVFFlat을 선택한다.

## 백업

- 운영 데이터 경로: `/home/ubuntu/bomi/data/postgres`
- 논리 백업 형식: `pg_dump -Fc`
- 백업 경로: `/home/ubuntu/bomi/backup`
- 컨테이너 삭제와 데이터 삭제를 별개 작업으로 취급한다.
- 백업 파일 생성뿐 아니라 실제 복구 가능 여부를 정기적으로 검증한다.

실행, 점검, 백업 절차는 `infra/README.md`를 따른다.
