"""Disposable local login site for end-to-end testing; no real account data."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

TOKEN='fixture-cookie-9c768d31'
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        data=parse_qs(self.rfile.read(int(self.headers.get('Content-Length','0'))).decode())
        if self.path=='/login' and data.get('username')==['演示用户'] and data.get('password')==['demo-only-123']:
            self.send_response(303);self.send_header('Set-Cookie',f'fixture_session={TOKEN}; HttpOnly; SameSite=Lax; Path=/');self.send_header('Location','/private');self.end_headers()
        else:self.send_error(403)
    def do_GET(self):
        authenticated=f'fixture_session={TOKEN}' in self.headers.get('Cookie','')
        if self.path=='/private' and authenticated:
            page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>已登录的演示网站</title><h1>内部订单管理</h1><p id="gate">正在读取登录状态…</p><script>
const entered = sessionStorage.getItem('fixture-session') === 'session-ready';
if (!entered) sessionStorage.setItem('fixture-session','session-ready');
localStorage.setItem('fixture-local','local-ready');
const db=indexedDB.open('fixture-auth',1);db.onupgradeneeded=()=>db.result.createObjectStore('auth');db.onsuccess=()=>{const tx=db.result.transaction('auth','readwrite');tx.objectStore('auth').put('idb-ready','proof');db.result.close();};
document.getElementById('gate').textContent='登录后专属功能：订单审核、客户跟进、库存查询。验收标记：玉竹-6729';
</script></html>'''
        elif self.path=='/private':
            self.send_response(303);self.send_header('Location','/');self.end_headers();return
        elif authenticated:
            self.send_response(303);self.send_header('Location','/private');self.end_headers();return
        else:
            page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>网站登录入口验收</title><style>body{font:20px sans-serif;margin:60px}input,button{font:inherit;margin:12px;padding:8px}</style><h1>演示网站登录</h1><p>这是本机测试页面，使用演示账号，不涉及真实网站。</p><form action="/login" method="post"><label>账号<input name="username" autocomplete="off"></label><br><label>密码<input type="password" name="password" autocomplete="off"></label><br><button>登录演示网站</button></form></html>'''
        body=page.encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
if __name__=='__main__':ThreadingHTTPServer(('127.0.0.1',18782),Handler).serve_forever()
