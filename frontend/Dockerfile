FROM node:24.18.0-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY index.html ./
# tsconfig.json 과 vite.config.ts 가 없으면 npm run build 의 첫 단계인 tsc --noEmit 이
# 도움말을 출력하고 exit 1 로 죽는다 — && 뒤의 vite build 는 실행조차 되지 않는다.
# vite.config.ts 가 없으면 @vitejs/plugin-react 도 등록되지 않아 JSX 변환이 깨진다.
# bomi-fe-production #11 (2026-08-07) 이 정확히 이 두 줄이 없어서 실패했다.
COPY tsconfig*.json ./
COPY vite.config.ts ./
COPY src ./src

# ── 운영 빌드에서 mock 을 끈다 (S15P11E102-371) ────────────────────────────
# Vite 는 import.meta.env.VITE_* 를 **빌드 타임에 정적 치환**한다. 컨테이너
# 런타임 환경변수로는 절대 바뀌지 않으므로 값을 여기서 굳혀야 한다.
#
# 플래그가 두 개인 이유 (frontend/src/services/bomiService.ts):
#   VITE_USE_MOCK_API            구현체를 고른다. MockBomiService <-> HttpBomiService
#   VITE_GUARDIAN_API_AUTH_READY HttpBomiService 안의 assertGuardianApiReady()
#                                게이트를 연다. false 면 모든 조회가 throw 한다.
# 하나만 뒤집으면 HttpBomiService 를 고르고도 게이트에 막혀 전 화면이 빈다.
#
# 주의: AUTH_READY=true 는 "보호자 인증이 준비됐다"는 뜻이 아니다. 보호자 채널
# 인증은 아직 없다(docs/backend-api-todo.md 1번). 단일 어르신 전제(P0)라
# 동작할 뿐이며, 인증이 붙기 전까지 이 이름은 사실과 다르다.
#
# 롤백(예시 데이터로 복귀):
#   docker compose build --build-arg VITE_USE_MOCK_API=true \
#     --build-arg VITE_GUARDIAN_API_AUTH_READY=false frontend
ARG VITE_USE_MOCK_API=false
ARG VITE_GUARDIAN_API_AUTH_READY=true
ENV VITE_USE_MOCK_API=$VITE_USE_MOCK_API
ENV VITE_GUARDIAN_API_AUTH_READY=$VITE_GUARDIAN_API_AUTH_READY

RUN npm run build

FROM nginx:1.30.4-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 8080
