FROM node:24.18.0-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY index.html ./
COPY tsconfig*.json ./
COPY vite.config.ts ./
COPY src ./src

# 빌드 시점에 Vite 환경변수를 주입한다(Vite는 빌드 때 값을 번들에 박음).
# 운영 기본값: 실제 API 사용. 같은 도메인에서 Nginx가 /api·/ws를 백엔드로 프록시.
ARG VITE_USE_MOCK_API=false
ARG VITE_API_BASE_URL=/api
ARG VITE_WS_URL=/ws
ENV VITE_USE_MOCK_API=$VITE_USE_MOCK_API \
    VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_WS_URL=$VITE_WS_URL

RUN npm run build

FROM nginx:1.30.4-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 8080
