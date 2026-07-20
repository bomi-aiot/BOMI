# 운영 배포 스크립트

`deploy-production.sh`는 EC2에 checkout된 Git 커밋을 Backend와 Frontend 운영
컨테이너로 배포합니다. Jenkins에서도 동일한 스크립트를 호출할 수 있습니다.

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

스크립트는 필수 파일 검사, Git SHA 이미지 태그 기록, Compose 검증, 이미지 빌드,
컨테이너 기동, health 및 HTTPS 검증을 순서대로 수행합니다. 성공 시 종료 코드는 0이고
마지막에 `Deployment completed successfully`가 출력됩니다. 실패하면 0이 아닌 코드와
실패한 줄을 출력합니다.

## 배포 결과 확인

```bash
docker compose \
  --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml \
  ps postgres backend frontend nginx

curl --fail https://i15e102.p.ssafy.io/ > /dev/null
curl --fail https://i15e102.p.ssafy.io/api/health
```

## 경로 재정의

기본 EC2 경로가 아닌 환경에서 검사할 때만 다음 환경변수를 사용할 수 있습니다.

```bash
BOMI_SOURCE_DIR=/path/to/source \
BOMI_ENV_FILE=/path/to/production.env \
scripts/deploy/deploy-production.sh
```
