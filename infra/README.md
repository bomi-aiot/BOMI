# Infrastructure

BOMI의 Docker Compose, PostgreSQL, Mosquitto, Nginx, Jenkins 설정을 관리합니다.
공개 가능한 설정만 Git으로 관리하고 실제 비밀번호와 API 키는 EC2의
`/home/ubuntu/bomi/secrets`에만 저장합니다.

## 환경 구분

- `../docker-compose.yml`: 로컬 개발용 구성
- `compose.prod.yml`: EC2 운영용 구성
- `production.env.example`: 운영 환경변수 형식 예제
- `docker/postgres/init/`: PostgreSQL 최초 초기화 SQL
- `docker/mosquitto/`: Mosquitto 설정

운영 명령은 별도 안내가 없는 한 Git 저장소 루트에서 실행합니다.

## PostgreSQL 운영 원칙

- 이미지: `pgvector/pgvector:0.8.5-pg17`
- PostgreSQL의 5432 포트는 EC2 호스트와 인터넷에 공개하지 않습니다.
- Backend는 `bomi-backend-net` 내부에서 서비스 이름 `postgres:5432`로 접속합니다.
- 데이터는 `/home/ubuntu/bomi/data/postgres`에 영속화합니다.
- 실제 환경변수는 `/home/ubuntu/bomi/secrets/production.env`에서 읽습니다.
- `docker compose down -v` 또는 데이터 디렉터리 삭제는 운영 환경에서 금지합니다.

## 1. EC2 최초 준비

운영 디렉터리를 만들고 접근 권한을 제한합니다.

```bash
sudo install -d -o ubuntu -g ubuntu -m 750 /home/ubuntu/bomi/data/postgres
sudo install -d -o ubuntu -g ubuntu -m 700 /home/ubuntu/bomi/secrets
sudo install -d -o ubuntu -g ubuntu -m 700 /home/ubuntu/bomi/backup
```

예제 파일을 실제 운영 환경변수 파일로 복사합니다.

```bash
cp infra/production.env.example /home/ubuntu/bomi/secrets/production.env
chmod 600 /home/ubuntu/bomi/secrets/production.env
openssl rand -hex 32
```

마지막 명령이 출력한 값을 `POSTGRES_PASSWORD`에 입력합니다. 비밀번호를 셸
명령 기록에 직접 작성하지 말고 편집기로 파일을 수정합니다.

```bash
nano /home/ubuntu/bomi/secrets/production.env
```

운영 파일에는 최소한 다음 값이 있어야 합니다.

```dotenv
POSTGRES_DB=bomi
POSTGRES_USER=bomi
POSTGRES_PASSWORD=<랜덤 비밀번호>
POSTGRES_DATA_DIR=/home/ubuntu/bomi/data/postgres
```

## 2. 배포 전 검증

Compose 문법과 필수 환경변수를 검사합니다. 이 명령은 컨테이너를 실행하지 않습니다.

```bash
docker compose \
  --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml \
  config --quiet
```

렌더링된 설정을 확인할 때는 비밀번호가 출력될 수 있으므로 `config` 결과를 로그나
메신저에 공유하지 않습니다.

## 3. PostgreSQL 시작

```bash
docker compose \
  --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml \
  pull postgres

docker compose \
  --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml \
  up -d postgres
```

## 4. 상태 및 pgvector 확인

```bash
docker compose \
  --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml \
  ps postgres

docker inspect --format='{{.State.Health.Status}}' bomi-postgres

docker compose \
  --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml \
  exec -T postgres sh -c \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
  "SELECT extversion FROM pg_extension WHERE extname = '\''vector'\'';"'
```

정상이라면 컨테이너 상태는 `healthy`, 확장 버전은 `0.8.5`로 출력됩니다.

DB 포트가 호스트에 공개되지 않았는지도 확인합니다.

```bash
docker port bomi-postgres
sudo ss -lnt | grep ':5432' || true
```

두 명령 모두 리스닝 포트를 표시하지 않아야 합니다.

## 5. 로그와 재시작

최근 로그 확인:

```bash
docker compose \
  --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml \
  logs --tail=100 postgres
```

정상 재시작:

```bash
docker compose \
  --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml \
  restart postgres
```

## 6. 백업

백업 파일에는 개인정보가 포함될 수 있으므로 권한을 제한합니다.

```bash
umask 077
docker compose \
  --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml \
  exec -T postgres sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "/home/ubuntu/bomi/backup/bomi-$(date -u +%Y%m%dT%H%M%SZ).dump"
```

백업 파일이 생성됐는지 확인합니다.

```bash
ls -lh /home/ubuntu/bomi/backup
```

백업은 EC2 디스크에만 두지 말고 추후 별도 저장소에도 복제해야 합니다.

## 7. 복구 원칙

복구는 기존 데이터를 덮어쓸 수 있는 작업입니다. 장애 상황에서 즉시 실행하지 말고
대상 DB와 백업 파일을 재확인한 뒤 수행합니다. 평상시에는 백업 목록 검사까지만 합니다.

```bash
pg_restore --list /home/ubuntu/bomi/backup/<backup-file>.dump | head
```

실제 복구 절차는 운영 데이터가 생긴 뒤 별도의 복구 리허설을 통해 확정합니다.

## 8. 이미지 업그레이드

`pgvector` 또는 PostgreSQL 메이저 버전을 운영 중 즉시 변경하지 않습니다.

1. `pg_dump` 백업 생성
2. 변경할 이미지 태그와 호환성 확인
3. 별도 테스트 DB에서 복구 검증
4. 점검 시간 확보
5. 운영 이미지 변경 및 검증

PostgreSQL 메이저 버전 변경은 단순 컨테이너 교체가 아니라 데이터 마이그레이션 작업으로 취급합니다.

## Backend 컨테이너 운영

Backend는 PostgreSQL과 동일한 `bomi-backend-net`에 연결하며 DB 서비스 이름
`postgres`를 사용합니다. 8080 포트는 호스트에 공개하지 않습니다.

### 1. 이미지 빌드

배포할 커밋 SHA를 이미지 태그로 사용하는 것을 권장합니다.

```bash
cd /home/ubuntu/bomi/deploy/source
docker compose \
  --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml \
  build --pull backend
```

`production.env`의 `BACKEND_IMAGE_TAG`에는 배포할 커밋 SHA나 릴리스 식별자를
기록합니다. 태그 값을 바꾼 뒤 빌드해야 해당 이름으로 이미지가 생성됩니다.

### 2. Backend 시작

```bash
docker compose \
  --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml \
  up -d --wait --wait-timeout 120 backend
```

PostgreSQL이 healthy 상태가 된 이후 Backend가 시작됩니다.

### 3. 상태 및 DB 연결 확인

```bash
docker compose \
  --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml \
  ps postgres backend

docker inspect \
  --format='Status={{.State.Status}} Health={{.State.Health.Status}} RestartCount={{.RestartCount}}' \
  bomi-backend

docker logs --tail=100 bomi-backend
```

Actuator health 응답은 Backend 컨테이너 내부에서 확인합니다.

```bash
docker exec bomi-backend \
  curl --fail --silent --show-error http://localhost:8080/actuator/health
```

응답의 전체 상태가 `UP`이어야 합니다. Spring Boot Actuator의 전체 health에는
DataSource 상태가 반영됩니다.

호스트 포트가 공개되지 않았는지 확인합니다.

```bash
docker port bomi-backend
sudo ss -lntp | grep ':8080' || echo 'OK: Backend is not published on the host'
```

### 4. 리소스 및 보안 설정

- 메모리 제한: 1GB
- CPU 제한: 1.5 CPU
- 파일시스템: 읽기 전용
- 임시 파일: 64MB `/tmp` tmpfs
- 실행 사용자: 비-root `bomi`
- 추가 권한 획득: 금지
- 정상 종료 대기: 30초

### 5. 로그와 재시작

```bash
docker compose \
  --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml \
  logs --tail=100 backend

docker compose \
  --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml \
  restart backend
```

Backend만 재시작해도 PostgreSQL 컨테이너와 데이터에는 영향을 주지 않습니다.

## Mosquitto 주의사항

현재 Mosquitto 설정은 로컬 개발 편의를 위해 익명 접속을 허용합니다. 운영 환경에
배포하기 전에 사용자 인증, ACL, TLS를 적용해야 합니다.
