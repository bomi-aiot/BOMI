# 영역별 Jenkins Pipeline

| Pipeline | 대상 브랜치 | 동작 |
| --- | --- | --- |
| `Jenkinsfile.backend` | `be-main` | Backend만 EC2에 배포 |
| `Jenkinsfile.mqtt` | `be-main` | MQTT Broker만 EC2에 배포 |
| `Jenkinsfile.frontend` | `fe-main` | Frontend만 EC2에 배포 |
| `Jenkinsfile.ai` | `ai-main` | 빌드·테스트 검증만 수행 |
| `Jenkinsfile.robot` | `robot-main` | 빌드 검증만 수행 |

각 Jenkins Job의 SCM Branch Specifier와 GitLab push trigger branch filter를 같은 main
브랜치로 지정합니다. `develop` 및 기능 브랜치는 운영 Job에서 허용하지 않습니다.

Backend와 MQTT Job은 같은 `be-main` push를 받아도 담당 경로를 따로 검사합니다.
`backend/` 변경은 Backend만 배포하고, `infra/compose.mqtt.prod.yml` 및 Mosquitto
운영 설정 변경은 MQTT Broker만 배포합니다. Jenkins의 `FORCE_DEPLOY` 매개변수는
변경 경로와 관계없이 해당 대상을 수동으로 다시 배포할 때만 사용합니다.

AI 프로젝트는 향후 `ai/`에 생성합니다. 디렉터리가 없을 때 AI Job은 실행 사실을
기록하되 결과를 `UNSTABLE`로 표시합니다. AI·Robot 배포 대상 장치가 준비되기 전까지
두 Pipeline은 원격 배포를 수행하지 않습니다.

이 파일들과 `scripts/ci`, `scripts/deploy`, `infra` 운영 설정은 각 영역의 main으로
릴리스되기 전에 해당 develop 브랜치에도 반영되어야 합니다.
