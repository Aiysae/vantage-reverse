"""Real Chromium + Craft regression: saved login, bad layouts, repaired layouts, coverage."""
import json
from pathlib import Path
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from unittest.mock import patch
from playwright.sync_api import sync_playwright
import craft_analysis as craft
import website_login

HTML = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><style>
*{box-sizing:border-box}body{margin:0;background:#eef2f7;color:#172838;font:16px Arial,sans-serif}
header{background:#163d50;color:white;padding:28px 6vw}h1{font-size:32px;margin:0 0 12px}
nav a{color:#95e9cc;margin-right:24px}main{max-width:1000px;margin:32px auto;padding:0 24px}
section{display:grid;grid-template-columns:1fr 1fr;gap:24px}article{background:white;padding:28px;border-radius:16px;box-shadow:0 5px 20px #1231}
button{padding:12px 24px;background:#176b55;color:white;border:0;border-radius:8px}input{padding:12px;width:100%;margin:12px 0;border:1px solid #aaa}
@media(max-width:600px){section{grid-template-columns:1fr}h1{font-size:26px}main{margin:20px auto}}
BAD_STYLE</style><header><h1>Vantage 项目管理</h1><nav><a href="/reference">项目</a><a href="/reference/detail">详情</a></nav></header>
<main><section><article><h2>PAGE_TITLE</h2><p>规划、跟进、交付。</p><input placeholder="搜索项目"><button>查询</button></article><article><h2>本周进度</h2><p>已完成 8 项，共 12 项。</p><button>查看详情</button></article></section></main></html>'''


def main():
    fixed = False
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith('/reference') and 'vantage_fixture=1' not in self.headers.get('Cookie',''):
                self.send_response(401);self.end_headers();return
            if self.path.startswith('/preview') and 'preview_fixture=1' not in self.headers.get('Cookie',''):
                self.send_response(401);self.end_headers();return
            bad = self.path.startswith('/preview') and not fixed
            body = HTML.replace('BAD_STYLE', 'header{background:#912856;padding:80px}main{margin:70px}section{display:block}article{border-radius:0;background:#efb06c;margin:10px}' if bad else '').replace('PAGE_TITLE','项目详情' if self.path.endswith('/detail') else '项目列表').encode()
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    origin=f'http://127.0.0.1:{server.server_port}'
    results={}
    try:
        with tempfile.TemporaryDirectory(prefix='vantage-visual-') as temp:
            root=Path(temp);project=root/'project';project.mkdir();docs=project/'交付资料';docs.mkdir()
            sessions=root/'sessions';sid='f'*32;session=sessions/sid;session.mkdir(parents=True)
            record={'id':sid,'website':origin+'/reference','origin':website_login.origin(origin),'persistent':True,'status':'saved'}
            (session/'session.json').write_text(json.dumps(record))
            with sync_playwright() as p:
                context=p.chromium.launch_persistent_context(str(session/'profile'),headless=True)
                context.add_cookies([{'name':'vantage_fixture','value':'1','url':origin}]);website_login.capture(context,session);context.close()
            task={'id':'a'*32,'website':origin+'/reference','project_path':str(project),'port':server.server_port,'page_limit':2,'login_id':sid}
            (docs/'网站分析.json').write_text(json.dumps({'access_ok':True,'pages':[{'url':origin+'/reference','visited':True},{'url':origin+'/reference/detail','visited':True}]}))
            (docs/craft.MAPPING).write_text(json.dumps({'pages':[{'page_id':1,'target_path':'/preview'},{'page_id':2,'target_path':'/preview/detail'}]}))
            with patch.object(website_login,'SESSIONS',sessions):
                craft.collect(task)
            reference=json.loads((docs/craft.REFERENCE).read_text())
            assert reference['login_reused'] and len(reference['shots'])==6
            results['saved_login_and_six_reference_screenshots']='PASS'
            # Like the verification browser, persist a new preview login into the profile.
            # The older cookies.json intentionally still has only the reference login.
            with sync_playwright() as p:
                context=p.chromium.launch_persistent_context(str(session/'profile'),headless=True)
                context.add_cookies([{'name':'preview_fixture','value':'1','url':origin}])
                private=root/'browser-private';private.mkdir(mode=0o700)
                context.storage_state(path=str(private/'preview-storage.json'));context.close()
            with patch.object(website_login,'SESSIONS',sessions):
                bad=craft.compare(task)
            assert bad['status']=='failed' and all(x['status']=='failed' for x in bad['comparisons'])
            results['detect_six_deliberate_layout_regressions']='PASS'
            fixed=True
            with patch.object(website_login,'SESSIONS',sessions):
                good=craft.compare(task)
            assert good['status']=='passed' and all(x['metrics']['identical'] for x in good['comparisons'])
            results['six_repaired_layouts_identical']='PASS'
            results['preview_session_cookie_survives_browser_close_via_private_snapshot']='PASS'
            (docs/craft.MAPPING).write_text(json.dumps({'pages':[{'page_id':1,'target_path':'/preview'}]}))
            try: craft.compare(task)
            except ValueError: results['missing_page_rejected']='PASS'
            else: raise AssertionError('missing page accepted')
            evidence={'status':'PASS','checks':results,'before':bad,'after':good}
            output=craft.ROOT/'evidence/vantage-visual-regression.json';output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
            # Keep one comparable pair and structural evidence for human review; tests use fixture data only.
            import shutil
            out=craft.ROOT/'evidence/vantage-visual-fixture';out.mkdir(exist_ok=True)
            for p in (docs/'界面证据').iterdir():shutil.copy2(p,out/p.name)
            print(json.dumps({'status':'PASS','checks':results,'evidence':str(output)},ensure_ascii=False))
    finally:server.shutdown()

if __name__=='__main__':main()
