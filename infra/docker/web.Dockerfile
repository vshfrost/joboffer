# syntax=docker/dockerfile:1
# Образ фронту (web/): збірка Vite → статика в Caddy. Контекст збірки — корінь репо.
FROM node:26.12.1-alpine AS build
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM caddy:2.11.9-alpine
COPY infra/web/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /web/dist /srv/app
# Не root: Caddy слухає 8080 (> 1024, привілеїв не треба), а стан пише лише у /config і /data.
RUN addgroup -S -g 10002 web \
    && adduser -S -u 10002 -G web -H web \
    && chown -R web:web /config /data
USER web
EXPOSE 8080
