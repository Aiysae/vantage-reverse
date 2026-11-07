"""Manage the macOS per-user task service for this checkout."""
import hashlib
import os
from pathlib import Path
import plistlib
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
label = 'io.vantage.reverse.' + hashlib.sha256(str(ROOT).encode()).hexdigest()[:12]
domain = f'gui/{os.getuid()}'
path = Path.home() / 'Library/LaunchAgents' / (label + '.plist')
if sys.argv[1:] == ['stop']:
    subprocess.run(['launchctl', 'bootout', domain + '/' + label], capture_output=True)
    path.unlink(missing_ok=True)
    raise SystemExit(0)
if sys.argv[1:] != ['start']:
    raise SystemExit('usage: task_service.py start|stop')
(ROOT / 'evidence').mkdir(exist_ok=True)
path.parent.mkdir(parents=True, exist_ok=True)
env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin:/usr/sbin:/sbin'), 'PYTHONUNBUFFERED': '1'}
for key in ('DOCKER_CONTEXT', 'CODEX_HOME', 'HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY'):
    if os.environ.get(key):
        env[key] = os.environ[key]
config = {'Label': label, 'ProgramArguments': [str(ROOT / 'tools/.venv/bin/python'), str(ROOT / 'scripts/task_server.py')],
          'WorkingDirectory': str(ROOT), 'EnvironmentVariables': env, 'RunAtLoad': True, 'KeepAlive': True,
          'ThrottleInterval': 15, 'StandardOutPath': str(ROOT / 'evidence/task-service.log'),
          'StandardErrorPath': str(ROOT / 'evidence/task-service.log')}
content = plistlib.dumps(config)
subprocess.run(['launchctl', 'bootout', domain + '/' + label], capture_output=True)
path.write_bytes(content)
subprocess.run(['launchctl', 'bootstrap', domain, str(path)], check=True)
