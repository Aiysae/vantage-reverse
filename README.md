# Vantage 逆向工具

### 给它一个网站，把看见的页面、交互和结构变成一个可以继续开发的项目。

看到一个想研究的网站，你可能需要一边点页面、一边记录功能，再对着截图还原界面。Vantage 逆向工具把这些工作放进同一个工作台：输入参考网址和需求，工具会分析可访问的页面，整理设计，生成项目，再用浏览器和测试结果检查交付。

它适合研究网站的功能与交互、搭建原型，以及从参考界面出发开发自己的产品。你可以在工作台查看进度、检查分析和验收资料，下载生成的项目，继续修改代码。


![Vantage workbench](docs/workbench.png)

## 它能做什么

- **看懂参考网站**：采集页面、交互、网络请求和前端资源，整理观察到的功能与证据。需要登录时，可通过浏览器完成登录。
- **从分析走到项目**：围绕需求依次进行网站分析、功能与数据设计、开发和验收，生成可继续开发的项目代码。
- **对照页面检查外观**：结合参考截图、布局数据和成品截图，帮助发现视觉差异；也可以关闭外观对照，按自己的方向设计。
- **保留过程和结果**：查看任务进度、分析资料与验收报告；任务可以停止，已有项目文件会保留。
- **让 Agent 调用**：提供 MCP 入口，可通过对话启动任务、查询进度、读取报告和停止任务。

## 一次实测

在一个两页项目管理网站的对照测试中，加入视觉对照后，6 张截图的平均感知相似度从 80.7% 提升到 93.7%，8 项功能验收均通过。这是一组具体样例，页面复杂度、动态内容和任务条件不同，结果也会不同。

## 使用边界

当前视觉检查覆盖已访问页面在 390、768、1440 像素宽度下的初始状态和页面顶部区域；菜单、弹窗、滚动内容及其他业务状态需要另行检查。生成项目是根据可见资料和需求进行的重建，网站服务端的原始源码不会因此出现。原生软件分析依赖对应工具，当前网站重建的测试结果不代表原生程序分析已完成验收。


## 在 macOS 上安装

准备 Python 3.12、Node.js 24、npm、uv、Docker（含 Compose），并启动 Docker。安装过程会下载 Python 和 Node 依赖、Chromium 及 Craft Anything CLI；模型调用需要可用的 Codex 登录与额度。

```bash
git clone https://github.com/Aiysae/vantage-reverse.git
cd vantage-reverse
./setup.sh
./workbench.sh agent-check
./workbench.sh up
```

打开 `http://127.0.0.1:18780/develop`，填写参考网址和需求，选择分析范围后开始。需要登录的网站，可在工作台打开登录窗口，完成登录后保存会话。

停止服务运行 `./workbench.sh stop`，任务文件和数据库卷会保留。工作台使用 18780 和 18781 端口，请先确保端口空闲。安装器仅在首次运行时生成本地配置；`.env`、`agent.env`、任务记录和浏览器会话应留在自己的电脑上。

## 通过 MCP 使用

将项目目录的 `tools/.venv/bin/python` 作为命令，`scripts/vantage_mcp.py` 作为参数加入支持 MCP 的客户端。启动工作台后，可让 Agent 调用 `vantage_info`、`vantage_start`、`vantage_wait` 和 `vantage_get_report`。

## 运行与依赖

工作台是本机开发工具。Agent 以当前用户权限运行命令并读写文件，任务目录并非隔离沙箱；请检查生成的代码和执行结果。任务记录、会话和生成项目可能包含敏感资料。模型使用受账号权限和额度影响。

基础应用基于 [Full Stack FastAPI Template](https://github.com/fastapi/full-stack-fastapi-template)，保留其 [MIT 许可证](app/LICENSE)。分析与界面对照使用 [REA](https://github.com/morluto/rea)、[Craft Anything](https://github.com/storytold/craft-anything)、[Playwright MCP](https://github.com/microsoft/playwright-mcp) 和 [OpenHands](https://github.com/OpenHands/software-agent-sdk)，分别遵循各自的许可证；Craft 由安装脚本从其发布页下载，许可证随下载包保留。

本项目代码采用 [MIT 许可证](LICENSE)。

安装依赖的审计结果：REA 6.4.0 的部分间接依赖目前有中危提示，涉及 `glob` 和 `minimatch`；高危提示对应的 Zod 已在本项目锁定到修复版本。使用前可在 `tools/` 目录运行 `npm audit` 查看当前详情。
