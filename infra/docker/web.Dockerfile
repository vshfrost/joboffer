# syntax=docker/dockerfile:1
# Образ фронту (web/): збірка Vite → статика в Caddy. Контекст збірки — корінь репо.
FROM node:26.12.1-alpine AS build
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM caddy:2.11.7-alpine
COPY infra/web/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /web/dist /srv/app
EXPOSE 8080
