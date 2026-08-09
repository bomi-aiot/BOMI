# BOMI 운영자 콘솔

기존 Jetson 웨이포인트 편집기와 분리된 EC2 운영 도구다. 인증된 Backend 운영 API를
이용해 Robot 상태를 확인하고, 멈춘 내비게이션 Scenario를 취소한 뒤 실제 정지를
확인하여 Robot mode를 `IDLE`로 복구한다.

## 운영 배포

`operator-console`은 `infra/compose.prod.yml`에 포함되며
`hotfix/scenario-integration` 배포 시 Backend와 함께 이미지가 빌드되고 재시작된다.
EC2 재부팅 뒤에도 `restart: unless-stopped` 정책으로 자동 시작된다.

최초 자동 배포 전에 기존에 터미널이나 tmux에서 수동 실행한 Streamlit을 종료한다.
수동 프로세스가 `127.0.0.1:8501`을 계속 사용하면 컨테이너가 포트를 바인딩하지
못해 배포가 실패한다.

```bash
docker ps --filter name=bomi-operator-console
docker inspect bomi-operator-console \
  --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}'
```

서비스는 EC2의 `127.0.0.1:8501`과 HTTPS의 `/operator-console/` 경로에서 접근한다.
공개 HTTPS 경로는 Nginx Basic 인증으로 보호하며, Backend 운영 API용
`OPERATOR_SHARED_SECRET`과 다른 자격 증명을 사용한다.

최초 배포 전에 EC2에서 인증 파일을 생성한다. 비밀번호와 생성된 해시는 저장소에
커밋하지 않는다.

```bash
docker run --rm httpd:2.4-alpine \
  htpasswd -Bbn <운영자 아이디> '<강한 비밀번호>' \
  > /home/ubuntu/bomi/secrets/operator-console.htpasswd
chmod 600 /home/ubuntu/bomi/secrets/operator-console.htpasswd
```

`/home/ubuntu/bomi/secrets/production.env`에는 다음 경로를 설정한다.

```dotenv
NGINX_OPERATOR_CONSOLE_HTPASSWD_FILE=/home/ubuntu/bomi/secrets/operator-console.htpasswd
```

배포 후 `https://i15e102.p.ssafy.io/operator-console/`을 열고 위에서 지정한
자격 증명으로 로그인한다.

SSH 터널 접근도 유지된다. Streamlit의 기준 경로가 `/operator-console/`이므로
터널을 연 뒤 `http://localhost:8501/operator-console/`을 사용한다.

```bash
ssh -N -L 8501:127.0.0.1:8501 <EC2 SSH Host 별칭>
```

EC2 보안 그룹에 8501 포트를 공개하지 않는다.

## 로컬 수동 실행

개발 중에는 Backend 컨테이너의 운영 Secret을 현재 셸로 읽고 콘솔을 실행한다. Secret
값 자체를 화면이나 로그에 출력하지 않는다.

```bash
cd /home/ubuntu/bomi/data/jenkins/workspace/bomi-integration-production/backend/tools/operator_console
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export BOMI_BACKEND_URL='http://localhost:8080'
export OPERATOR_SHARED_SECRET="$(docker exec bomi-backend printenv OPERATOR_SHARED_SECRET)"
test -n "$OPERATOR_SHARED_SECRET"

streamlit run app.py
```

## 안전 절차

1. 화면에서 Robot mode와 활성 Scenario를 확인한다.
2. 로봇 주변의 물리적 안전을 확인하고 `진행 중 내비게이션 취소`를 누른다.
3. Scenario가 `CANCELLED`, Robot mode가 `SAFE_STOP`으로 바뀌는지 확인한다.
4. Jetson/Nav2에서 Robot이 실제로 정지했는지 확인한다.
5. 별도의 안전 확인 후 `IDLE로 복구`를 누른다.

두 버튼을 한 번에 실행하지 않는다. MQTT `CANCEL` 발행과 실제 모터 정지 사이에는
시간 차이가 있을 수 있다.

## 테스트

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -v
```
