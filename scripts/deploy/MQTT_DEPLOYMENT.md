# MQTT Broker 운영 배포

운영 Mosquitto는 Backend·Frontend와 다른 Compose 프로젝트(`bomi-mqtt`)로
실행합니다. `be-main`에 변경이 들어오면 Backend와 MQTT Jenkins Job이 각각 담당
경로를 확인하므로, Broker 설정만 바뀐 경우 Backend는 다시 배포되지 않습니다.

## 1. EC2 저장소 동기화

다음 작업은 MQTT 변경이 `be-main`에 병합된 뒤 한 번 수행합니다. 이 경로의 저장소는
인증서 갱신 cron에서도 사용하므로 최신 운영 스크립트가 있어야 합니다.

```bash
cd /home/ubuntu/bomi/deploy/source
git fetch origin
git switch be-main
git pull --ff-only origin be-main
```

## 2. 디렉터리와 환경 파일 생성

```bash
install -d -m 700 /home/ubuntu/bomi/secrets/mosquitto
install -d -m 750 /home/ubuntu/bomi/secrets/mosquitto/certs
install -d -m 755 /home/ubuntu/bomi/data/mosquitto/data
install -d -m 755 /home/ubuntu/bomi/data/mosquitto/log
install -d -m 755 /home/ubuntu/bomi/logs

test -e /home/ubuntu/bomi/secrets/mqtt.env || \
  install -m 600 infra/mqtt.env.example /home/ubuntu/bomi/secrets/mqtt.env

openssl rand -hex 32
nano /home/ubuntu/bomi/secrets/mqtt.env
```

마지막 명령이 출력한 임의 문자열을 `MQTT_HEALTH_PASSWORD`에 기록합니다.
`BOMI_DOMAIN`과 각 경로도 실제 EC2 값과 일치하는지 확인합니다. 실제 비밀번호와
`mqtt.env`는 Git에 커밋하지 않습니다.

## 3. MQTT 사용자 비밀번호 파일 생성

아래 함수는 비밀번호를 명령행에 직접 쓰지 않고 대화형으로 입력받습니다. 네 계정은
서로 다른 긴 비밀번호를 사용합니다. `bomi-healthcheck`에는 앞 단계에서
`MQTT_HEALTH_PASSWORD`에 기록한 것과 같은 값을 입력합니다.

```bash
MQTT_SECRET_DIR=/home/ubuntu/bomi/secrets/mosquitto

mqtt_passwd() {
  docker run --rm -it \
    --user "$(id -u):$(id -g)" \
    -v "$MQTT_SECRET_DIR:/work" \
    eclipse-mosquitto:2.0.22-openssl \
    mosquitto_passwd "$@"
}

mqtt_passwd -c /work/passwords bomi-healthcheck
mqtt_passwd /work/passwords bomi-backend
mqtt_passwd /work/passwords bomi-iot-gateway
mqtt_passwd /work/passwords bomi-jetson
unset -f mqtt_passwd

sudo chown 1883:1883 "$MQTT_SECRET_DIR/passwords"
sudo chmod 600 "$MQTT_SECRET_DIR/passwords"
```

사용자별 권한은 `infra/docker/mosquitto/production/acl`에서 제한합니다. 서비스 계정
비밀번호는 각 장치 또는 Backend의 별도 비밀 저장소에 전달하고 소스 코드에는 넣지
않습니다.

## 4. EC2 네트워크 설정

AWS EC2 보안 그룹 인바운드 규칙에 `TCP 8883`을 추가합니다. 가능하면 Raspberry Pi와
Jetson이 사용하는 공인 IP 또는 VPN 대역만 소스로 허용합니다. MQTT 평문 포트
`1883`은 호스트에 공개하지 않으므로 보안 그룹에 추가하지 않습니다.

Compose 문법과 필수 환경값을 먼저 확인합니다.

```bash
cd /home/ubuntu/bomi/deploy/source
docker compose \
  --env-file /home/ubuntu/bomi/secrets/mqtt.env \
  -f infra/compose.mqtt.prod.yml \
  --profile tools config --quiet
```

## 5. Jenkins Job 생성

Jenkins에서 `bomi-mqtt-production` Pipeline Job을 새로 만들고 다음처럼 설정합니다.

- Definition: `Pipeline script from SCM`
- SCM 및 Credentials: 기존 Backend Job과 동일
- Branch Specifier: `*/be-main`
- Script Path: `ci/Jenkinsfile.mqtt`
- GitLab push trigger branch filter: `be-main`

첫 빌드는 이전 성공 커밋이 없으므로 MQTT를 자동 배포합니다. 이후에는 MQTT 운영
경로가 바뀐 빌드만 실제 배포하며, 필요할 때 `Build with Parameters`에서
`FORCE_DEPLOY=true`로 수동 재배포할 수 있습니다.

| `be-main` 변경 | Backend Job | MQTT Job |
| --- | --- | --- |
| `backend/**` | 배포 | 생략 |
| MQTT Compose·설정·배포 스크립트 | 생략 | 배포 |
| 두 영역 모두 | 배포 | 배포 |

## 6. 첫 배포 확인

Jenkins MQTT Job이 성공한 뒤 EC2에서 확인합니다.

```bash
docker ps --filter name=bomi-mosquitto \
  --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

docker inspect --format '{{.State.Health.Status}}' bomi-mosquitto
sudo ss -lntp | grep ':8883'
sudo ss -lntp | grep ':1883' || echo 'OK: port 1883 is not public'

openssl s_client \
  -connect i15e102.p.ssafy.io:8883 \
  -servername i15e102.p.ssafy.io </dev/null 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates

cd /home/ubuntu/bomi/deploy/source
BOMI_SOURCE_DIR="$PWD" scripts/deploy/verify-mqtt.sh
```

정상 기준은 컨테이너 상태 `healthy`, 호스트의 8883 리스닝, 호스트 1883 미공개,
유효한 인증서 출력, 마지막 smoke test 성공입니다. Smoke test는 익명 연결이
거부되고 인증된 MQTTS 발행·구독이 실제로 오가는지 확인합니다.

## 7. 인증서 갱신

기존 `renew-certificates.sh`와 cron을 그대로 사용합니다. 스크립트는 Certbot 갱신 후
Nginx를 reload하고, Mosquitto가 실행 중이면 새 인증서를 전용 디렉터리로 복사한 뒤
HUP 신호로 중단 없이 다시 읽게 합니다.

```bash
cd /home/ubuntu/bomi/deploy/source
scripts/deploy/renew-certificates.sh
```
