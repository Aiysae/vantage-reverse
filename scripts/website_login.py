"""Keep target-site browser sessions outside project files and model prompts."""
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import threading
import time
from urllib.parse import urlsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SESSIONS = ROOT / '.website-sessions'
LOCK = threading.RLock()
PROCESSES = {}


def origin(website):
    url = urlsplit(website)
    if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or len(website) > 2048:
        raise ValueError('请先填写完整的网站网址，网址中请勿包含账号密码')
    port = url.port or (443 if url.scheme == 'https' else 80)
    return f'{url.scheme}://{url.hostname.lower()}:{port}'


def directory(session_id):
    if not re.fullmatch(r'[a-f0-9]{32}', session_id or ''):
        raise ValueError('登录记录无效，请重新打开网站登录')
    return SESSIONS / session_id


def read(session_id):
    try:
        return json.loads((directory(session_id) / 'session.json').read_text())
    except FileNotFoundError:
        raise ValueError('登录记录已清除，请重新登录目标网站')


def write(record):
    path = directory(record['id']) / 'session.json'
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(record, ensure_ascii=False))
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def latest(website):
    site = origin(website)
    with LOCK:
        records = [json.loads(p.read_text()) for p in SESSIONS.glob('*/session.json')]
        records = [r for r in records if r['origin'] == site]
        return max(records, key=lambda r:r['created_at']) if records else None


def open_login(website, env):
    site = origin(website)
    with LOCK:
        for process in PROCESSES.values():
            if process.poll() is None:
                raise ValueError('已有网站登录窗口打开，请先保存或取消当前登录')
        SESSIONS.mkdir(mode=0o700, exist_ok=True)
        os.chmod(SESSIONS, 0o700)
        record = latest(website)
        if record is None:
            record = {'id': uuid4().hex, 'origin': site, 'website': website, 'created_at': time.time(), 'persistent': True}
            directory(record['id']).mkdir(mode=0o700)
        record.update(website=website, status='opening', message='正在复用已有会话打开网站；若仍需验证，请扫码或登录。')
        (directory(record['id'])/'save.request').unlink(missing_ok=True)
        write(record)
        try:
            process = subprocess.Popen([str(ROOT / 'tools/.venv/bin/python'), str(Path(__file__).resolve()), record['id']],
                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            PROCESSES[record['id']] = process
        except OSError:
            record.update(status='failed', message='登录窗口启动失败，请重试')
            write(record)
        return record


def save_login(session_id):
    with LOCK:
        record = read(session_id)
        process = PROCESSES.get(session_id)
        if record['status'] != 'waiting' or not process or process.poll() is not None:
            raise ValueError('登录窗口已关闭，请重新打开网站登录')
        (directory(session_id) / 'save.request').touch(mode=0o600)
        return record


def clear_login(session_id):
    with LOCK:
        process = PROCESSES.pop(session_id, None)
        if process and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        shutil.rmtree(directory(session_id), ignore_errors=True)
        return {'cleared': True}


def for_task(session_id, website):
    if not session_id:
        return {}
    with LOCK:
        record = read(session_id)
        if record['origin'] != origin(website):
            raise ValueError('已保存的登录状态属于另一个网站，请先登录当前目标网站')
        path = directory(session_id)
        if record['status'] != 'saved' or not (path / 'storage.json').is_file():
            raise ValueError('请先完成目标网站登录并保存登录状态')
        hook = path/'mcp-session.ts'
        hook.write_text((ROOT/'scripts/mcp_session.ts').read_text().replace('__SESSION_DIR__', json.dumps(str(path))))
        os.chmod(hook, 0o600)
        return {('WORKBENCH_BROWSER_PROFILE' if record.get('persistent') else 'WORKBENCH_BROWSER_STATE'): str(path / ('profile' if record.get('persistent') else 'storage.json')),
                'WORKBENCH_BROWSER_HOOK': str(hook),
                'WORKBENCH_BROWSER_INIT': str(path / 'session-storage.js')}


def capture(context, path):
    """Capture browser auth, including sessionStorage, without reading password fields."""
    context.storage_state(path=str(path / 'storage.json'), indexed_db=True)
    (path/'cookies.json').write_text(json.dumps(context.cookies()))
    snapshots = {}
    for page in context.pages:
        if page.url.startswith(('http://', 'https://')):
            try:
                data = page.evaluate('({origin: location.origin, entries: Object.entries(sessionStorage)})')
                snapshots[data['origin']] = data['entries']
            except Exception:
                pass
    script = '(() => { const data = ' + json.dumps(snapshots, ensure_ascii=False) + '; for (const [key, value] of data[location.origin] || []) if (sessionStorage.getItem(key) === null) sessionStorage.setItem(key, value); })();'
    (path/'session-storage.json').write_text(json.dumps(snapshots, ensure_ascii=False))
    (path / 'session-storage.js').write_text(script)
    for name in ['storage.json', 'cookies.json', 'session-storage.json', 'session-storage.js']:
        os.chmod(path / name, 0o600)


def browser_context(p, record, headless, launch_args=None):
    path = directory(record['id'])
    if record.get('persistent'):
        context = p.chromium.launch_persistent_context(str(path/'profile'), headless=headless, args=launch_args or [], locale='zh-CN', viewport={'width':1200,'height':850})
    else:
        browser = p.chromium.launch(headless=headless, args=launch_args or [])
        context = browser.new_context(locale='zh-CN', viewport={'width':1200,'height':850},
                                      **({'storage_state':str(path/'storage.json')} if (path/'storage.json').is_file() else {}))
    if (path/'cookies.json').is_file():
        context.clear_cookies()
        context.add_cookies(json.loads((path/'cookies.json').read_text()))
    if (path/'session-storage.js').is_file():
        context.add_init_script(path=str(path/'session-storage.js'))
    return context


def refresh_session(session_id, env):
    """Allow normal navigation/SSO to renew cookies. No password guessing or form submission."""
    result = subprocess.run([str(ROOT/'tools/.venv/bin/python'), str(Path(__file__).resolve()), session_id, '--refresh'],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=80)
    return result.returncode == 0


def browser_refresh(session_id):
    from playwright.sync_api import sync_playwright
    record = read(session_id)
    with sync_playwright() as p:
        context = browser_context(p, record, True)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(record['website'], wait_until='domcontentloaded', timeout=45000)
            page.wait_for_timeout(5000)
            capture(context, directory(session_id))
        finally:
            context.close()


def browser_login(session_id):
    from playwright.sync_api import sync_playwright
    os.umask(0o077)
    record = read(session_id)
    path = directory(session_id)
    try:
        with sync_playwright() as p:
            context = browser_context(p, record, False)
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(record['website'], wait_until='domcontentloaded', timeout=60000)
            page.bring_to_front()
            record.update(status='waiting', message='请在打开的网站窗口输入账号密码；登录成功后，回到工作台保存登录状态')
            write(record)
            deadline = time.monotonic() + 1800
            while context.pages and time.monotonic() < deadline:
                if (path / 'save.request').exists():
                    capture(context, path)
                    record.update(status='saved', message='登录状态已保存，开始开发时会自动使用', saved_at=time.time())
                    write(record)
                    context.close()
                    return
                context.pages[0].wait_for_timeout(300)
            record.update(status='closed', message='登录窗口已关闭或超时，请重新登录')
            write(record)
            context.close()
    except Exception:
        if path.exists():
            record.update(status='failed', message='登录窗口未能完成操作，请重新打开；验证码或验证提示请在网站窗口处理')
            write(record)


def shutdown():
    for session_id, process in list(PROCESSES.items()):
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
    for path in SESSIONS.glob('*/session.json'):
        record = json.loads(path.read_text())
        if record['status'] in ('opening', 'waiting'):
            record.update(status='closed', message='登录窗口已中断，请重新打开网站登录')
            write(record)


if __name__ == '__main__':
    import sys
    if '--refresh' in sys.argv:
        browser_refresh(sys.argv[1])
    else:
        browser_login(sys.argv[1])
