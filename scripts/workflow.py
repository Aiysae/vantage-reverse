"""Four sequential OpenHands stages with file and deployment completion checks."""
import json
from pathlib import Path
import subprocess
import httpx

STAGES = [
    ('analysis', '登录检查与网站分析'),
    ('design', '功能与数据库设计'),
    ('build', '前后端与数据库开发'),
    ('verify', '测试、部署与验收'),
]
DOCS = '交付资料'
FILES = {
    'analysis': ['网站分析.json', '网站分析.md'],
    'design': ['实现方案.md'],
    'build': ['开发说明.md'],
    'verify': ['验收结果.json', '验收报告.md'],
}


class NeedsInput(ValueError):
    pass


class LoginExpired(NeedsInput):
    def __init__(self, message, kind="codex"):
        super().__init__(message)
        self.kind = kind


class QuotaExceeded(NeedsInput):
    def __init__(self, message, reset_at=None):
        super().__init__(message)
        self.reset_at = reset_at


def stages():
    return [{'id': key, 'label': label, 'status': 'pending', 'message': ''} for key, label in STAGES]


def stage_prompt(task, stage):
    limit = task.get('page_limit', 40)
    shared = f'''
这是 Vantage 逆向工具自动流程的一个阶段。只执行下述当前阶段；前序交付资料在 {DOCS}/，必须先阅读现有项目和前序资料。
资料使用简体中文，JSON 使用有效 JSON，不要写 Markdown 围栏。不记录真实客户记录、凭据或网页中的个人信息，只总结页面结构与业务规则。
如果确实需要用户操作（重新登录、验证码、服务密钥或账号额度），写 {DOCS}/需要协助.json，结构为 {{"reason":"login 或 captcha 或 credentials 或 quota","message":"用户需要做的具体操作，不含任何密钥"}} 并结束。普通代码错误、测试失败、部署报错或时间不够不属于需要用户协助，应继续修复或保留具体错误供下一轮接续。
不要臆测已执行的步骤或测试通过。阻碍、推断及未覆盖内容必须明确记录。不得用静态假按钮、内存数组或模拟 API 冒充完整系统。
'''
    instructions = {
        'analysis': f'''当前阶段：登录检查与网站分析。此阶段不开发或部署。
1. 有参考网址时，用配置好的浏览器访问。先等待页面正常加载，让网站自动续期或通过已有单点登录恢复；不填写未知密码、不反复提交登录。检查登录状态，若仍显示登录、验证码或权限不足，写下方 JSON 的 access_ok=false、blockers=中文具体原因，并结束本阶段等待用户处理。没有网址时，依据需求分析，access_ok=true、pages=[]。
2. 登录成功后，实际逐一访问站内导航、菜单、标签、详情入口和表单界面，最多 {limit} 个不同功能页面。对同模板数据详情只检查代表页面；排除退出登录、下载大文件及外站链接。滚动和打开只读菜单以发现懒加载入口。不要提交增删改、付款、发送消息等会改变原站数据的表单或按钮。
3. 记录页面网址/标题、模块、按钮、字段、筛选、表单校验、关联跳转和业务流程。区分实际观察与推断。分析停在发现的入口已覆盖、达到上限、登录失效或遇到访问阻碍之一；未访问的入口列入 unvisited，说明原因。不要称已经覆盖所有隐藏功能。发现与需求无关页面也记录排除原因。
4. 生成 {DOCS}/网站分析.json，结构必须为：
{{"access_ok":true,"blockers":[],"pages":[{{"url":"实际网址","title":"标题","visited":true,"features":["实际可见功能"]}}],"unvisited":[{{"url":"入口","reason":"原因"}}],"flows":[{{"name":"流程","steps":["步骤"]}}],"assumptions":["推断、未知权限或未知后台规则"]}}
同时生成 {DOCS}/网站分析.md，列出观察到的功能、覆盖情况、需求对应关系和缺项。失败时也要生成两份资料，并说明登录等具体障碍。''',
        'design': f'''当前阶段：功能与数据库设计。此阶段不编写应用代码或部署。
读取网站分析和用户需求，生成 {DOCS}/实现方案.md：逐项列出要实现的页面和功能、前后端 API、数据实体/字段/关系、权限与校验规则、各功能的验收方法。后台源码不可见的规则明确为实现假设；外部支付、短信等缺少服务凭据时列为待接入，不伪造成功。
优先使用已有项目和本机镜像，选择最小足够技术栈。新建普通系统默认采用 Python HTTP 后端 + SQLite 持久数据库 + 中文网页，复杂需求再使用现有 FastAPI/PostgreSQL 等。数据库必须持久化到项目专属容器卷。方案应覆盖需求及已观察到的目标功能，说明依赖和未覆盖部分。''',
        'build': f'''当前阶段：前后端与数据库开发。
按实现方案实际编写中文前端、真实后端 API、持久数据库表和必要的迁移/初始化；完成需求覆盖的业务操作与校验，不能只交付静态页面。已有项目增量修改并保留已有数据。
创建实际接口及数据库测试。提供 compose.yml、Dockerfile（需要构建时）、README.md 和 {DOCS}/开发说明.md，说明功能与源文件对应、真实实现和未完成项。本阶段做必要单元或接口检查，但最终部署和重启持久化验收由下一阶段执行。不要自动导入目标网站的真实业务记录；验收只用明确的演示数据。''',
        'verify': f'''当前阶段：测试、部署与验收。
使用 docker compose -p dev-{task['id']} -f compose.yml 构建启动当前项目，入口必须为 http://127.0.0.1:{task['port']}/，数据库使用独立持久卷。不要操作别的项目。
实际验证浏览器可用、前端调用真实后端、API 校验和错误情况、数据库增删改查，以及写入测试记录后重启本项目容器、确认记录仍存在。测试只使用本项目演示数据，验证后清除测试记录。浏览器检查主要业务流程和手机宽度；发现问题就修复并重测。部署成功后保持容器运行。
生成 {DOCS}/验收结果.json，结构：
{{"status":"passed 或 failed","checks":[{{"id":"frontend","status":"passed 或 failed","evidence":"实际执行及结果"}},{{"id":"api","status":"passed","evidence":"实际接口结果"}},{{"id":"database","status":"passed","evidence":"实际数据库读写结果"}},{{"id":"crud","status":"passed","evidence":"业务增删改查结果"}},{{"id":"persistence","status":"passed","evidence":"重启前后记录一致的证据"}}],"remaining":[],"preview_url":"http://127.0.0.1:{task['port']}/"}}
有失败项或未完成的需求就 status=failed，remaining 明确列出。未分析的页面和外部服务待接入也需要在报告说明；不要虚构已经完整还原原站。
同时生成 {DOCS}/验收报告.md，列出功能覆盖、测试证据、部署地址、未实现/未覆盖项及原因。最后面向用户简短报告实际结果。''',
    }
    if task.get('rea_enabled'):
        if stage == 'analysis':
            shared += '\n本阶段结束后工作台会自动运行 REA，复用同一保存会话复核你实际访问的页面；请准确填写 pages，不要虚构 REA 结果或自己安装工具。\n'
        else:
            shared += '\n已启用 REA。必须读取交付资料/REA深度分析.json 和 REA深度分析.md，将实际网络请求、静态脚本发现与页面观察结合；静态发现与运行时证据分开标记，未观察到不等于不存在。设计和验收报告说明 REA 相比页面分析补充了什么，证据数不等于新增功能数。\n'
    if task.get('visual_enabled'):
        if stage == 'analysis':
            shared += '\n阶段结束后自动采集已访问页面的 390/768/1440 像素截图；请完整填写 pages，不自行制作参考图。\n'
        else:
            shared += '\n已启用界面对照。读取交付资料/界面参考.json 及其中 layout_file、screenshot 路径；必须查看实际截图，按三种宽度复现参考页的布局、颜色、字体、间距及交互。参考图与结构证据不得修改。\n'
        if stage == 'verify':
            adapter = Path(__file__).resolve().parent / 'craft_analysis.py'
            python = adapter.parent.parent / 'tools/.venv/bin/python'
            task_path = Path(task['project_path']).parent / 'task.json'
            shared += f'''\n界面验收额外要求：生成交付资料/视觉映射.json，结构 {{"pages":[{{"page_id":1,"target_path":"/本地对应页面"}}]}}，逐一覆盖界面参考中的所有 page 编号。
部署并在浏览器完成成品的必要登录后，用 browser_storage_state 将当前会话保存到 {str(task_path.parent/'browser-private/preview-storage.json')!r}。仅通过浏览器工具保存，不读取或打印其内容；该任务私有文件位于项目下载范围外。
然后运行 {str(python)!r} {str(adapter)!r} compare --task {str(task_path)!r}。这仅调用现成采集器，勿编辑工作台文件。
读取界面对照.json 和截图，修正明显视觉差异并重新对照，最多 3 轮。布局和感知相似度均至少 0.85；不调低门槛、不改参考图、不隐藏页面来通过。
验收报告记录三种宽度、菜单/弹窗/表单等实测状态、尚未覆盖部分。分数不替代功能验收。阶段结束后后台重新截图核验，未过会进入现有自动修复流程。\n'''
    return shared + instructions[stage]


def artifact(project, name):
    path = project / DOCS / name
    if path.is_symlink() or not path.resolve().is_relative_to(project.resolve()) or not path.is_file():
        raise ValueError(f'缺少阶段交付文件：{name}')
    size_limit = 2_000_000 if name in {'界面参考.json','界面对照.json'} else 200000
    if not 1 <= path.stat().st_size <= size_limit:
        raise ValueError(f'阶段交付文件为空或过大：{name}')
    return path.read_text()


def check_input(task):
    project = Path(task['project_path'])
    if not (project / DOCS / '需要协助.json').exists():
        return
    result = json.loads(artifact(project, '需要协助.json'))
    if result.get('reason') not in {'login', 'captcha', 'credentials', 'quota'} or not isinstance(result.get('message'), str) or not result['message'].strip():
        raise ValueError('需要协助.json 格式不完整，请说明实际阻碍或继续修复')
    if result['reason'] == 'quota':
        raise QuotaExceeded(result['message'][:1000])
    if result['reason'] in {'login', 'captcha'} and task.get('website'):
        raise LoginExpired(result['message'][:1000], 'website')
    raise NeedsInput(result['message'][:1000])


def validate(task, stage, env):
    project = Path(task['project_path'])
    documents = {name: artifact(project, name) for name in FILES[stage]}
    if stage == 'analysis':
        try:
            result = json.loads(documents['网站分析.json'])
        except json.JSONDecodeError:
            raise ValueError('网站分析文件格式不完整，请查看反馈后继续')
        if result.get('access_ok') is not True:
            reasons = result.get('blockers') or ['请先完成目标网站登录或处理访问提示']
            raise LoginExpired('；'.join(str(item) for item in reasons)[:1000], 'website')
        pages = result.get('pages')
        if not isinstance(pages, list) or not isinstance(result.get('unvisited'), list):
            raise ValueError('网站分析缺少页面覆盖清单')
        if task['website'] and not any(p.get('visited') is True and p.get('url') for p in pages):
            raise ValueError('还没有实际访问的页面记录，请查看分析反馈后继续')
        if task.get('visual_enabled'):
            visual = json.loads(artifact(project, '界面参考.json'))
            if visual.get('status') != 'passed' or not visual.get('shots'):
                raise ValueError('界面参考采集尚未完成')
        if task.get('rea_enabled'):
            rea = json.loads(artifact(project, 'REA深度分析.json'))
            artifact(project, 'REA深度分析.md')
            if rea.get('status') != 'passed' or not rea.get('pages') or any(not p.get('evidence_id') or not p.get('bundle_evidence_id') for p in rea['pages']):
                raise ValueError('REA 深度分析尚未完成，请自动补齐真实证据')
            return f"已分析 {len(pages)} 页；REA 已复核 {len(rea['pages'])} 页、记录 {rea['counts']['unique_requests']} 个不同请求"
        return f"已记录 {sum(p.get('visited') is True for p in pages)} 个访问页面，{len(result['unvisited'])} 个未覆盖入口"
    if stage == 'build':
        for name in ['compose.yml', 'README.md']:
            if not (project/name).is_file():
                raise ValueError(f'开发交付缺少 {name}')
    if stage == 'verify':
        try:
            result = json.loads(documents['验收结果.json'])
        except json.JSONDecodeError:
            raise ValueError('验收结果文件格式不完整，请查看反馈后继续')
        checks = {c['id']:c for c in result.get('checks', [])}
        required = {'frontend','api','database','crud','persistence'}
        if (result.get('status') != 'passed' or result.get('remaining') != [] or
            not required.issubset(checks) or any(checks[k].get('status') != 'passed' or not checks[k].get('evidence') for k in required)):
            raise ValueError('验收未通过：' + json.dumps({'remaining': result.get('remaining'), 'checks': result.get('checks')}, ensure_ascii=False)[:3000])
        url = f"http://127.0.0.1:{task['port']}/"
        response = httpx.get(url, timeout=10, trust_env=False, follow_redirects=True)
        if response.status_code != 200:
            raise ValueError('部署后的本机网页检查未通过')
        command = ['docker','compose','-p','dev-'+task['id'],'-f',str(project/'compose.yml'),'ps','-q']
        ids = subprocess.check_output(command, cwd=project, env=env, text=True, timeout=30).split()
        if not ids:
            raise ValueError('没有检测到本项目运行中的部署容器')
        containers = json.loads(subprocess.check_output(['docker','inspect',*ids], env=env, text=True, timeout=30))
        if any(not c['State']['Running'] or c['State'].get('Health',{}).get('Status') == 'unhealthy' for c in containers):
            raise ValueError('本项目部署容器尚未正常运行')
        if not any(m.get('Type') == 'volume' for c in containers for m in c.get('Mounts',[])):
            raise ValueError('本项目尚未检测到数据库所需的持久数据卷')
        if task.get('visual_enabled'):
            visual = json.loads(artifact(project, '界面对照.json'))
            if visual.get('status') != 'passed' or not visual.get('comparisons'):
                raise ValueError('界面对照未通过；读取交付资料/界面对照.json 的差异区域和截图，修正后重测')
        return '五项验收通过；工作台已复核网页响应、运行容器与持久卷'
    return '阶段交付已生成'


def reports(task):
    project = Path(task['project_path'])
    result = {}
    current = {item['id']:item['status'] for item in task.get('workflow', [])}
    for stage, names in FILES.items():
        if current.get(stage) == 'pending':
            continue
        for name in names:
            try:
                result[name] = artifact(project, name)
            except (ValueError, OSError):
                pass
    if task.get('rea_enabled') and current.get('analysis') != 'pending':
        for name in ['REA深度分析.json', 'REA深度分析.md']:
            try:
                result[name] = artifact(project, name)
            except (ValueError, OSError):
                pass
    if task.get('visual_enabled'):
        for name in ['界面参考.json', '视觉映射.json', '界面对照.json', '界面对照.md']:
            try:
                result[name] = artifact(project, name)
            except (ValueError, OSError):
                pass
    return result
