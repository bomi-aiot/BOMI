# Frontend 운영 절차

Frontend는 Vite 정적 파일을 빌드한 뒤 전용 Nginx 컨테이너에서 제공합니다.
Frontend 컨테이너의 8080 포트는 호스트에 공개하지 않으며, 공용 Nginx만
`bomi-proxy-net`을 통해 접근합니다.

## 환경 변수

`/home/ubuntu/bomi/secrets/production.env`에 배포할 Git 커밋 SHA를 이미지 태그로
기록합니다.

```dotenv
FRONTEND_IMAGE_TAG=<Git commit SHA>
```

## 이미지 빌드 및 시작

```bash
cd /home/ubuntu/bomi/deploy/source

docker compose \
  --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml \
  config --quiet

docker compose \
  --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml \
  build frontend

docker compose \
  --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml \
  up -d --wait --wait-timeout 60 frontend nginx
```

## 배포 검증

```bash
docker compose \
  --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml \
  ps frontend nginx backend postgres

curl --fail --silent --show-error https://i15e102.p.ssafy.io/ > /dev/null
curl --fail --silent --show-error https://i15e102.p.ssafy.io/api/health
curl -I https://i15e102.p.ssafy.io/frontend-health

docker port bomi-frontend
sudo ss -lntp | grep -E ':(5173|8080) ' \
  || echo 'OK: Frontend and Backend ports are not published on the host'
```

정상 기준은 `frontend`, `nginx`, `backend`, `postgres`가 모두 healthy이고, 웹 루트와
`/api/health`가 HTTPS로 응답하며, 호스트의 5173·8080 포트가 열리지 않은 상태입니다.

## 재배포

새 커밋을 checkout한 뒤 `FRONTEND_IMAGE_TAG`를 새 커밋 SHA로 바꾸고 위의 빌드 및
시작 명령을 반복합니다. 이전 이미지 태그를 유지하고 있으면 코드가 변경되어도 동일
태그를 덮어쓰게 되므로 배포마다 커밋 SHA를 사용하는 것을 권장합니다.
