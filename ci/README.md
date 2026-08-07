# 영역별 Jenkins Pipeline

| Pipeline | 대상 브랜치 | 동작 |
| --- | --- | --- |
| `Jenkinsfile.integration` | `hotfix/scenario-integration` | **시연 기간 한정.** Backend → Frontend 순차 배포 |
| `Jenkinsfile.backend` | `be-main` | Backend만 EC2에 배포 |
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

Job을 하나로 합친 이유는 Jenkins의 Job 트리거가 "브랜치" 단위지 "경로" 단위가 아니기
때문입니다. `Jenkinsfile.backend`와 `Jenkinsfile.frontend`를 둘 다 같은 브랜치에 걸면
push 한 번에 두 Job이 **동시에** 뜨고, 두 Job이 같은 `production.env`를 읽고-고쳐-덮어쓰기
때문에(`deploy-common.sh`의 `set_env_value`) 서로의 이미지 태그를 유실시킬 수 있습니다.
빌드는 성공으로 끝나는데 실제로는 이전 이미지가 뜨는, 에러 없는 실패입니다.
Job이 하나면 `disableConcurrentBuilds()` 하나로 전부 직렬화되어 이 문제가 사라집니다.

젯슨(`robot/ai_chat`·`bridge`·`ros2_ws`)과 파이(`iot`)는 수동 배포이므로 이 Pipeline의
대상이 아닙니다. 해당 기계들은 이 브랜치를 직접 checkout해서 실행합니다.

### Jenkins Job 설정

- Script Path: `ci/Jenkinsfile.integration`
- Branch Specifier: `*/hotfix/scenario-integration`
- Refspec: **기본값 유지** (`+refs/heads/*:refs/remotes/origin/*`)
  `deploy-common.sh`의 `verify_release_commit`가 `refs/remotes/origin/hotfix/scenario-integration`을
  읽으므로, refspec이 특정 브랜치로 좁혀져 있으면 그 ref가 만들어지지 않아 실패합니다.
- GitLab push trigger branch filter: `hotfix/scenario-integration`

`Jenkinsfile.integration`의 `BOMI_RELEASE_BRANCH`와 Job의 Branch Specifier가 서로 다르면
`HEAD is not the latest origin/<branch> commit`으로 배포가 중단됩니다. 둘은 항상 같이 바꿉니다.

### 시연 후 원복

`Jenkinsfile.integration`과 해당 Job을 제거하고, `Jenkinsfile.backend`·`Jenkinsfile.frontend`
Job의 Branch Specifier를 `be-main`·`fe-main`으로 되돌립니다. 그 두 파일은 시연 스프린트
동안 수정하지 않았으므로 그대로 사용할 수 있습니다.
