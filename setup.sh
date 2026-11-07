#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ "$(uname -s)" != Darwin ]]; then echo '目前安装流程仅支持 macOS。'; exit 1; fi
for cmd in python3.12 node npm docker curl unzip shasum uv; do command -v "$cmd" >/dev/null || { echo "缺少依赖：$cmd"; exit 1; }; done
python3.12 -m venv tools/.venv
uv pip install --python tools/.venv/bin/python -r tools/requirements.lock.txt
(cd tools && npm ci && npx playwright install chromium)
tools/.venv/bin/python -m playwright install chromium
mkdir -p tools/craft-anything/0.5.0 evidence tasks
archive=$(mktemp -t vantage-craft.XXXXXX)
trap 'rm -f "$archive"' EXIT
curl -fL --retry 2 'https://github.com/storytold/craft-anything/releases/download/v0.5.0/craft-anything-cli-0.5.0-macos-universal.zip' -o "$archive"
printf '%s  %s\n' '88ce25c2d727e8536678a4c9877e1a8020165198869135f08e7fac13761835fc' "$archive" | shasum -a 256 -c -
unzip -o -q "$archive" -d tools/craft-anything/0.5.0
if [[ ! -f .env ]]; then
  tools/.venv/bin/python - <<'PY'
import secrets
from pathlib import Path
path = Path('.env')
path.write_text('POSTGRES_PASSWORD=' + secrets.token_hex(24) + '\nSECRET_KEY=' + secrets.token_hex(32) + '\nFIRST_SUPERUSER=admin@example.com\nFIRST_SUPERUSER_PASSWORD=' + secrets.token_hex(24) + '\n')
path.chmod(0o600)
PY
fi
if [[ ! -f agent.env ]]; then cp agent.env.example agent.env; chmod 600 agent.env; fi
echo '安装完成。启动 Docker 后执行 ./workbench.sh up。'
