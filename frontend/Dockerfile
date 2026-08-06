FROM node:24.18.0-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY index.html ./
COPY tsconfig*.json ./
COPY vite.config.ts ./
COPY src ./src

# 빌드 시점에 Vite 환경변수를 주입한다(Vite는 빌드 때 값을 번들에 박음).
# 보호자 권한 경계가 준비되기 전 안전 기본값: 명시된 예시 데이터 사용.
# 실제 연동 시 build arg로 MOCK=false, AUTH_READY=true를 함께 명시해야 한다.
ARG VITE_USE_MOCK_API=true
ARG VITE_GUARDIAN_API_AUTH_READY=false
ARG VITE_API_BASE_URL=/api
ARG VITE_WS_URL=/ws
ENV VITE_USE_MOCK_API=$VITE_USE_MOCK_API \
    VITE_GUARDIAN_API_AUTH_READY=$VITE_GUARDIAN_API_AUTH_READY \
    VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_WS_URL=$VITE_WS_URL

RUN npm run build

FROM nginx:1.30.4-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 8080
