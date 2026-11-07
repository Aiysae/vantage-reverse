#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$PWD"
compose() { docker compose --env-file "$ROOT/.env" -f "$ROOT/compose.yml" "$@"; }
case "${1:-status}" in
  up)
    test -f .env && test -x tools/.venv/bin/python || { echo '请先执行 ./setup.sh'; exit 1; }
    mkdir -p evidence tasks
    if lsof -nP -iTCP:18781 -sTCP:LISTEN >/dev/null 2>&1; then echo '18781 端口已占用，请先关闭占用进程'; exit 1; fi
    if lsof -nP -iTCP:18780 -sTCP:LISTEN >/dev/null 2>&1; then echo '18780 端口已占用，请先关闭占用进程'; exit 1; fi
    rm -f evidence/docker-recovery-paused
    docker info >/dev/null
    compose up -d --build --wait --wait-timeout 240
    "$ROOT/tools/.venv/bin/python" "$ROOT/scripts/task_service.py" start
    ready=0
    for _ in {1..30}; do
      if lsof -nP -iTCP:18781 -sTCP:LISTEN >/dev/null 2>&1; then ready=1; break; fi
      sleep 1
    done
    if [[ "$ready" != 1 ]]; then
      echo '任务服务启动失败，请查看 evidence/task-service.log'
      exit 1
    fi
    echo '工作台：http://127.0.0.1:18780/develop'
    ;;
  stop)
    mkdir -p evidence
    touch evidence/docker-recovery-paused
    "$ROOT/tools/.venv/bin/python" "$ROOT/scripts/task_service.py" stop
    compose stop
    ;;
  status) compose ps ;;
  logs) compose logs --tail 80 ;;
  agent-check) "$ROOT/tools/.venv/bin/python" "$ROOT/scripts/agent.py" --check ;;
  *) echo '用法：./workbench.sh up|stop|status|logs|agent-check'; exit 2 ;;
esac
