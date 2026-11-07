"""Disposable authenticated two-page notes reference for workflow acceptance."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):
  data=parse_qs(self.rfile.read(int(self.headers.get('Content-Length','0'))).decode())
  if self.path=='/login' and data.get('username')==['演示用户'] and data.get('password')==['demo-only-123']:
   self.send_response(303);self.send_header('Set-Cookie','workflow_demo=local-fixture-only; HttpOnly; SameSite=Lax; Path=/');self.send_header('Location','/notes');self.end_headers()
  else:self.send_error(403)
 def do_GET(self):
  auth='workflow_demo=local-fixture-only' in self.headers.get('Cookie','')
  if self.path=='/favicon.ico':self.send_response(204);self.end_headers();return
  if not auth:
   body='<h1>演示笔记系统登录</h1><form action="/login" method="post"><label>账号<input name="username"></label><label>密码<input type="password" name="password"></label><button>登录演示网站</button></form>'
  elif self.path=='/summary':
   body='<nav><a href="/notes">笔记列表</a> <a href="/summary">统计概览</a></nav><h1>统计概览</h1><p>总笔记：0</p><p>已归档：0</p><p>未归档：0</p><p>统计来自笔记数据库；请在重建项目中实现真实统计。</p>'
  else:
   body='<nav><a href="/notes">笔记列表</a> <a href="/summary">统计概览</a></nav><h1>笔记列表</h1><p>验收标记：青竹-8492</p><label>搜索笔记<input placeholder="按标题搜索"></label><h2>新增或编辑笔记</h2><label>标题<input required maxlength="100"></label><label>正文<textarea maxlength="2000"></textarea></label><button type="button">保存笔记</button><p>标题为必填，最多 100 字，正文最多 2000 字。列表每条可编辑、归档/取消归档、删除。</p><p>暂无笔记。这是只读参考网站，按钮用于展示界面；新建系统需要实际实现这些操作。</p>'
  html=('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>演示笔记系统</title><style>body{font:18px sans-serif;margin:40px}label{display:block;margin:15px 0}input,textarea,button{padding:8px;margin:8px}</style>'+body+'</html>').encode()
  self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(html)));self.end_headers();self.wfile.write(html)
if __name__=='__main__':ThreadingHTTPServer(('127.0.0.1',18782),Handler).serve_forever()
