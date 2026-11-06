#!/usr/bin/env bash
# Frontend-команди в Docker (Node на машині не потрібен).
#   scripts/web.sh ci | run build | run typecheck | run lint | run test
#   scripts/web.sh run dev        → Vite на http://localhost:5174/
set -euo pipefail
cd "$(dirname "$0")/.."

NODE_IMAGE="node:24.21.0-alpine"
tty_flags=()
if [ -t 0 ] && [ -t 1 ]; then tty_flags=(-it); fi

# Порт публікуємо лише для dev/preview, щоб інші команди (напр. CI) не конфліктували з dev-сервером.
port_flags=()
case "${1:-} ${2:-}" in
  # host-gateway: Vite-проксі /api ходить на бекенд, запущений на машині (Linux теж).
  "run dev" | "run preview") port_flags=(-p 127.0.0.1:5174:5174 --add-host=host.docker.internal:host-gateway) ;;
esac

exec docker run --rm ${tty_flags[@]+"${tty_flags[@]}"} \
  --user "$(id -u):$(id -g)" \
  -e npm_config_cache=/tmp/.npm -e npm_config_update_notifier=false \
  -v "$PWD/web:/app" -w /app \
  ${port_flags[@]+"${port_flags[@]}"} \
  "$NODE_IMAGE" npm "$@"
