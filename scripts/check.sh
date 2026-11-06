#!/usr/bin/env bash
# Швидка локальна перевірка змін (≤ ~2 хв), одна синхронна команда з кореня репо.
#   scripts/check.sh            → що змінено відносно origin/main (коміти, робоче дерево, нові файли)
#   scripts/check.sh <шляхи…>   → лише ці файли (від кореня репо)
# app/: ruff check, ruff format --check, mypy, pytest лише змінених test_*.py (без -n, без покриття).
# web/: lint, typecheck, `vitest related --run` для змінених файлів.
# Повний прогін (усі тести, покриття, infra) — тільки в GitHub CI (scripts/ci.sh); локально його не запускати.
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo"

step() { printf '\n\033[1m▶ %s\033[0m\n' "$*"; }

if [ "$#" -gt 0 ]; then
  files=("$@")
else
  files=()
  while IFS= read -r f; do files+=("$f"); done < <(
    { git diff --name-only origin/main; git ls-files --others --exclude-standard; } | sort -u
  )
fi

app_files=()
web_files=()
for f in ${files[@]+"${files[@]}"}; do
  case "$f" in
    app/*) app_files+=("${f#app/}") ;;
    web/*) web_files+=("${f#web/}") ;;
  esac
done

if [ "${#app_files[@]}" -eq 0 ] && [ "${#web_files[@]}" -eq 0 ]; then
  echo "нема змін в app/ чи web/ — перевіряти нічого"
  exit 0
fi

if [ "${#app_files[@]}" -gt 0 ]; then
  cd "$repo/app"

  step "app: ruff lint + format"
  uv run ruff check .
  uv run ruff format --check .

  step "app: mypy --strict"
  uv run mypy

  tests=()
  for f in "${app_files[@]}"; do
    case "$f" in
      tests/*test_*.py) [ -f "$f" ] && tests+=("$f") ;;
    esac
  done
  if [ "${#tests[@]}" -gt 0 ]; then
    step "app: pytest лише змінених тестів (${#tests[@]})"
    uv run pytest -q "${tests[@]}"
  else
    echo "змінених test_*.py нема — pytest пропущено"
  fi
  cd "$repo"
fi

if [ "${#web_files[@]}" -gt 0 ]; then
  step "web: lint + межі шарів"
  scripts/web.sh run lint

  step "web: typecheck"
  scripts/web.sh run typecheck

  related=()
  for f in "${web_files[@]}"; do
    case "$f" in
      src/*.ts | src/*.tsx) [ -f "web/$f" ] && related+=("$f") ;;
    esac
  done
  if [ "${#related[@]}" -gt 0 ]; then
    step "web: vitest related (${#related[@]} файлів)"
    scripts/web.sh exec -- vitest related --run "${related[@]}"
  else
    echo "змінених src/*.ts(x) нема — vitest пропущено"
  fi
fi

printf '\n\033[1;32m✔ локальна перевірка пройдена\033[0m (повний CI — лише на GitHub)\n'
