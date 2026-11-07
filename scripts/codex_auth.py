"""Reuse Codex's cache; let the official CLI own refresh and interactive OAuth."""
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
LOCK = threading.RLock()
LOGIN = {}
RETRY_AFTER = 0
LAST_ERROR = ''


class AuthRequired(RuntimeError):
    pass


class AuthUnavailable(RuntimeError):
    pass


def cached_credentials():
    from openhands.sdk.llm.auth.credentials import OAuthCredentials
    try:
        data = json.loads((Path(os.getenv('CODEX_HOME') or Path.home()/'.codex')/'auth.json').read_text())
        if data.get('auth_mode') != 'chatgpt':
            raise ValueError()
        token = data['tokens']['access_token']
        payload = token.split('.')[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + '='*(-len(payload)%4)))
        return OAuthCredentials(vendor='openai', access_token=token, refresh_token='', expires_at=int(claims['exp'])*1000)
    except (OSError, ValueError, KeyError, IndexError):
        raise AuthRequired('请连接 Codex 账号，完成官方登录授权。') from None


def fingerprint():
    try:
        token = cached_credentials().access_token
        if hasattr(token, 'get_secret_value'):
            token = token.get_secret_value()
        return hashlib.sha256(token.encode()).hexdigest()
    except AuthRequired:
        return ''


class CodexRPC:
    def __init__(self):
        binary = shutil.which('codex')
        if not binary:
            binary = next((str(p) for p in [Path.home()/'Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex', Path('/Applications/Codex.app/Contents/Resources/codex')] if p.is_file()), None)
        if not binary:
            raise AuthUnavailable('未找到本机 Codex 登录组件，请启动 Codex 后重试。')
        self.events = queue.Queue()
        self.sequence = 0
        self.process = subprocess.Popen([binary, 'app-server', '--stdio'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, start_new_session=True)
        threading.Thread(target=self._read, daemon=True).start()
        try:
            self.call('initialize', {'clientInfo': {'name':'system_workbench', 'title':'中文系统工作台', 'version':'1.0'}, 'capabilities':None})
            self.send({'method':'initialized'})
        except Exception:
            self.close()
            raise

    def _read(self):
        for line in self.process.stdout:
            try:
                self.events.put(json.loads(line))
            except ValueError:
                pass
        self.events.put(None)

    def send(self, value):
        self.process.stdin.write(json.dumps(value)+'\n')
        self.process.stdin.flush()

    def call(self, method, params):
        self.sequence += 1
        self.send({'id':self.sequence, 'method':method, 'params':params})
        deadline = time.monotonic()+60
        while time.monotonic() < deadline:
            try:
                message = self.events.get(timeout=max(.01, deadline-time.monotonic()))
            except queue.Empty:
                break
            if message is None:
                break
            if message.get('id') != self.sequence:
                continue
            if 'error' in message:
                detail = str(message['error']).lower()
                if any(word in detail for word in ('refresh_token_reused','refresh_token_expired','refresh_token_invalidated','invalid_grant','reauth','sign in again','unauthorized','401')):
                    raise AuthRequired('自动续登未成功，请完成一次 Codex 官方登录授权。')
                raise AuthUnavailable('登录服务暂时未连接，将自动重试；也可点击重新授权。')
            return message.get('result', {})
        raise AuthUnavailable('登录服务响应超时，将自动重试。')

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.process.stdin.close()
        self.process.stdout.close()


def load_codex_credentials(force=False):
    global RETRY_AFTER, LAST_ERROR
    with LOCK:
        cached = None
        try:
            cached = cached_credentials()
            if not force and cached.expires_at > (time.time()+300)*1000:
                return cached
        except AuthRequired:
            pass
        if time.time() < RETRY_AFTER:
            raise AuthUnavailable(LAST_ERROR)
        # Separate runner processes and the task service must not rotate the same token concurrently.
        lockpath = ROOT/'evidence/.codex-refresh.lock'
        lockpath.parent.mkdir(exist_ok=True)
        with lockpath.open('a') as lock:
            os.chmod(lockpath, 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not force:
                try:
                    newer = cached_credentials()
                    if newer.expires_at > (time.time()+300)*1000:
                        return newer
                except AuthRequired:
                    pass
            rpc = None
            try:
                rpc = CodexRPC()
                result = rpc.call('account/read', {'refreshToken':True})
                if not result.get('account') or result['account'].get('type') != 'chatgpt':
                    raise AuthRequired('请完成一次 Codex 官方登录授权。')
                credentials = cached_credentials()
                if credentials.is_expired():
                    raise AuthRequired('登录状态已过期，请完成一次 Codex 官方登录授权。')
                RETRY_AFTER, LAST_ERROR = 0, ''
                return credentials
            except (AuthRequired, AuthUnavailable, OSError) as exc:
                LAST_ERROR = str(exc) if isinstance(exc, (AuthRequired, AuthUnavailable)) else '登录服务暂时未连接，将自动重试。'
                RETRY_AFTER = time.time()+300
                raise AuthUnavailable(LAST_ERROR) from None
            finally:
                if rpc:
                    rpc.close()


def start_login():
    global LOGIN
    with LOCK:
        if LOGIN.get('status') == 'waiting':
            return dict(LOGIN)
        rpc = CodexRPC()
        try:
            result = rpc.call('account/login/start', {'type':'chatgpt'})
            from urllib.parse import urlsplit
            if urlsplit(result.get('authUrl','')).hostname != 'auth.openai.com':
                raise AuthUnavailable('登录服务没有返回有效的官方授权链接，请重试。')
        except Exception:
            rpc.close()
            raise
        LOGIN = {'status':'waiting', 'url':result['authUrl'], 'message':'请在官方页面完成授权，完成后开发任务自动接续。'}
        threading.Thread(target=_wait_login, args=(rpc,result['loginId']), daemon=True).start()
        return dict(LOGIN)


def _wait_login(rpc, login_id):
    global LOGIN, RETRY_AFTER
    deadline = time.monotonic()+900
    success = False
    try:
        while time.monotonic() < deadline:
            try:
                message = rpc.events.get(timeout=min(5, max(.01,deadline-time.monotonic())))
            except queue.Empty:
                continue
            if message is None:
                break
            if message.get('method') == 'account/login/completed' and message.get('params',{}).get('loginId') == login_id:
                success = message['params'].get('success') is True
                break
    finally:
        rpc.close()
        with LOCK:
            RETRY_AFTER = 0
            LOGIN = {'status':'completed' if success else 'failed', 'message':'登录已更新，等待任务自动接续。' if success else '授权未完成或已超时，请重新打开官方登录。'}


def status():
    try:
        load_codex_credentials()
        return {'configured':True, 'message':'已连接当前 Codex 账号 · 登录自动续期已开启', 'login':dict(LOGIN)}
    except (AuthRequired, AuthUnavailable):
        return {'configured':False, 'message':LAST_ERROR or '正在等待 Codex 登录授权', 'login':dict(LOGIN)}


def create_codex_llm(model):
    from openhands.sdk.llm.auth.openai import OpenAISubscriptionAuth
    return OpenAISubscriptionAuth().create_llm(model=model, credentials=load_codex_credentials())
