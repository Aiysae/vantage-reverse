"""Craft's capture and pixel tools, sharing the existing website login and task lifecycle."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import time
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright
import website_login
import workflow
from rea_analysis import safe_url

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'tools/craft-anything/0.5.0/craft-anything-cli-0.5.0-macos-universal/craft-anything-cli'
WIDTHS = (390, 768, 1440)
HEIGHT = 900
MIN_SIMILARITY = 0.85
REFERENCE = '界面参考.json'
COMPARISON = '界面对照.json'
SUMMARY = '界面对照.md'
MAPPING = '视觉映射.json'

# Structural values only; no HTML, field values, customer text or browser storage.
LAYOUT_JS = '''() => {
  const nodes = [...document.querySelectorAll('body,header,nav,main,aside,section,article,footer,h1,h2,button,input,table,[role="dialog"]')];
  return {scroll_height: document.documentElement.scrollHeight, landmarks: nodes.slice(0,120).map(el => {
    const s=getComputedStyle(el), r=el.getBoundingClientRect();
    return {tag:el.tagName.toLowerCase(), role:el.getAttribute('role'),
      rect:[r.x,r.y,r.width,r.height].map(Math.round), display:s.display,
      font:s.fontFamily, font_size:s.fontSize, weight:s.fontWeight,
      color:s.color, background:s.backgroundColor, gap:s.gap,
      padding:s.padding, margin:s.margin, radius:s.borderRadius};
  })};
}'''


def status():
    return {'installed': CLI.is_file(), 'version': '0.5.0' if CLI.is_file() else None,
            'widths': list(WIDTHS), 'minimum_similarity': MIN_SIMILARITY,
            'message': '界面对照已就绪：手机、平板、桌面三种宽度' if CLI.is_file() else '界面对照工具尚未安装'}


def cli(command, params):
    # Bound each child; it also inherits the task worker's process group for stop/timeouts.
    result = subprocess.run([str(CLI), '--deep', command, '--json', json.dumps(params)],
                            capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError(f'Craft {command} 执行失败（{result.returncode}），请检查页面与工具连接')
    data = json.loads(result.stdout)
    if 'result' not in data or 'error' in data:
        raise ValueError(f'Craft {command} 返回格式不完整')
    return data


def write_report(project, name, data):
    docs = project / workflow.DOCS
    docs.mkdir(exist_ok=True)
    path = docs / name
    if path.is_symlink() or not path.resolve().is_relative_to(project.resolve()):
        raise ValueError('交付资料路径无效')
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    temp.replace(path)


def progress(task, message):
    with (Path(task['project_path']).parent / 'progress.log').open('a') as stream:
        stream.write('Vantage 界面对照：' + message + '\n')


def local_file(project, relative):
    path = project / relative
    if path.is_symlink() or not path.resolve().is_relative_to(project.resolve()) or not path.is_file():
        raise ValueError('截图文件缺失或路径不在项目内')
    return path


def capture(task, items, prefix, use_source_session=False):
    project = Path(task['project_path']).resolve()
    folder = project / workflow.DOCS / '界面证据'
    if folder.is_symlink() or not folder.resolve().is_relative_to(project):
        raise ValueError('截图目录无效')
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    args = [f'--remote-debugging-port={port}', '--remote-debugging-address=127.0.0.1']
    results = []
    with sync_playwright() as p:
        record = website_login.read(task['login_id']) if use_source_session and task.get('login_id') else None
        browser = None
        if record:
            context = website_login.browser_context(p, record, True, args)
        else:
            browser = p.chromium.launch(headless=True, args=args)
            options = {}
            snapshot = project.parent / 'browser-private/preview-storage.json'
            if not use_source_session and snapshot.is_file():
                if snapshot.is_symlink() or not snapshot.resolve().is_relative_to(project.parent):
                    raise ValueError('成品会话路径无效')
                state = json.loads(snapshot.read_text())
                target = urlsplit(items[0]['url'])
                local_origin = f'{target.scheme}://{target.netloc}'
                # Keep only this preview's origin and local cookies; never copy source-site credentials into project evidence.
                state = {'cookies':[c for c in state.get('cookies',[]) if c.get('domain','').lstrip('.') == target.hostname],
                         'origins':[o for o in state.get('origins',[]) if o.get('origin') == local_origin]}
                snapshot.write_text(json.dumps(state))
                os.chmod(snapshot, 0o600)
                options['storage_state'] = state
            context = browser.new_context(locale='zh-CN', reduced_motion='reduce', **options)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.emulate_media(reduced_motion='reduce', color_scheme='light')
            for index, item in enumerate(items):
                url = item['url']
                page.set_viewport_size({'width': WIDTHS[-1], 'height': HEIGHT})
                response = page.goto(url, wait_until='domcontentloaded', timeout=45000)
                page.wait_for_timeout(1200)
                if website_login.origin(page.url) != website_login.origin(url) or (response and response.status in (401,403)) or page.locator('input[type=password]').count():
                    if use_source_session:
                        write_report(project, '需要协助.json', {'reason':'login','message':'界面采集时网站登录已失效，请恢复网站登录。'})
                        workflow.check_input(task)
                    raise ValueError('成品页面跳转到登录或权限页面，请修复预览访问')
                if not response or response.status >= 400:
                    raise ValueError(f'界面采集页面返回错误：{safe_url(url)}')
                page.evaluate('() => document.fonts.ready')
                # Neutralize animation and mask obvious sensitive fields in locally retained screenshots.
                page.add_style_tag(content='*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important} input[type=password],[data-private],[data-sensitive]{visibility:hidden!important}')
                cdp = context.new_cdp_session(page)
                target = cdp.send('Target.getTargetInfo')['targetInfo']['targetId']
                cdp.detach()
                for width in WIDTHS:
                    page.set_viewport_size({'width': width, 'height': HEIGHT})
                    page.evaluate('scrollTo(0,0)')
                    page.wait_for_timeout(250)
                    evidence = cli('web-page-screenshot-take', {'cdp_endpoint':f'http://127.0.0.1:{port}', 'target_id':target})
                    screenshot = evidence['result']['screenshot']
                    raw = base64.b64decode(screenshot['base64'], validate=False)
                    if hashlib.sha256(raw).hexdigest() != screenshot['sha256']:
                        raise ValueError('Craft 截图校验失败')
                    path = folder / f'{prefix}-{index+1}-{width}.png'
                    if path.is_symlink():
                        raise ValueError('截图路径无效')
                    path.write_bytes(raw)
                    layout = page.evaluate(LAYOUT_JS)
                    layout_path = path.with_suffix('.layout.json')
                    if layout_path.is_symlink():
                        raise ValueError('布局证据路径无效')
                    layout_path.write_text(json.dumps(layout, ensure_ascii=False, indent=2))
                    results.append({'page':item.get('page_id',index+1), 'url':safe_url(url), 'source_url':item.get('source_url',safe_url(url)),
                                    'width':width, 'height':HEIGHT, 'screenshot':str(path.relative_to(project)),
                                    'sha256':screenshot['sha256'], 'evidence_id':evidence['id'],
                                    'layout_file':str(layout_path.relative_to(project)), 'scroll_height':layout['scroll_height']})
                progress(task, f'{prefix} {index+1}/{len(items)} 页完成，三种宽度截图已保存。')
        finally:
            if record:
                website_login.capture(context, website_login.directory(record['id']))
            context.close()
            if browser:
                browser.close()
    return results


def collect(task):
    workflow.check_input(task)
    project = Path(task['project_path'])
    analysis = json.loads(workflow.artifact(project, '网站分析.json'))
    if analysis.get('access_ok') is not True:
        return
    origin = website_login.origin(task['website'])
    urls = list(dict.fromkeys(p['url'] for p in analysis.get('pages', []) if p.get('visited') is True
                             and p.get('url') and website_login.origin(p['url']) == origin))[:task.get('page_limit',40)]
    if not urls:
        raise ValueError('界面采集尚无已访问的同源页面')
    shots = capture(task, [{'url':u} for u in urls], 'reference', True)
    write_report(project, REFERENCE, {'status':'passed', 'engine':'Craft Anything 0.5.0 + Playwright',
        'captured_at':time.time(), 'login_reused':bool(task.get('login_id')), 'widths':list(WIDTHS), 'shots':shots,
        'limitations':['每页只采集初始状态顶部 900 像素；滚动区、菜单、弹窗及特殊状态仍需浏览器业务验收。',
                       '截图保留在本机项目；布局数据由 Playwright 采集，截图与像素指标由 Craft 生成。']})


def compare(task):
    project = Path(task['project_path'])
    reference = json.loads(workflow.artifact(project, REFERENCE))
    mapping = json.loads(workflow.artifact(project, MAPPING))
    expected = set(s['page'] for s in reference['shots'])
    pairs = mapping.get('pages', [])
    if len(pairs) != len(expected) or {p.get('page_id') for p in pairs} != expected:
        raise ValueError('视觉映射必须逐一覆盖界面参考中的所有 page 编号，不得遗漏页面')
    items = []
    for pair in pairs:
        path = pair.get('target_path', '')
        parsed = urlsplit(path)
        if not path.startswith('/') or path.startswith('//') or parsed.scheme or parsed.netloc or '\\' in path:
            raise ValueError('target_path 必须是本项目内以 / 开头的路径')
        items.append({'url':f"http://127.0.0.1:{task['port']}" + path, 'page_id':pair['page_id'], 'source_url':next(s['source_url'] for s in reference['shots'] if s['page']==pair['page_id'])})
    actual = capture(task, items, 'preview')
    source = {(s['page'],s['width']):s for s in reference['shots']}
    comparisons = []
    for shot in actual:
        before = source[(shot['page'],shot['width'])]
        result = cli('web-pixels-compare', {'before':{'path':str(local_file(project,before['screenshot']))},
                     'after':{'path':str(local_file(project,shot['screenshot']))}, 'tolerance':16, 'common_area':True})
        metrics = result['result']
        passed = metrics.get('comparable') is True and metrics.get('sizes',{}).get('before') == metrics.get('sizes',{}).get('after') and all(metrics.get(k,0) >= MIN_SIMILARITY for k in ('layout_similarity','perceptual_similarity'))
        comparisons.append({'source_url':shot['source_url'], 'width':shot['width'],
                            'reference':before['screenshot'], 'preview':shot['screenshot'],
                            'evidence_id':result['id'], 'status':'passed' if passed else 'failed', 'metrics':metrics})
    report = {'status':'passed' if comparisons and all(c['status']=='passed' for c in comparisons) else 'failed',
              'engine':'Craft Anything 0.5.0', 'captured_at':time.time(), 'minimum_similarity':MIN_SIMILARITY,
              'comparisons':comparisons, 'limitations':reference['limitations'] + ['相似度只辅助外观检查，不替代功能、数据、交互及人工/Agent 视觉复核。动态内容和不同示例数据可能影响分数。']}
    write_report(project, COMPARISON, report)
    lines = ['# Vantage 逆向工具 · 界面对照', f"结果：{report['status']}；布局与感知相似度门槛均为 {MIN_SIMILARITY:.0%}。", '', '| 页面 | 宽度 | 布局 | 感知 | 差异像素比例 | 结果 |', '|---|---:|---:|---:|---:|---|']
    for c in comparisons:
        m=c['metrics']
        lines.append(f"| {c['source_url']} | {c['width']} | {m.get('layout_similarity',0):.1%} | {m.get('perceptual_similarity',0):.1%} | {m.get('difference_fraction',0):.1%} | {c['status']} |")
    lines += ['', '逐项截图、证据编号及差异区域见界面对照.json；读取截图后修复具体差异，不得通过改参考图或调低门槛使任务通过。', '', *['- '+s for s in report['limitations']]]
    summary_path = project/workflow.DOCS/SUMMARY
    if summary_path.is_symlink():
        raise ValueError('对照报告路径无效')
    summary_path.write_text('\n'.join(lines))
    progress(task, f"{len(comparisons)} 组对照完成，结果 {report['status']}。")
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['collect','compare'])
    parser.add_argument('--task', required=True)
    args = parser.parse_args()
    task = json.loads(Path(args.task).read_text())
    result = collect(task) if args.operation == 'collect' else compare(task)
    print(json.dumps({'status':(result or {}).get('status','passed')}, ensure_ascii=False))
