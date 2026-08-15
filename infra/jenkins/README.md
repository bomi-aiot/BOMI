# Jenkins 운영 구성

Jenkins는 호스트 포트를 직접 공개하지 않고 공용 Nginx의 `/jenkins/` 경로를 통해서만
접근합니다. Jenkins 홈은 `/home/ubuntu/bomi/data/jenkins`에 영속화합니다.

## 보안 주의사항

Jenkins는 Docker socket을 통해 호스트 Docker를 제어합니다. 이 권한은 사실상 EC2의
관리자 권한과 동일하므로 Jenkins 관리자와 Pipeline 수정 권한을 최소 인원에게만
부여해야 합니다. GitLab Deploy Token, Webhook Secret, 관리자 비밀번호는 Jenkins
Credentials 또는 EC2 secrets에만 보관하고 Git에 커밋하지 않습니다.
운영 배포 스크립트가 이미지 태그를 원자적으로 갱신할 수 있도록 EC2의 `secrets`
디렉터리를 Jenkins에 마운트하므로 Pipeline 열람·수정 권한도 관리자에게만 부여합니다.

## EC2 사전 준비

```bash
sudo install -d -o 1000 -g 1000 -m 700 /home/ubuntu/bomi/data/jenkins

# 이 숫자를 아래 DOCKER_GID 에 그대로 넣습니다.
stat -c '%g' /var/run/docker.sock
```

두 번째 명령의 숫자를 `/home/ubuntu/bomi/secrets/production.env`에 설정합니다.

```dotenv
JENKINS_HOME_DIR=/home/ubuntu/bomi/data/jenkins
DOCKER_GID=<docker.sock group ID>
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
  build jenkins

docker compose \
  --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml \
  up -d --wait --wait-timeout 420 jenkins

docker exec bomi-nginx nginx -t
docker exec bomi-nginx nginx -s reload
```

> Jenkins healthcheck는 `start_period 60s` + `interval 15s` × `retries 20`이라
> 최초 기동 시 healthy 판정까지 최대 약 6분이 걸릴 수 있습니다(`infra/compose.prod.yml`).
> 타임아웃이 짧으면 실제로는 정상 기동 중인데 명령이 실패합니다.

브라우저에서 `https://i15e102.p.ssafy.io/jenkins/`에 접속합니다. 최초 잠금 해제용
비밀번호는 다음 명령으로만 확인하고 채팅이나 저장소에 복사하지 않습니다.

```bash
docker exec bomi-jenkins \
  cat /var/jenkins_home/secrets/initialAdminPassword
```

설정 마법사에서는 권장 플러그인을 설치하고 별도의 관리자 계정을 생성합니다.
Jenkins URL은 `https://i15e102.p.ssafy.io/jenkins/`로 설정합니다.
최초 잠금 해제 비밀번호가 터미널 로그나 채팅에 노출되었다면 설정을 마친 직후 새로
생성한 관리자 계정만 사용하고 안전한 비밀번호로 관리합니다.

## Pipeline 작업공간

모든 Pipeline은 `customWorkspace`로 **고정 작업공간**을 지정합니다. 이 경로를 컨테이너
안팎에서 동일하게 마운트해야 Docker Compose의 bind mount 경로가 EC2 호스트에서도 정확히
해석됩니다. 모든 Pipeline은 `disableConcurrentBuilds()`로 동시 실행을 금지합니다.

| Pipeline | 작업공간 (`/home/ubuntu/bomi/data/jenkins/workspace/` 아래) |
| --- | --- |
| `ci/Jenkinsfile.integration` — **현재 유일한 EC2 자동 배포 경로** | `bomi-integration-production` |
| `ci/Jenkinsfile.backend` | `bomi-backend-production` |
| `ci/Jenkinsfile.frontend` | `bomi-frontend-production` |
| `ci/Jenkinsfile.mqtt` | `bomi-mqtt-production` |
| `ci/Jenkinsfile.ai` (검증만) | `bomi-ai-verify` |
| `ci/Jenkinsfile.robot` (검증만) | `bomi-robot-verify` |
| 루트 `Jenkinsfile` — **레거시** | `bomi-production` |

루트 `Jenkinsfile`은 `deploy-production.sh`를 부르는 이전 세대 경로입니다. 릴리스 브랜치
검증(`verify_release_commit`)도 nginx 설정 reload도 타지 않으므로, 새로 Job을 만들 때
이것을 고르지 않습니다.

**작업공간 안에서 손으로 무언가를 만들지 않습니다.** 배포 스크립트가 시작 시
`git status --porcelain`이 비어 있는지 검사하므로(`../../scripts/deploy/deploy-common.sh`),
venv나 임시 파일을 남기면 다음 빌드가 실패합니다.

Job별 Branch Specifier와 트리거 설정은 [`../../ci/README.md`](../../ci/README.md)에 있습니다.

## 백업 대상

`JENKINS_HOME_DIR`(`/home/ubuntu/bomi/data/jenkins`)에 Job 설정과 빌드 이력이 전부
들어갑니다. PostgreSQL 백업 절차는 [`../README.md`](../README.md) §6에 있지만 Jenkins 홈의
백업 절차는 아직 어느 문서에도 없습니다.

## 상태 및 영속성 확인

```bash
docker compose \
  --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml \
  ps jenkins

curl -I https://i15e102.p.ssafy.io/jenkins/login
docker port bomi-jenkins
sudo ss -lntp | grep -E ':(8080|50000) ' \
  || echo 'OK: Jenkins ports are not published on the host'
```
