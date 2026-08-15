# Frontend 운영 절차 (수동)

Frontend는 Vite 정적 파일을 빌드한 뒤 전용 Nginx 컨테이너에서 제공합니다.
Frontend 컨테이너의 8080 포트는 호스트에 공개하지 않으며, 공용 Nginx만
`bomi-proxy-net`을 통해 접근합니다.

> **평상시에는 이 절차를 직접 쓰지 않습니다.** Frontend 배포는
> `scripts/deploy/deploy-frontend.sh`가 담당하고, Jenkins가 그것을 부릅니다 —
> `ci/Jenkinsfile.frontend`(`fe-main`) 또는 `ci/Jenkinsfile.integration`(`main`).
> 이 문서는 **파이프라인이 막혔을 때 손으로 되짚는 절차**입니다.

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

> nginx는 `depends_on: service_healthy`로 **backend·operator-console·waypoint-editor·
> db-viewer·frontend 다섯 개 모두**를 요구합니다(`compose.prod.yml`). 위 명령은 그 다섯
> 개를 함께 끌어올리며, 도구 컨테이너 하나라도 불건강하면 60초 뒤 실패합니다. 그때는
> `docker compose ps`로 어느 것이 걸렸는지 먼저 확인합니다 — Frontend 문제가 아닐 수
> 있습니다.

## 배포 검증

```bash
docker compose \
  --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml \
  ps postgres qdrant backend operator-console db-viewer waypoint-editor frontend nginx

curl --fail --silent --show-error https://i15e102.p.ssafy.io/ > /dev/null
curl --fail --silent --show-error https://i15e102.p.ssafy.io/api/health
curl -I https://i15e102.p.ssafy.io/frontend-health

docker port bomi-frontend
sudo ss -lntp | grep -E ':(5173|8080) ' \
  || echo 'OK: Frontend and Backend ports are not published on the host'
```

정상 기준은 위 여덟 개 컨테이너가 모두 healthy이고, 웹 루트와 `/api/health`가 HTTPS로
응답하며, 호스트의 5173·8080 포트가 열리지 않은 상태입니다.

헬스 경로는 두 겹입니다. `/frontend-health`는 Frontend 컨테이너 자체의 것이고,
`/nginx-health`는 공용 Nginx의 것입니다. 위 명령은 전자만 확인합니다.

## 재배포

새 커밋을 checkout한 뒤 `FRONTEND_IMAGE_TAG`를 새 커밋 SHA로 바꾸고 위의 빌드 및
시작 명령을 반복합니다. 이전 이미지 태그를 유지하고 있으면 코드가 변경되어도 동일
태그를 덮어쓰게 되므로 배포마다 커밋 SHA를 사용하는 것을 권장합니다.

빌드 인자를 주지 않으면 `frontend/Dockerfile`의 기본값 `VITE_USE_MOCK_API=false`,
`VITE_GUARDIAN_API_AUTH_READY=true`(실서버 연동)로 굳습니다. 예시 데이터 화면으로
되돌려야 할 때만 두 인자를 **함께** 뒤집습니다 — 하나만 바꾸면 화면 전체가 빕니다.

```bash
docker compose \
  --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml \
  build --build-arg VITE_USE_MOCK_API=true \
        --build-arg VITE_GUARDIAN_API_AUTH_READY=false frontend
```

`deploy-frontend.sh`는 nginx reload를 **의도적으로 하지 않습니다.** 공용 nginx는 프론트
워크스페이스를 마운트하지 않으므로 리로드할 이유가 없습니다. 수동 절차에서도 습관적으로
`nginx -s reload`를 넣지 않습니다.
