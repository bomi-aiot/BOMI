# BOMI Frontend

React, Vite, JavaScript 기반의 BOMI 웹 애플리케이션입니다.

## 로컬 개발

```bash
npm ci
npm run dev
```

기본 개발 서버 주소는 `http://localhost:5173`입니다.

## 빌드 검증

```bash
npm ci
npm run build
```

빌드 결과는 `dist/`에 생성됩니다. 운영 배포에서는 로컬의 `dist/`를 사용하지
않고 Docker 이미지의 builder 단계에서 `npm ci`와 `npm run build`를 수행합니다.

## 운영 컨테이너

`Dockerfile`은 다음 두 단계로 이미지를 생성합니다.

1. Node.js 이미지에서 Vite 정적 파일을 빌드합니다.
2. 빌드 결과만 Nginx 이미지에 복사하여 8080 포트로 제공합니다.

컨테이너의 8080 포트는 EC2 호스트에 공개하지 않습니다. 외부 요청은 공용 Nginx가
`bomi-proxy-net` 내부에서 `frontend:8080`으로 전달합니다. `/api/` 요청은 기존과
동일하게 Backend로 전달됩니다.

컨테이너 상태 확인 경로는 `/frontend-health`입니다. SPA 경로는 파일이 없으면
`index.html`로 처리됩니다.
