# 영역별 Jenkins Pipeline

| Pipeline | 대상 브랜치 | 동작 |
| --- | --- | --- |
| `Jenkinsfile.integration` | `hotfix/scenario-integration` | **시연 기간 한정.** MQTT Broker와 Backend를 배포 |
| `Jenkinsfile.backend` | `be-main` | Backend만 EC2에 배포 |
| `Jenkinsfile.mqtt` | `be-main` | MQTT 관련 경로가 바뀐 경우에만 Mosquitto 재배포 |
| `Jenkinsfile.frontend` | `fe-main` | Frontend만 EC2에 배포 |
| `Jenkinsfile.ai` | `ai-main` | 빌드·테스트 검증만 수행 |
| `Jenkinsfile.robot` | `robot-main` | 빌드 검증만 수행 |

각 Jenkins Job의 SCM Branch Specifier와 GitLab push trigger branch filter를 같은 main
브랜치로 지정합니다. `develop` 및 기능 브랜치는 운영 Job에서 허용하지 않습니다.

AI 프로젝트는 `robot/ai_chat/`에 있습니다. 디렉터리가 없을 때 AI Job은 보류가 아니라
**실패**로 표시합니다. AI·Robot 배포 대상 장치가 준비되기 전까지 두 Pipeline은 원격
배포를 수행하지 않습니다.

이 파일들과 `scripts/ci`, `scripts/deploy`, `infra` 운영 설정은 각 영역의 main으로
릴리스되기 전에 해당 develop 브랜치에도 반영되어야 합니다.

## 시연 스프린트 한정 — 통합 Pipeline

시연 기간에는 브랜치 전략을 접고 모든 도메인을 `hotfix/scenario-integration` 하나로
모읍니다. 이 기간의 EC2 배포는 `Jenkinsfile.integration` **하나만** 담당합니다.
담당 범위는 MQTT Broker와 Backend입니다.

Job을 하나로 합친 이유는 Jenkins의 Job 트리거가 "브랜치" 단위지 "경로" 단위가 아니기
때문입니다. `Jenkinsfile.backend`와 `Jenkinsfile.frontend`를 둘 다 같은 브랜치에 걸면
push 한 번에 두 Job이 **동시에** 뜨고, 두 Job이 같은 `production.env`를 읽고-고쳐-덮어쓰기
때문에(`deploy-common.sh`의 `set_env_value`) 서로의 이미지 태그를 유실시킬 수 있습니다.
Job이 하나면 `disableConcurrentBuilds()` 하나로 전부 직렬화되어 이 문제가 사라집니다.

젯슨(`robot/ai_chat`·`bridge`·`ros2_ws`)과 파이(`iot`)는 수동 배포이므로 이 Pipeline의
대상이 아닙니다. 해당 기계들은 이 브랜치를 직접 checkout해서 실행합니다.

### MQTT Broker를 함께 배포합니다 (2026-08-07 추가)

운영 Mosquitto의 ACL과 `mosquitto.conf`는 이미지에 굽지 않고 이 저장소의
`infra/docker/mosquitto/production/`을 그대로 바인드 마운트합니다
(`infra/compose.mqtt.prod.yml`). 그런데 그 파일들을 배포하는 `Jenkinsfile.mqtt`는
Job 트리거가 `be-main`이고 `BOMI_RELEASE_BRANCH=be-main`이 하드코딩되어 있습니다.
시연 브랜치에서 ACL을 완화한 커밋(`8a001e2b`)은 `be-main`에 없으므로, 이 스테이지가
없으면 완화된 ACL은 **어떤 자동 경로로도 브로커에 도달하지 못합니다.**

`Deploy MQTT Broker`는 `Deploy Backend` **앞**에 둡니다. mosquitto는 SIGHUP으로 ACL을
다시 읽지만 이미 승인된 구독은 그대로 남습니다. 순서를 뒤집으면 Backend가 옛 ACL로
구독을 승인받은 상태로 남고 완화는 다음 재시작까지 무효화되며, MQTT는 거부를
클라이언트에 알리지 않으므로 그 사실이 로그에도 남지 않습니다.

변경 감지는 두지 않습니다. `has-changes.sh`는 직전 성공 빌드와의 diff를 보는데, ACL
완화 커밋은 이미 이 브랜치 히스토리에 있어서 diff에 걸리지 않고 영원히 skip됩니다.
Mosquitto 배포는 멱등이고 HUP reload라 매번 돌려도 저렴합니다.

MQTT 전제조건은 `Validate`에서 끝까지 확인합니다. `Deploy MQTT`가 `Deploy Backend`
앞에 있으므로 MQTT가 깨지면 Backend 배포까지 막히기 때문에, 그 실패를 운영에 손대기
전 단계로 끌어옵니다. 확인 항목은 `deploy-mqtt.sh`·`verify-mqtt.sh` 셸 문법,
`/home/ubuntu/bomi/secrets/mqtt.env` 읽기 가능 여부, `compose.mqtt.prod.yml`의
`--profile tools` 스키마입니다. **`mqtt.env`는 `production.env`와 다른 파일입니다** —
없으면 `scripts/deploy/MQTT_DEPLOYMENT.md` 2~3절을 먼저 수행합니다.

### Frontend는 배포하지 않습니다 (2026-08-07 결정)

이 브랜치의 `frontend`는 `fe-main`과 랜딩 페이지 구현이 갈라져 있고
(`LandingPage.tsx`/`LandingPage.css` ↔ `styles.css`), `frontend/Dockerfile`이
`tsconfig.json`과 `vite.config.ts`를 COPY하지 않아 `tsc --noEmit && vite build`가
성립하지 않습니다. `vite.config.ts`가 `@vitejs/plugin-react`를 등록하므로 JSX 변환이
죽습니다.

시연 화면은 이미 `fe-main` 이미지로 떠 있고 시연까지 프론트 변경 계획이 없으므로,
통합 Pipeline은 Backend만 배포합니다. 프론트를 다시 배포해야 하면 그때
`Jenkinsfile.frontend`와 `fe-main` Job을 사용합니다.

### Build와 Deploy를 분리한 이유 (2026-08-07 사고 기록)

`scripts/deploy/deploy-backend.sh`의 실행 순서는 다음과 같습니다.

```
set_env_value BACKEND_IMAGE_TAG  →  compose up -d postgres  →  compose build backend
```

이미지 빌드가 **마지막**입니다. 컴파일이 깨지면 이미 `production.env`가 존재하지 않는
태그로 덮여 있고 운영 PostgreSQL은 재기동된 뒤입니다. 실제로 이 순서 때문에
`hotfix`의 `backend/build.gradle`이 구버전이라는 사실을 배포 시도로 처음 발견했고,
그 과정에서 운영 DB 커넥션이 끊겨 백엔드가 `PSQLException`을 뱉었습니다.

배포 스크립트는 be 라인의 자산이므로 건드리지 않고, Pipeline에 선행 게이트를 둡니다.
`Build Backend` 스테이지는 새 SHA 태그로 이미지를 빌드만 하고 `production.env`와
실행 중인 컨테이너를 일절 건드리지 않습니다. Compose의 변수 우선순위가
셸 환경 > `--env-file`이므로 `BACKEND_IMAGE_TAG`를 셸로 넘기면 파일을 읽기만 합니다.
여기서 깨지면 운영은 무손상이고, 통과하면 Deploy 단계의 `compose build`는 캐시
적중이라 즉시 끝납니다.

### Jenkins Job 설정

- Script Path: `ci/Jenkinsfile.integration`
- Branch Specifier: `*/hotfix/scenario-integration`
- Refspec: **기본값 유지** (`+refs/heads/*:refs/remotes/origin/*`)
  `deploy-common.sh`의 `verify_release_commit`가
  `refs/remotes/origin/hotfix/scenario-integration`을 읽으므로, refspec이 특정 브랜치로
  좁혀져 있으면 그 ref가 만들어지지 않아 실패합니다.
- GitLab push trigger branch filter: `hotfix/scenario-integration`

`Jenkinsfile.integration`의 `BOMI_RELEASE_BRANCH`와 Job의 Branch Specifier가 서로 다르면
`HEAD is not the latest origin/<branch> commit`으로 배포가 중단됩니다. 둘은 항상 같이 바꿉니다.

### 시연 후 원복

`Jenkinsfile.integration`과 해당 Job을 제거하고, `Jenkinsfile.backend`·`Jenkinsfile.frontend`
Job의 Branch Specifier를 `be-main`·`fe-main`으로 되돌립니다. 그 두 파일은 시연 스프린트
동안 수정하지 않았으므로 그대로 사용할 수 있습니다.

MQTT는 `Jenkinsfile.mqtt`와 `be-main` Job으로 돌아갑니다. 그때 `infra/docker/mosquitto/
production/acl`을 파일 하단의 "복구용 원본" 기준으로 최소 권한으로 되돌리는데, 원본에
빠져 있던 `bomi-jetson`의 `robot/+/results` read와 `iot/+/events` read를 **반드시**
포함해야 합니다. 되돌리기 전에 `on_subscribe` granted QoS 확인 로직을 넣는 편이
낫습니다 — 그래야 다음 누락이 관측 가능해집니다.
