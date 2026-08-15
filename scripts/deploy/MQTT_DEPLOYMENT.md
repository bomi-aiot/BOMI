# MQTT Broker 운영 배포

운영 Mosquitto는 Backend·Frontend와 다른 Compose 프로젝트(`bomi-mqtt`)로 실행하며,
환경 파일도 `mqtt.env`로 별개입니다.

배포 경로는 두 가지입니다.

| 경로 | 브랜치 | 변경 감지 |
| --- | --- | --- |
| `ci/Jenkinsfile.integration` — **시연 통합 기간의 실제 경로** | `main` | **없음(항상 배포)**. Mosquitto 배포는 멱등이고 HUP reload라 매번 돌려도 저렴하기 때문입니다 |
| `ci/Jenkinsfile.mqtt` — 라인별 전략 복귀 후의 경로 | `be-main` | `has-changes.sh`로 MQTT 관련 경로만 감지 |

이 문서의 1~4절(최초 구축)은 두 경로에 공통이고, 5절(Jenkins Job)은 후자 기준입니다.

`bomi-mqtt-net` 네트워크는 이 Compose 프로젝트가 만들고 `infra/compose.prod.yml`이
`external: true`로 붙습니다. MQTT를 내리면 Backend 쪽 compose가 네트워크를 찾지 못합니다.

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

마지막 명령이 출력한 임의 문자열을 `MQTT_HEALTH_PASSWORD`에 기록합니다. 실제 비밀번호와
`mqtt.env`는 Git에 커밋하지 않습니다.

`compose.mqtt.prod.yml`은 아래 8개를 `:?`로 요구합니다 — 하나라도 비면 렌더링 단계에서
실패합니다.

| 변수 | 값 |
| --- | --- |
| `MQTT_HEALTH_USERNAME` / `MQTT_HEALTH_PASSWORD` | 헬스체크 계정 (`bomi-healthcheck`) |
| `MQTT_PASSWORD_FILE` | `/home/ubuntu/bomi/secrets/mosquitto/passwords` |
| `MQTT_DATA_DIR` / `MQTT_LOG_DIR` | `/home/ubuntu/bomi/data/mosquitto/{data,log}` |
| `MQTT_CERT_DIR` | `/home/ubuntu/bomi/secrets/mosquitto/certs` |
| `BOMI_DOMAIN` | `i15e102.p.ssafy.io` |
| `CERTBOT_CONF_DIR` | `/home/ubuntu/bomi/data/certbot/conf` (`production.env`와 같은 값) |

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

> **현재 ACL은 시연을 위해 완화되어 있습니다** — 네 계정 모두 `bomi/v1/#`에 readwrite
> 권한을 가집니다. 최소 권한 원본은 같은 파일 하단에 주석으로 보존되어 있고, 되돌릴
> 때는 원본에서 빠져 있던 `bomi-jetson`의 `robot/+/results`·`iot/+/events` read를
> 반드시 포함해야 합니다. MQTT는 구독 거부를 클라이언트에 알리지 않으므로, 되돌리기
> 전에 `on_subscribe`의 granted QoS 확인 로직을 넣어 두는 편이 안전합니다.

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

> 이 절은 라인별 브랜치 전략 기준입니다. **시연 통합 기간에 실제로 도는 것은
> `ci/Jenkinsfile.integration`(`main`)이며, 그쪽은 변경 감지 없이 매번 MQTT를 배포합니다.**
> 아래 Job 설정 자체는 그대로 유효하고, 전략 복귀 후에 다시 주 경로가 됩니다.

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
유효한 인증서 출력, 마지막 smoke test 성공입니다. Smoke test는 익명 연결이 거부되는지,
그리고 TLS 8883으로 인증 구독·발행이 실제로 오가는지를 순서대로 확인합니다
(`infra/compose.mqtt.prod.yml`의 `--profile tools` 서비스).

## 7. 인증서 갱신 — **Mosquitto는 자동으로 반영되지 않습니다**

`renew-certificates.sh`와 cron은 그대로 사용합니다. 다만 그 스크립트가 하는 일은
`certbot renew`와 **Nginx reload 두 가지뿐**입니다. Mosquitto의 인증서
(`/mosquitto/certs/`)는 건드리지 않습니다.

```bash
cd /home/ubuntu/bomi/deploy/source
scripts/deploy/renew-certificates.sh
```

새 인증서를 브로커에 반영하는 것은 `mosquitto-cert-sync` 서비스이고, 그것을 부르는
것은 `deploy-mqtt.sh`뿐입니다. 따라서 **인증서가 갱신된 뒤 MQTT 배포가 한 번도 돌지
않으면, 브로커는 만료된 인증서를 계속 쓰다가 조용히 TLS 접속을 거부하게 됩니다.**

갱신 후에는 다음 중 하나를 수행합니다.

```bash
# (a) MQTT 배포를 한 번 돌린다 — 인증서 동기화 + HUP reload 포함
BOMI_SOURCE_DIR="$PWD" BOMI_RELEASE_BRANCH=main \
  BOMI_MQTT_ENV_FILE=/home/ubuntu/bomi/secrets/mqtt.env \
  scripts/deploy/deploy-mqtt.sh

# (b) 만료일만 확인한다
openssl s_client -connect i15e102.p.ssafy.io:8883 \
  -servername i15e102.p.ssafy.io </dev/null 2>/dev/null \
  | openssl x509 -noout -dates
```

> 이 갭을 없애려면 `renew-certificates.sh`에 cert-sync 호출과 브로커 HUP을 추가하는
> 편이 낫습니다. 지금은 **운영 절차로 메우고 있다**는 것을 알고 씁니다.

`deploy-mqtt.sh`는 HUP 뒤에 `sleep 1`만 둡니다. HUP 재적재 실패는 mosquitto가 죽지 않기
때문에 컨테이너 health로 잡히지 않습니다 — 설정 오타는 로그로만 확인됩니다.
