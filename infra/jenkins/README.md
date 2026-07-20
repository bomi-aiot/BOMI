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
  up -d --wait --wait-timeout 180 jenkins

docker exec bomi-nginx nginx -t
docker exec bomi-nginx nginx -s reload
```

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

`Jenkinsfile`은 `/home/ubuntu/bomi/data/jenkins/workspace/bomi-production`을 고정
작업공간으로 사용합니다. 이 경로를 컨테이너 안팎에서 동일하게 마운트하여 Docker
Compose의 bind mount 경로가 EC2 호스트에서도 정확히 해석되도록 합니다. Pipeline은
동시 실행을 금지하고 Compose 검증, 이미지 빌드, 기존 운영 배포 스크립트를 차례로
실행합니다.

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
