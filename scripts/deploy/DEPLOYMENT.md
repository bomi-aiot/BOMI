# 운영 배포 스크립트 — `deploy-production.sh` (레거시 단일 경로)

`deploy-production.sh`는 EC2에 checkout된 Git 커밋을 Backend·Frontend·운영 도구 3종
컨테이너로 한 번에 배포합니다. 루트 `Jenkinsfile`이 이것을 부릅니다.

> **현행 자동 배포는 이 경로가 아닙니다.** `main` push는
> `ci/Jenkinsfile.integration`이 받아 `deploy-mqtt.sh` → `deploy-backend.sh` →
> `deploy-frontend.sh`를 순서대로 실행합니다. 이 문서의 스크립트에는
> **릴리스 브랜치 가드(`verify_release_commit`), 경로 절대경로 검증, nginx 설정
> reload가 없습니다.** 파이프라인이 막혀 손으로 한 번에 배포해야 할 때만 씁니다.
> 자동 경로는 [`../../ci/README.md`](../../ci/README.md)를 봅니다.

## 사전 조건

- 실행 위치의 Git 작업 트리가 깨끗해야 합니다.
- `/home/ubuntu/bomi/secrets/production.env`가 존재하고 권한이 600이어야 합니다.
- Docker Engine과 Docker Compose가 실행 중이어야 합니다.
- 인증서가 발급되어 있고 `BOMI_DOMAIN`이 환경 파일에 설정되어 있어야 합니다.

스크립트는 실제 비밀번호를 출력하지 않습니다. PostgreSQL 컨테이너와 데이터 볼륨을
삭제하거나 초기화하지 않습니다.

## 실행

```bash
cd /home/ubuntu/bomi/deploy/source
chmod 750 scripts/deploy/deploy-production.sh
scripts/deploy/deploy-production.sh
```

스크립트는 아래 순서로 수행합니다.

1. 필수 명령·파일 검사 (`git`/`docker`/`curl`, `production.env`, compose 파일)
2. **작업 트리가 깨끗한지 확인** — 더러우면 여기서 중단합니다
3. Git SHA(12자)를 5개 이미지 태그에 기록 (`BACKEND_/OPERATOR_CONSOLE_/WAYPOINT_EDITOR_/DB_VIEWER_/FRONTEND_IMAGE_TAG`)
4. `compose config --quiet` 검증
5. PostgreSQL 기동 대기(60초)
6. 이미지 5개 빌드
7. 앱 컨테이너 5개 기동(120초) → nginx `--force-recreate`(60초)
8. 컨테이너 7개 health 확인
9. HTTPS 검증 — `/`·`/api/health` 200, 운영 도구 3종 401

성공 시 종료 코드는 0이고 마지막에 `Deployment completed successfully`가 출력됩니다.
실패하면 0이 아닌 코드와 실패한 줄 번호를 출력합니다.

> **3번이 6번보다 먼저**입니다. 빌드가 깨지면 `production.env`가 존재하지 않는 이미지
> 태그를 가리킨 채 남습니다. 그때는 `production.env`의 태그를 직전 성공 SHA로 손으로
> 되돌린 뒤 `compose up -d`로 다시 올립니다. 이것이 현재의 롤백 절차입니다.
> (이 순서 문제 때문에 `ci/Jenkinsfile.integration`은 Build를 별도 선행 스테이지로
> 분리했습니다.)

7번의 nginx는 `--force-recreate`이므로 짧은 502가 생길 수 있습니다. `deploy-backend.sh`는
대신 무중단 reload를 씁니다.

## 배포 결과 확인

```bash
docker compose \
  --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml \
  ps postgres backend operator-console waypoint-editor db-viewer frontend nginx

curl --fail https://i15e102.p.ssafy.io/ > /dev/null
curl --fail https://i15e102.p.ssafy.io/api/health

# 운영 도구 3종은 인증 없이 접근하면 401이어야 합니다 (스크립트도 같은 것을 검사합니다).
for path in operator-console waypoint-editor db-viewer; do
  printf '%s -> ' "$path"
  curl --silent --output /dev/null --write-out '%{http_code}\n' \
    "https://i15e102.p.ssafy.io/$path/"
done
```

## 경로 재정의

기본 EC2 경로가 아닌 환경에서 검사할 때만 다음 환경변수를 사용할 수 있습니다.

```bash
BOMI_SOURCE_DIR=/path/to/source \
BOMI_ENV_FILE=/path/to/production.env \
scripts/deploy/deploy-production.sh
```
