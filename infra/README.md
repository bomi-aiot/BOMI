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

## 4. 상태 확인 (pgvector 는 켜지 않습니다)

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

정상이라면 컨테이너 상태는 `healthy`이고, **확장 버전은 아무것도 출력되지 않습니다(빈 줄).**

`0.8.5`가 출력되면 누군가 `CREATE EXTENSION vector`를 실행한 것입니다. 의도된 상태가 아닙니다 — S15P11E102-218에서 의미 검색을 Qdrant로 옮겼고, pgvector는 4096차원을 인덱싱할 수 없습니다(상한은 `vector` 2,000 / `halfvec` 4,000). 켜져 있으면 검색 경로가 둘이 되고 그중 하나는 인덱스 없는 순차 스캔입니다. `infra/docker/postgres/init/001-enable-vector.sql`에 경위가 적혀 있습니다.

이미지가 `pgvector/pgvector`인 것은 그대로입니다. 운영 중 PostgreSQL 이미지를 바꾸는 것이 확장 하나를 끄는 것보다 위험하기 때문입니다.

### Qdrant 상태 확인

```bash
docker compose \
  --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml \
  ps qdrant

docker inspect --format='{{.State.Health.Status}}' bomi-qdrant
```

`healthy`여야 합니다. 컬렉션은 백엔드가 기동할 때 만듭니다(`memory`, `conversation_summary`, 각각 4096차원). 호스트 포트를 열지 않으므로 대시보드는 밖에서 볼 수 없습니다. 안에서 확인하려면:

```bash
docker exec bomi-qdrant bash -c \
  "exec 3<>/dev/tcp/127.0.0.1/6333 && \
   printf 'GET /collections HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n' >&3 && cat <&3"
```

이미지에 `curl`·`wget`·`nc`가 없어서 `bash`의 `/dev/tcp`를 씁니다. `/bin/sh`는 dash이므로 `sh -c`로는 동작하지 않습니다.

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

## Nginx 및 HTTPS 운영

외부 HTTP/HTTPS 요청은 Nginx만 수신합니다. `/api/` 요청은 `bomi-proxy-net`을
통해 Backend로 전달하고 `/actuator`는 외부에서 차단합니다. Backend의 8080은
계속 호스트에 공개하지 않습니다.

- 도메인: `i15e102.p.ssafy.io`
- Nginx 이미지: `nginx:1.30.4-alpine`
- Certbot 이미지: `certbot/certbot:v5.7.0`
- 인증서: `/home/ubuntu/bomi/data/certbot/conf`
- ACME webroot: `/home/ubuntu/bomi/data/certbot/www`

### 1. 사전 확인

도메인의 A 레코드와 EC2의 공인 IP가 일치해야 하며 외부에서 80과 443 포트에
접근할 수 있어야 합니다.

```bash
getent ahostsv4 i15e102.p.ssafy.io
curl -4 --max-time 10 https://checkip.amazonaws.com
sudo ss -lntp | grep -E ':(80|443) ' || true
```

UFW에 HTTP를 허용합니다. HTTPS는 기존 규칙이 있더라도 함께 확인합니다.

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw status numbered
```

### 2. 인증서 디렉터리와 환경변수

```bash
sudo install -d -o ubuntu -g ubuntu -m 700 /home/ubuntu/bomi/data/certbot/conf
sudo install -d -o ubuntu -g ubuntu -m 755 /home/ubuntu/bomi/data/certbot/www
```

`/home/ubuntu/bomi/secrets/production.env`에 다음 값을 추가합니다.

```dotenv
BOMI_DOMAIN=i15e102.p.ssafy.io
LETSENCRYPT_EMAIL=<팀에서 관리하는 실제 이메일>
CERTBOT_CONF_DIR=/home/ubuntu/bomi/data/certbot/conf
CERTBOT_WEBROOT_DIR=/home/ubuntu/bomi/data/certbot/www
```

### 3. 최초 인증서 발급

인증서가 없으면 HTTPS Nginx가 시작될 수 없습니다. 먼저 임시 HTTP Nginx를
실행하여 ACME challenge 경로를 제공합니다.

```bash
cd /home/ubuntu/bomi/deploy/source

docker compose \
  --profile tools \
  --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml \
  up -d nginx-bootstrap

curl --fail http://localhost/nginx-health
```

환경파일에서 도메인과 이메일을 읽어 인증서를 발급합니다.

```bash
BOMI_DOMAIN=$(awk -F= '$1 == "BOMI_DOMAIN" { print $2 }' /home/ubuntu/bomi/secrets/production.env)
BOMI_LETSENCRYPT_EMAIL=$(awk -F= '$1 == "LETSENCRYPT_EMAIL" { print $2 }' /home/ubuntu/bomi/secrets/production.env)

docker compose \
  --profile tools \
  --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml \
  run --rm certbot certonly \
  --webroot --webroot-path /var/www/certbot \
  --domain "$BOMI_DOMAIN" \
  --email "$BOMI_LETSENCRYPT_EMAIL" \
  --agree-tos --no-eff-email --non-interactive
```

발급에 성공하면 임시 Nginx를 제거합니다.

```bash
docker compose \
  --profile tools \
  --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml \
  rm -sf nginx-bootstrap
```

### 4. HTTPS Nginx 시작 및 검증

```bash
docker compose \
  --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml \
  up -d --wait --wait-timeout 60 nginx

curl -I http://i15e102.p.ssafy.io/api/health
curl --fail --silent --show-error https://i15e102.p.ssafy.io/api/health
curl -I https://i15e102.p.ssafy.io/actuator/health
curl -I https://i15e102.p.ssafy.io/swagger-ui.html
curl --fail --silent --show-error https://i15e102.p.ssafy.io/openapi/vision-ai.openapi.yaml > /dev/null
curl --fail --silent --show-error https://i15e102.p.ssafy.io/openapi/vision-callback.openapi.yaml > /dev/null
curl --fail --silent --show-error https://i15e102.p.ssafy.io/openapi/voice-ai.openapi.yaml > /dev/null
```

정상 기준은 HTTP 요청의 HTTPS 리다이렉트, `/api/health`의 `UP` 응답,
`/actuator/health`의 404 응답, `/swagger-ui.html`의 Backend Swagger UI 리다이렉트,
세 OpenAPI YAML의 200 응답입니다. Swagger UI는 계약 열람 전용이며 Nginx는 지정된
문서 경로에 GET·HEAD만 허용합니다.

Backend 포트가 계속 비공개인지 함께 확인합니다.

```bash
docker port bomi-backend
sudo ss -lntp | grep ':8080' || echo 'OK: Backend is not published on the host'
```

### 5. 인증서 갱신

갱신 테스트:

```bash
cd /home/ubuntu/bomi/deploy/source
docker compose \
  --profile tools \
  --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml \
  run --rm certbot renew \
  --webroot --webroot-path /var/www/certbot \
  --dry-run
```

운영 갱신 스크립트는 `scripts/deploy/renew-certificates.sh`입니다. 실행 권한을
부여하고 cron 또는 systemd timer로 하루 한 번 실행합니다. Certbot은 갱신 시점이
아니면 인증서를 변경하지 않습니다.

```bash
chmod 750 scripts/deploy/renew-certificates.sh
scripts/deploy/renew-certificates.sh
```

운영 EC2는 UTC 기준 매일 03:17(한국 시간 12:17)에 갱신 여부를 확인합니다.

```bash
(
  crontab -l 2>/dev/null | grep -v 'renew-certificates.sh'
  echo '17 3 * * * /home/ubuntu/bomi/deploy/source/scripts/deploy/renew-certificates.sh >> /home/ubuntu/bomi/logs/certbot-renew.log 2>&1'
) | crontab -

crontab -l
```

갱신 로그는 `/home/ubuntu/bomi/logs/certbot-renew.log`에서 확인합니다.

## Mosquitto 주의사항

`docker/mosquitto/config/mosquitto.conf`는 로컬 개발용 설정입니다. 운영 배포는
별도 파일인 `compose.mqtt.prod.yml`과 `docker/mosquitto/production/`을 사용하며,
익명 접속 차단, 사용자별 ACL, MQTTS(8883)를 적용합니다. 최초 EC2 설정과 Jenkins
Job 등록 절차는 `scripts/deploy/MQTT_DEPLOYMENT.md`를 따릅니다.
