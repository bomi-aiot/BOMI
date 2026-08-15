# 배포 스크립트

Jenkins Pipeline(`../../ci/`)이 부르는 EC2 배포 스크립트들입니다. 손으로 실행할 수도
있지만, 평상시에는 Pipeline이 부릅니다.

| 스크립트 | 하는 일 | 부르는 곳 |
| --- | --- | --- |
| `deploy-common.sh` | 공용 함수 라이브러리(브랜치 가드·경로 검증·env 원자적 갱신·health 확인·nginx reload). **source 전용** | `deploy-backend.sh`, `deploy-frontend.sh` |
| `deploy-backend.sh` | Backend + 운영 도구 3종 배포 → 컨테이너 6개 health → nginx reload → HTTPS 검증 4종 | `ci/Jenkinsfile.backend`, `ci/Jenkinsfile.integration` |
| `deploy-frontend.sh` | Frontend만 배포 (nginx reload는 **의도적으로 하지 않습니다**) | `ci/Jenkinsfile.frontend`, `ci/Jenkinsfile.integration` |
| `deploy-mqtt.sh` | Mosquitto 배포 — 인증서 동기화 → 기동 → SIGHUP reload → 스모크 테스트 | `ci/Jenkinsfile.mqtt`, `ci/Jenkinsfile.integration` |
| `verify-mqtt.sh` | 브로커 health 확인 후 스모크 테스트만 실행 | `deploy-mqtt.sh`, 수동 확인 |
| `renew-certificates.sh` | Certbot 갱신 + Nginx reload (cron 일 1회) | cron |
| `deploy-production.sh` | **레거시.** Backend·Frontend·운영 도구를 한 번에 배포 | 루트 `Jenkinsfile` |

> `deploy-production.sh`와 `deploy-mqtt.sh`는 `deploy-common.sh`를 source하지 않고 같은
> 함수를 자체 정의합니다. 그래서 `deploy-production.sh` 경로에는 릴리스 브랜치 가드도
> 절대경로 검증도 nginx reload도 없습니다. 공용 함수를 고칠 때 이 두 파일을 함께
> 확인합니다.

자세한 절차: [`DEPLOYMENT.md`](DEPLOYMENT.md)(레거시 단일 배포),
[`MQTT_DEPLOYMENT.md`](MQTT_DEPLOYMENT.md)(브로커), [`../../ci/README.md`](../../ci/README.md)(자동 배포).

비밀값은 스크립트에 작성하지 않고 EC2의 `/home/ubuntu/bomi/secrets/production.env`와
`/home/ubuntu/bomi/secrets/mqtt.env`에서만 관리합니다 — **두 파일은 별개입니다.**
