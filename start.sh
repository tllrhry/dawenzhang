#!/usr/bin/env bash
set -euo pipefail

# Local development entry point. Docker Compose owns PostgreSQL; FastAPI and
# Vite run on the host so the frontend remains available with hot reload.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$ROOT_DIR/data/logs"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"
FRONTEND_PORT=5173

cd "$ROOT_DIR"
mkdir -p "$LOG_DIR"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "缺少必需命令：$1" >&2
    exit 1
  fi
}

wait_for_url() {
  local url="$1"
  local service_name="$2"
  local log_file="$3"

  for _ in {1..30}; do
    if curl --fail --silent "$url" >/dev/null; then
      return 0
    fi
    sleep 1
  done

  echo "$service_name 未能在 30 秒内就绪。请查看日志：$log_file" >&2
  tail -n 40 "$log_file" >&2 || true
  exit 1
}

port_is_listening() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

start_background() {
  local service_name="$1"
  local port="$2"
  local service_label="$3"
  local log_file="$4"
  shift 4

  if port_is_listening "$port"; then
    echo "$service_name 已在端口 $port 运行，跳过启动。"
    return
  fi

  echo "启动${service_name}…"
  if [[ "$(uname)" == "Darwin" ]] && command -v launchctl >/dev/null 2>&1; then
    local escaped_root escaped_log escaped_path command_line
    printf -v escaped_root '%q' "$ROOT_DIR"
    printf -v escaped_log '%q' "$log_file"
    printf -v escaped_path '%q' "$PATH"
    printf -v command_line ' %q' "$@"
    launchctl bootout "gui/$(id -u)/$service_label" >/dev/null 2>&1 || true
    launchctl submit -l "$service_label" -- /bin/bash -c \
      "export PATH=$escaped_path; cd $escaped_root; exec$command_line >$escaped_log 2>&1"
  else
    nohup "$@" >"$log_file" 2>&1 < /dev/null &
  fi
}

require_command docker
require_command python
require_command npm
require_command curl
require_command lsof

PYTHON_BIN="$(command -v python)"
NPM_BIN="$(command -v npm)"
BACKEND_PORT="$(PYTHONPATH="$ROOT_DIR/backend" "$PYTHON_BIN" -c 'from app.core.config import get_settings; print(get_settings().port)')"
BACKEND_HEALTH_URL="http://127.0.0.1:${BACKEND_PORT}/api/v1/health"
FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}"

echo "启动 PostgreSQL（Docker Compose）…"
docker compose up -d --wait db

echo "执行数据库迁移…"
bash backend/scripts/migrate.sh

start_background "后端" "$BACKEND_PORT" "com.dawenzhang.backend" "$BACKEND_LOG" \
  env "PYTHONPATH=$ROOT_DIR/backend${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" backend/run.py
wait_for_url "$BACKEND_HEALTH_URL" "后端" "$BACKEND_LOG"

if [[ ! -d frontend/node_modules ]]; then
  echo "安装前端依赖…"
  (cd frontend && npm ci)
fi

start_background "前端" "$FRONTEND_PORT" "com.dawenzhang.frontend" "$FRONTEND_LOG" \
  "$NPM_BIN" --prefix frontend run dev -- --host 127.0.0.1 --port "$FRONTEND_PORT"
wait_for_url "$FRONTEND_URL" "前端" "$FRONTEND_LOG"

echo
echo "全栈已启动："
echo "  前端：$FRONTEND_URL"
echo "  后端：$BACKEND_HEALTH_URL"
echo "  后端日志：$BACKEND_LOG"
echo "  前端日志：$FRONTEND_LOG"
