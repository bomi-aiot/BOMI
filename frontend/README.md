# BOMI Frontend

React 19 · Vite · **TypeScript(strict)** 기반의 BOMI 보호자 웹입니다. `src/` 전체가
`.ts`/`.tsx`이며 `tsconfig.json`은 `allowJs: false`, `strict: true`입니다.

## 로컬 개발

```bash
npm ci
npm run dev
```

기본 개발 서버 주소는 `http://localhost:5173`입니다.

## 빌드 검증

```bash
npm ci
npm run build     # tsc --noEmit && vite build
npm run typecheck # 타입만 빠르게
```

**자동 테스트는 없습니다.** 단위·통합 테스트 파일이 하나도 없고 lint 스크립트도 없어
검증 수단은 타입 검사와 빌드 성공뿐입니다. 화면 동작은 직접 확인하고 그 경로를 MR에
적습니다.

빌드 결과는 `dist/`에 생성됩니다. 운영 배포에서는 로컬의 `dist/`를 사용하지
않고 Docker 이미지의 builder 단계에서 `npm ci`와 `npm run build`를 수행합니다.

## 데이터 소스 플래그 두 개 — 빌드 타임에 굳습니다

Vite는 `import.meta.env.VITE_*`를 **빌드 타임에 정적 치환**합니다. 컨테이너를 띄울 때
환경변수를 넣어도 절대 바뀌지 않습니다. 값을 바꾸려면 이미지를 다시 빌드해야 합니다.

| 플래그 | 하는 일 | 운영 이미지 기본값 | `.env.example` 기본값 |
| --- | --- | --- | --- |
| `VITE_USE_MOCK_API` | 구현체 선택. `MockBomiService` ↔ `HttpBomiService` | `false`(실서버) | `true`(예시 데이터) |
| `VITE_GUARDIAN_API_AUTH_READY` | `HttpBomiService`의 게이트. `false`면 **모든 조회가 예외를 던집니다** | `true` | `false` |

**둘은 반드시 같이 뒤집습니다.** 하나만 바꾸면 실서버 구현체를 고른 채 게이트에 막혀
화면 전체가 빕니다. 예시 데이터로 되돌리려면:

```bash
docker compose build \
  --build-arg VITE_USE_MOCK_API=true \
  --build-arg VITE_GUARDIAN_API_AUTH_READY=false frontend
```

`VITE_GUARDIAN_API_AUTH_READY=true`는 "보호자 인증이 준비됐다"는 뜻이 **아닙니다.**
보호자 채널 인증은 아직 없고(`services/http.ts`에 인증 헤더가 없습니다), 단일 어르신
전제 위에서 동작할 뿐입니다.

예시 데이터 모드에서는 `?demoState=` 쿼리 파라미터로 화면 상태를 바꿀 수 있습니다
(`urgent` · `alert-error` · `empty` · `unknown` · `stale` · `error`). 실 API 모드에서는
동작하지 않습니다.

실 API 모드에서 아직 연결되지 않은 기능이 있습니다. 어르신 프로필 저장과 대화 정보(기억)의
추가·수정·삭제·토글은 예외를 던집니다(`bomiService.ts`의 `unsupportedRealMutation`).
복약·일정 CRUD는 반대로 전부 연결되어 있습니다.

`.env.example`과 타입 선언에 있는 `VITE_WS_URL`은 **죽은 변수**입니다. `src/` 어디서도
읽지 않습니다.

## 운영 컨테이너

`Dockerfile`은 다음 두 단계로 이미지를 생성합니다.

1. Node.js 이미지에서 Vite 정적 파일을 빌드합니다.
2. 빌드 결과만 Nginx 이미지에 복사하여 8080 포트로 제공합니다.

컨테이너의 8080 포트는 EC2 호스트에 공개하지 않습니다. 외부 요청은 공용 Nginx가
`bomi-proxy-net` 내부에서 `frontend:8080`으로 전달합니다.

**이 컨테이너의 `nginx.conf`에는 `/api` 프록시가 없습니다.** 정적 파일 제공과 SPA
fallback만 합니다. `/api/` 라우팅과 20r/s rate limit은 공용 Nginx
(`infra/nginx/conf.d/bomi.conf`)의 몫입니다. 개발 서버에서는 Vite 프록시가 같은 일을
합니다(`vite.config.ts`, 대상은 `VITE_PROXY_TARGET` 또는 `http://localhost:8080`).

| 항목 | 값 |
| --- | --- |
| 컨테이너 포트 | 8080 (호스트 비공개) |
| 헬스 경로 | `/frontend-health` → 200 `ok` |
| SPA fallback | 파일이 없으면 `index.html` |
| 정적 캐시 | `/assets/` 1년 immutable |
| dev / preview 포트 | 5173 / 4173 |
