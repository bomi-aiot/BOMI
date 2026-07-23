# BOMI Frontend

BOMI AIoT 돌봄 로봇의 보호자용 웹 대시보드입니다. React, TypeScript, Vite로 구성되어 있습니다.

## 로컬 실행

```bash
npm ci
npm run dev
```

기본 개발 서버는 `http://localhost:5173`입니다. 초기 MVP는 `.env.example`의
`VITE_USE_MOCK_API=true` 설정으로 Mock 데이터를 사용합니다.

## 검증과 빌드

```bash
npm run typecheck
npm run build
```

빌드 결과는 `dist/`에 생성됩니다. 운영 컨테이너는 Node.js 단계에서 빌드한 뒤 결과물만
Nginx 이미지로 복사하며, 8080 포트와 `/frontend-health` 상태 확인 경로를 제공합니다.
SPA의 직접 경로 접근은 `index.html`로 연결됩니다.

## API 연결

운영 도메인 `i15e102.p.ssafy.io`에서는 같은 출처의 `/api`와 `/ws`를 사용합니다.
백엔드 연동 시 `VITE_USE_MOCK_API=false`로 변경하고 서비스 계층의 계약을 실제 API에
연결합니다. 서버 주소를 코드에 직접 넣지 않도록 환경변수를 사용합니다.

현재 API 경로는 `src/services/bomiService.ts`에 한곳으로 모아 둔 임시 계약입니다.
프론트 내부는 camelCase를 사용하며, 실제 PostgreSQL 물리 컬럼의 snake_case 변환은
향후 HTTP adapter에서 처리합니다. `memory`와 `care_record`의 코드값, 출처 및 검증
상태는 공유 컬럼 정의서의 값을 그대로 타입으로 고정했습니다.

## 주요 경로

- `/dashboard`: 오늘의 돌봄 요약
- `/elder/profile`: 초기 질문 결과 및 어르신 프로필
- `/conversation-preferences`: 맞춤 대화 정보
- `/confirmation-requests`: AI 확인 요청
- `/health`, `/medications`: 건강 참고 정보와 복약
- `/schedules`: 병원·개인 일정
