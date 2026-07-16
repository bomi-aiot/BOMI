# BOMI 팀 개발 행동 강령

이 문서는 BOMI 프로젝트에 참여하는 모든 팀원이 동일한 방식으로 Git과 GitHub를 사용하기 위한 협업 규칙입니다. 모든 팀원은 작업 전에 이 문서를 읽고 아래 절차를 따릅니다.

## 1. 핵심 규칙 요약

- `main`은 시연·배포 가능한 안정 버전만 관리합니다.
- `develop`은 완료된 기능을 통합하는 개발 브랜치입니다.
- 모든 작업은 최신 `develop`에서 새 브랜치를 만들어 시작합니다.
- 기능 브랜치는 `feat/*`, 수정 브랜치는 `fix/*`, 문서는 `docs/*` 형식을 사용합니다.
- 기능 브랜치는 `develop`으로 Pull Request를 생성합니다.
- `main`과 `develop`에는 직접 Push하지 않습니다.
- Pull Request는 최소 1명의 승인 후 Squash merge합니다.
- 비밀번호, API Key, `.env` 등 민감정보는 절대 커밋하지 않습니다.
- 현재 GitHub Organization에서는 별도 Team을 만들지 않고 팀원별로 저장소 권한을 부여합니다.

## 2. 브랜치 구조

(예시)
```text
main
└─ develop
   ├─ feat/be-door-event
   ├─ feat/fe-home-dashboard
   ├─ feat/robot-navigation
   ├─ feat/iot-door-sensor
   ├─ fix/be-health-check
   └─ docs/system-architecture
```

### `main`

- 시연 또는 배포할 수 있는 안정 버전만 관리합니다.
- 평상시 기능 개발의 대상 브랜치로 사용하지 않습니다.
- 릴리스 시점에만 `develop → main` Pull Request를 생성합니다.

### `develop`

- 팀원들의 완료된 기능을 통합하는 브랜치입니다.
- 모든 기능 브랜치는 최신 `develop`에서 생성합니다.
- 기능 작업은 Pull Request를 통해서만 병합합니다.

### 작업 브랜치

- `feat/*`: 새로운 기능
- `fix/*`: 버그 및 설정 오류 수정
- `docs/*`: 문서 중심 변경
- `refactor/*`: 동작 변경 없는 구조 개선
- `chore/*`: 빌드, 의존성, 공통 설정 작업

브랜치 이름에는 담당 영역과 작업 목적을 짧고 명확하게 작성합니다.

```text
feat/be-door-event
feat/fe-home-dashboard
feat/robot-navigation
feat/robot-mqtt
feat/iot-door-sensor
fix/be-health-check
docs/system-architecture
```

권장 영역 약어:

- `be`: Backend
- `fe`: Frontend
- `robot`: ROS 2 및 로봇
- `iot`: 센서 및 장치
- `infra`: 서버·배포 설정

## 3. 팀원의 최초 참여 절차

### 3.1 Organization 초대 수락

GitHub 이메일 또는 알림으로 받은 Organization 초대를 먼저 수락합니다. 초대를 수락하지 않으면 Private 저장소를 Clone할 수 없습니다.

### 3.2 저장소 Clone

```bash
git clone https://github.com/조직이름/BOMI.git
cd BOMI
git switch develop
```

조직 이름과 저장소 대소문자는 실제 GitHub 주소에 맞게 변경합니다.

### 3.3 연결 상태 확인

```bash
git branch
git remote -v
```

정상 기준:

- 현재 브랜치 앞에 `* develop`이 표시됩니다.
- `origin`이 Organization의 BOMI 저장소를 가리킵니다.

### 3.4 개인 환경변수 생성

PowerShell:

```powershell
Copy-Item .env.example .env
```

Git Bash, macOS 또는 Linux:

```bash
cp .env.example .env
```

`.env`는 각 팀원이 자신의 환경에서만 관리합니다. 서버 주소와 계정 등 민감정보는 GitHub가 아닌 팀에서 합의한 보안 채널로 공유합니다.

다음 명령으로 `.env`가 Git에서 제외되는지 확인합니다.

```bash
git check-ignore -v .env
```

## 4. 기능 개발 절차

### 4.1 Issue 확인 또는 생성

작업을 시작하기 전에 GitHub Issue에서 다음 내용을 확인하거나 작성합니다.

- 작업 목적
- 요구사항
- 완료 조건
- 담당자
- 관련 영역

동일한 기능을 두 명이 중복 개발하지 않도록 담당자를 지정한 뒤 시작합니다.

### 4.2 최신 `develop` 반영

```bash
git switch develop
git pull origin develop
```

로컬 `develop`에서 직접 코드를 수정하지 않습니다. 실수로 수정했다면 브랜치를 생성한 뒤 작업을 이어갑니다.

```bash
git switch -c feat/be-health-check
```

### 4.3 기능 브랜치 생성

```bash
git switch -c feat/be-door-event
```

브랜치는 한 가지 목적만 갖도록 작게 구성합니다. 프런트엔드 화면과 백엔드 API가 독립적으로 리뷰 가능하다면 별도 브랜치와 PR로 분리합니다.

### 4.4 작업 중 상태 확인

```bash
git status
git diff
```

커밋 전에는 변경한 파일과 실제 변경 내용을 확인합니다.

## 5. 커밋 규칙

### 5.1 파일 추가

가능하면 변경한 파일을 명시적으로 추가합니다.

```bash
git add backend/src/main/java/com/ssafy/bomi/health/HealthController.java
git add docs/api/README.md
```

전체 파일을 추가해야 할 때만 다음 명령을 사용합니다.

```bash
git add .
```

스테이징 결과를 반드시 확인합니다.

```bash
git status
git diff --cached
```

### 5.2 커밋 메시지

형식:

```text
type: 작업 요약
```

사용 가능한 대표 타입:

- `feat`: 새로운 기능
- `fix`: 버그 수정
- `docs`: 문서 변경
- `refactor`: 기능 변화 없는 구조 개선
- `test`: 테스트 추가 또는 수정
- `chore`: 설정, 의존성, 빌드 작업
- `style`: 포맷, 공백 등 동작과 무관한 변경

예시:

```bash
git commit -m "feat: add door event handling"
git commit -m "fix: disable database connection for local health check"
git commit -m "docs: document MQTT topic convention"
```

커밋 하나에는 가능한 한 하나의 논리적인 변경만 포함합니다.

### 5.3 브랜치 Push

최초 Push:

```bash
git push -u origin feat/be-door-event
```

이후 같은 브랜치의 Push:

```bash
git push
```

## 6. Pull Request 규칙

기능 개발 PR의 대상과 비교 브랜치는 다음과 같습니다.

```text
base: develop
compare: feat/be-door-event
```

즉, 평상시 병합 방향은 다음과 같습니다.

```text
feat/* → develop
fix/*  → develop
docs/* → develop
```

`main`에는 기능 브랜치를 직접 병합하지 않습니다. 시연 또는 배포 버전을 만들 때만 다음 PR을 생성합니다.

```text
develop → main
```

### 6.1 PR 작성 항목

저장소의 Pull Request 템플릿에 따라 다음 내용을 작성합니다.

- 작업 내용
- 변경 범위
- 테스트 방법과 결과
- 관련 Issue
- 민감정보 포함 여부
- 아직 구현하지 않은 부분 또는 후속 작업

화면 변경은 가능하면 스크린샷을 첨부합니다. API 변경은 요청·응답 예시를 작성하고, MQTT 변경은 토픽과 메시지 예시를 작성합니다.

### 6.2 PR 크기

- 하나의 PR은 하나의 목적을 가집니다.
- 리뷰하기 어려운 대규모 PR은 기능 단위로 나눕니다.
- 불필요한 포맷 변경을 기능 코드와 섞지 않습니다.
- PR을 만든 뒤 본인이 먼저 `Files changed`를 검토합니다.

## 7. 리뷰와 병합 규칙

- 작성자가 아닌 팀원 최소 1명이 리뷰합니다.
- 승인되지 않은 PR은 병합하지 않습니다.
- 리뷰에서 `Request changes`가 있으면 수정 후 다시 리뷰를 요청합니다.
- 모든 대화와 지적사항을 해결한 뒤 병합합니다.
- 병합 방식은 기본적으로 `Squash and merge`를 사용합니다.
- 병합 후 원격 기능 브랜치는 삭제합니다.

리뷰어는 다음을 확인합니다.

- 요구사항과 완료 조건을 만족하는가
- 실행 또는 테스트 방법이 명확한가
- 기존 기능에 부작용이 없는가
- 민감정보가 포함되지 않았는가
- 코드와 문서가 함께 갱신되었는가
- 아직 구현되지 않은 부분이 명시되었는가

## 8. 병합 후 정리

기능 브랜치가 병합되면 로컬에서 다음을 실행합니다.

```bash
git switch develop
git pull origin develop
git branch -d feat/be-door-event
```

원격 브랜치는 GitHub의 `Delete branch` 버튼으로 삭제합니다. 다른 작업을 시작할 때는 다시 최신 `develop`에서 새 브랜치를 생성합니다.

## 9. 충돌 처리 원칙

PR에 충돌이 표시되면 작업 브랜치에서 최신 `develop`을 반영합니다.

```bash
git switch feat/be-door-event
git fetch origin
git merge origin/develop
```

충돌 파일을 수정한 뒤:

```bash
git add 충돌을해결한파일
git commit
git push
```

충돌 해결 과정에서 다른 팀원의 변경을 임의로 삭제하지 않습니다. 의도가 불분명하면 해당 작성자와 함께 해결합니다.

공용 브랜치에는 `git push --force`를 사용하지 않습니다.

## 10. 영역별 최소 테스트

### Backend

```powershell
cd backend
.\gradlew.bat test
```

DB가 없는 로컬 환경에서는 Health Controller 단위 테스트 또는 DB 자동설정을 제외한 실행 결과를 PR에 기록합니다. 제공 서버 연동이 필요한 테스트는 실행 여부와 미실행 사유를 명시합니다.

### Frontend

```bash
cd frontend
npm install
npm run build
```

### Robot / IoT

- 실제 장치가 필요한 테스트인지 명시합니다.
- Mock 테스트와 실제 장치 테스트를 구분합니다.
- 사용한 ROS 2, Python, 장치 환경을 PR에 기록합니다.

테스트할 수 없는 기능은 성공한 것처럼 작성하지 않고, 미검증 사유와 후속 검증 계획을 기록합니다.

## 11. 민감정보 관리

다음 파일과 값은 절대 Git에 포함하지 않습니다.

```text
.env
application-local.yml
application-secret.yml
실제 MQTT 인증정보
DB 비밀번호
API Key
SSH Private Key
장치별 실제 네트워크 설정
```

저장소에는 예시 파일만 포함합니다.

```text
.env.example
frontend/.env.example
backend/.env.example
robot/config/*.example.yaml
iot/config/*.example.yaml
```

실제 비밀값을 Push했다면 파일 삭제만으로 해결되지 않습니다. 즉시 팀에 알리고 해당 비밀번호나 Key를 폐기·재발급해야 합니다.

## 12. 공유 서버 및 Docker 주의사항

- 공유 서버의 컨테이너를 임의로 종료하거나 재생성하지 않습니다.
- 데이터 삭제 가능성이 있는 명령은 실행 전에 담당자와 확인합니다.
- 공유 환경에서는 `docker compose down -v`를 절대 임의 실행하지 않습니다.
- 서버 접속정보와 운영 환경변수는 GitHub Issue, PR, 코드에 작성하지 않습니다.

## 13. 절대 금지 사항

- `main` 직접 Push
- `develop` 직접 Push
- 승인 없이 다른 팀원의 브랜치 수정
- 공용 브랜치 또는 다른 팀원 브랜치에 `git push --force` 사용
- `.env`, API Key, DB 비밀번호, SSH Key 커밋
- 동작 또는 테스트 확인 없이 PR 병합
- 리뷰 지적사항을 해결하지 않고 임의 병합
- 공유 서버에서 `docker compose down -v` 실행
- `node_modules`, `dist`, Gradle 빌드 결과물 커밋
- IntelliJ 개인 설정인 `.idea` 커밋
- 준비되지 않은 기능을 구현 완료로 보고

## 14. 문제가 생겼을 때

다음 상황에서는 임의로 이력을 변경하지 말고 팀에 먼저 공유합니다.

- `main` 또는 `develop`에 잘못 Push한 경우
- 민감정보를 커밋하거나 Push한 경우
- 다른 팀원의 변경을 덮어쓴 경우
- 대규모 충돌이 발생한 경우
- 공유 서버나 DB 데이터에 영향을 줄 수 있는 경우

상황 공유 시 다음 정보를 제공합니다.

```bash
git status
git branch --show-current
git log --oneline -5
git remote -v
```

비밀번호나 토큰이 포함된 출력은 반드시 가린 뒤 공유합니다.

## 15. 일일 작업 체크리스트

작업 시작:

```text
[ ] Organization과 저장소 접근 권한 확인
[ ] develop으로 이동
[ ] origin/develop 최신 변경 Pull
[ ] 작업 목적에 맞는 새 브랜치 생성
[ ] 관련 Issue 확인 또는 생성
```

작업 종료 및 PR 생성 전:

```text
[ ] git status와 diff 확인
[ ] 민감정보 및 불필요한 파일 제외
[ ] 담당 영역의 테스트 또는 빌드 실행
[ ] 명확한 커밋 메시지 작성
[ ] 작업 브랜치 Push
[ ] develop 대상 PR 생성
[ ] 테스트 결과와 미구현 항목 기록
[ ] 본인이 Files changed를 먼저 검토
```

병합 전:

```text
[ ] 최소 1명 승인
[ ] 리뷰 지적사항 해결
[ ] 충돌 없음
[ ] 필요한 테스트 통과
[ ] Squash and merge 사용
```
