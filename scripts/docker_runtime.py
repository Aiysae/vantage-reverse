"""Recover only the existing workbench engine; runs outside Docker in the task service."""
import json
from pathlib import Path
import subprocess
import threading
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
PAUSED = ROOT / 'evidence/docker-recovery-paused'
STATE = ROOT / 'evidence/docker-recovery.json'
DOCKER = ['docker']
LOCK = threading.RLock()
_state = {'status': 'healthy', 'message': 'Docker 自动恢复已开启', 'recoveries': 0}


class Unavailable(RuntimeError):
    pass


def status():
    with LOCK:
        return dict(_state)


def available():
    return status()['status'] == 'healthy' and not PAUSED.exists()


def update(**values):
    with LOCK:
        _state.update(values)
        temporary = STATE.with_suffix('.tmp')
        temporary.write_text(json.dumps(_state, ensure_ascii=False, indent=2))
        temporary.replace(STATE)


def run(command, env, timeout=15, check=False):
    result = subprocess.run(command, env=env, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode:
        # Do not publish CLI output: Compose/engine diagnostics may include environment values.
        raise RuntimeError(f'{Path(command[0]).name} 操作未完成（退出码 {result.returncode}），稍后自动重试')
    return result


def engine_ready(env):
    try:
        return run([*DOCKER, 'version', '--format', '{{.Server.Version}}'], env).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def app_ready():
    try:
        return httpx.get('http://127.0.0.1:18780/api/v1/utils/health-check/', timeout=5, trust_env=False).status_code == 200
    except httpx.HTTPError:
        return False


def tick(env):
    if PAUSED.exists():
        update(status='paused', message='工作台已主动停止，自动恢复已暂停；启动工作台后重新开启', next_check=None)
        return
    if status().get('next_check', 0) and time.time() < status()['next_check']:
        return
    engine = engine_ready(env)
    if engine and app_ready():
        update(status='healthy', message='Docker 与工作台运行正常，自动恢复已开启', next_check=None)
        return
    update(status='recovering', message='正在自动恢复 Docker 和本机工作台，开发进度已保留', next_check=None)
    try:
        if not engine:
            raise RuntimeError('Docker 引擎未连接，请启动 Docker 后重试')
        if PAUSED.exists():
            return
        run([*DOCKER, 'compose', '--env-file', str(ROOT / '.env'), '-f', str(ROOT / 'compose.yml'),
             'up', '-d', '--no-build', '--pull', 'never', '--wait', '--wait-timeout', '120'], env, timeout=160, check=True)
        if not app_ready():
            raise RuntimeError('Docker 已连接，工作台仍在启动，稍后自动重试')
        update(status='healthy', message='Docker 与工作台已自动恢复，中断任务会自动接续',
               recoveries=status().get('recoveries', 0) + 1, last_recovered_at=time.time(), last_error='', next_check=None)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        message = str(exc) if isinstance(exc, RuntimeError) else 'Docker 恢复操作超时或运行环境未就绪，稍后自动重试'
        update(status='waiting', message=message, last_error=message, next_check=time.time() + 120)


def initialize():
    previous = {}
    if STATE.is_file():
        try:
            previous = json.loads(STATE.read_text())
        except (ValueError, OSError):
            pass
    update(status='checking', message='正在检查 Docker 与工作台运行状态', next_check=None,
           recoveries=previous.get('recoveries', 0), last_recovered_at=previous.get('last_recovered_at'))


def monitor(env):
    while True:
        try:
            tick(env)
        except (OSError, ValueError):
            pass
        time.sleep(15)
