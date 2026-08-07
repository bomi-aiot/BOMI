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
RUN npm run build

FROM nginx:1.30.4-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 8080
