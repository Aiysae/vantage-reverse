"""REA's real CLI supplements visited pages, using the workbench's private login profile."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
from urllib.parse import urlsplit, urlunsplit

from playwright.sync_api import sync_playwright
import website_login
import workflow

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'tools/node_modules/rea-agents'
CLI = PACKAGE / 'scripts/rea.mjs'
REPORT = 'REA深度分析.json'
SUMMARY = 'REA深度分析.md'


def status():
    installed = CLI.is_file()
    version = json.loads((PACKAGE/'package.json').read_text())['version'] if installed else None
    return {'installed': installed, 'version': version,
            'message': f'REA {version} 已就绪，复用网站登录后自动补充网络与脚本分析' if installed else 'REA 尚未安装'}


def safe_url(value):
    """Report endpoints without query values, fragments or URL credentials."""
    try:
        url = urlsplit(value or '')
        host = url.hostname or ''
        if ':' in host:
            host = '['+host+']'
        return urlunsplit((url.scheme, host+(f':{url.port}' if url.port else ''), url.path, '', ''))
    except ValueError:
        return '[网址已省略]'


def cli(command, endpoint, target):
    args = [shutil.which('node'), str(CLI), command, endpoint, target,
            '--observation-ms', '500', '--format', 'json']
    if command == 'inspect-web-page':
        args += ['--include-json-body-shapes']
    # Raw tool data stays in anonymous temporary files; only structural evidence is exported.
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(args, stdout=output, stderr=errors)
        try:
            process.wait(timeout=90)
            output.seek(0)
            data = json.load(output)
            if process.returncode or 'error' in data:
                raise RuntimeError('REA 分析失败，请查看页面加载和浏览器连接后自动重试')
            # Incur versions may wrap CLI data, while the canonical evidence is unchanged.
            if 'normalized_result' not in data and isinstance(data.get('data'), dict):
                data = data['data']
            if not isinstance(data.get('normalized_result'), dict):
                raise ValueError('REA 返回格式与固定版本不匹配')
            return data
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()


def project_page(evidence, bundle):
    inspection = evidence['normalized_result']
    inspection = inspection.get('inspection', inspection)
    analysis = bundle['normalized_result']
    analysis = analysis.get('analysis', analysis)
    observations = analysis.get('observations', {})
    requests = []
    for request in inspection.get('network', {}).get('requests', []):
        item = {key: request[key] for key in ('method', 'status', 'status_code', 'resource_type', 'mime_type', 'response_body_shape', 'json_body_shape') if key in request}
        item['url'] = safe_url(request.get('url'))
        item['source'] = 'REA'
        requests.append(item)
    scripts = inspection.get('scripts', {}).get('items', [])
    # Bundle capture includes script metadata even if passive inspection didn't include sources.
    capture = analysis.get('capture', {})
    return {
        'url': safe_url(inspection.get('target', {}).get('url') or capture.get('target_url')),
        'evidence_id': evidence.get('evidence_id'), 'bundle_evidence_id': bundle.get('evidence_id'),
        'captured_at': inspection.get('capture_window', {}).get('ended_at'),
        'dom_nodes': inspection.get('dom', {}).get('total_nodes', 0),
        'requests': requests,
        'scripts_observed': capture.get('scripts_observed', len(scripts)),
        'scripts_analyzed': capture.get('scripts_analyzed', 0),
        'scripts': [{'url': safe_url(s.get('url')), 'source_map_url': safe_url(s.get('source_map_url')),
                     'language': s.get('language'), 'length': s.get('length')} for s in scripts],
        'static_endpoints': [{'value': safe_url(x.get('value')), 'mechanism': x.get('mechanism'), 'location': x.get('location')} for x in observations.get('endpoints', [])],
        'static_routes': [{'value': safe_url(x.get('value')), 'mechanism': x.get('mechanism'), 'location': x.get('location')} for x in observations.get('routes', [])],
        'module_edges': observations.get('chunks', {}).get('edges', []),
        'completeness': analysis.get('completeness'),
        'limitations': list(dict.fromkeys([*inspection.get('limitations', []), *analysis.get('limitations', [])])),
    }


def collect(task):
    project = Path(task['project_path'])
    directory = project.parent
    analysis = json.loads(workflow.artifact(project, '网站分析.json'))
    workflow.check_input(task)
    if analysis.get('access_ok') is not True:
        return  # Let the existing login recovery gate handle this stage.
    target_origin = website_login.origin(task['website'])
    urls, skipped = [], []
    for record in analysis.get('pages', []):
        url = record.get('url', '')
        try:
            allowed = website_login.origin(url) == target_origin
        except ValueError:
            allowed = False
        if record.get('visited') is True and allowed and url not in urls:
            urls.append(url)
        elif not allowed:
            skipped.append({'url': safe_url(url), 'reason': '仅分析参考网站同源页面'})
    urls = urls[:task.get('page_limit', 40)]
    if not urls:
        raise ValueError('REA 尚无可复核的同源已访问页面')
    def progress(message):
        with (directory/'progress.log').open('a') as stream:
            stream.write('REA：'+message+'\n')
    progress('复用已保存的网站会话，开始逐页深度分析。')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    endpoint = f'http://127.0.0.1:{port}'
    launch_args = [f'--remote-debugging-port={port}', '--remote-debugging-address=127.0.0.1']
    pages = []
    with sync_playwright() as p:
        record = website_login.read(task['login_id']) if task.get('login_id') else None
        browser = None
        if record:
            context = website_login.browser_context(p, record, True, launch_args)
        else:
            browser = p.chromium.launch(headless=True, args=launch_args)
            context = browser.new_context(locale='zh-CN')
        try:
            page = context.pages[0] if context.pages else context.new_page()
            observed = []
            def on_response(response):
                if website_login.origin(response.url) == target_origin:
                    observed.append({'url':safe_url(response.url), 'method':response.request.method,
                                     'status':response.status, 'resource_type':response.request.resource_type,
                                     'source':'Playwright'})
            page.on('response', on_response)
            for index, url in enumerate(urls):
                observed.clear()
                response = page.goto(url, wait_until='domcontentloaded', timeout=45000)
                page.wait_for_timeout(1800)  # Allow the site's normal session renewal to complete.
                if website_login.origin(page.url) != target_origin or page.locator('input[type=password]').count() or (response and response.status in (401, 403)):
                    (project/workflow.DOCS/'需要协助.json').write_text(json.dumps({'reason':'login','message':'REA 复核时网站登录已失效，请恢复网站登录。'}, ensure_ascii=False))
                    return
                cdp = context.new_cdp_session(page)
                target = cdp.send('Target.getTargetInfo')['targetInfo']['targetId']
                cdp.detach()
                evidence = cli('inspect-web-page', endpoint, target)
                bundle = cli('analyze-web-bundle', endpoint, target)
                item = project_page(evidence, bundle)
                item['requests'] = [*observed, *item['requests']]
                item['url'] = safe_url(url)
                pages.append(item)
                progress(f"{index+1}/{len(urls)} 页完成：记录 {len(item['requests'])} 个请求、分析 {item['scripts_analyzed']} 个脚本。")
        finally:
            if record:
                website_login.capture(context, website_login.directory(record['id']))
            context.close()
            if browser:
                browser.close()
    requests = {(r.get('method'), r['url']) for page in pages for r in page['requests']}
    report = {'status':'passed','version':status()['version'],'completed_at':time.time(),
              'login_reused':bool(record), 'pages':pages, 'skipped':skipped,
              'counts':{'pages':len(pages),'unique_requests':len(requests),
                        'scripts_analyzed':sum(page['scripts_analyzed'] for page in pages),
                        'static_endpoints':len({x['value'] for page in pages for x in page['static_endpoints']})},
              'limitations':['只复核已访问的同源页面及加载期间的请求；未自动提交业务表单。',
                             '加载请求由 Playwright 从导航前开始记录；REA 补充稳定页面和脚本静态分析，请求逐条标记来源。',
                             '静态脚本中的接口和路由是代码证据，不代表已调用成功；运行时请求单独列出。',
                             '不包含 Cookie、请求头、响应原文、浏览器存储值和原站后台源码；source map 本轮未额外获取。',
                             '功能增加多少需逐项对照原分析，证据条数不等于新增功能数。']}
    docs = project/workflow.DOCS
    (docs/REPORT).write_text(json.dumps(report, ensure_ascii=False, indent=2))
    lines = ['# REA 深度分析', f"版本：{report['version']}；{'复用已保存登录' if record else '公开页面'}。",
             f"已复核 {len(pages)} 页，记录 {len(requests)} 个不同请求，分析 {report['counts']['scripts_analyzed']} 个脚本。"]
    for page in pages:
        lines += [f"\n## {page['url']}",f"证据编号：{page['evidence_id']}；脚本分析编号：{page['bundle_evidence_id']}",
                  f"DOM 节点：{page['dom_nodes']}；观察脚本：{page['scripts_observed']}；成功分析：{page['scripts_analyzed']}。"]
        lines += [f"- 请求：{r.get('method','')} {r['url']}（状态 {r.get('status',r.get('status_code','未提供'))}）" for r in page['requests']]
        lines += [f"- 静态接口：{r['value']}（{r['mechanism']}）" for r in page['static_endpoints']]
    lines += ['\n## 覆盖边界', *['- '+x for x in report['limitations']]]
    (docs/SUMMARY).write_text('\n'.join(lines))
    progress('深度分析已保存，后续设计与开发将自动读取证据。')
