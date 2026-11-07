import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { Download, ExternalLink, Play, RefreshCw, Square } from "lucide-react"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { WebsiteLogin, type WebsiteSession } from "@/components/Common/WebsiteLogin"
import { request } from "@/lib/task-api"

type Task = {
  id: string
  website: string
  requirements: string
  status: string
  created_at: number
  project_path: string
  error?: string
  log?: string
  technical_log?: string
  report?: string
  login_id?: string | null
  preview_url?: string
  page_limit?: number
  visual_enabled?: boolean
  rea_enabled?: boolean
  auto_repair?: boolean
  max_repairs?: number
  max_hours?: number
  auto_resume_quota?: boolean
  quota_check_minutes?: number
  next_quota_check?: number | null
  quota_reset_at?: number | null
  auth_kind?: string
  quota_checks?: number
  workflow?: { id: string; label: string; status: string; message: string; repairs?: number; last_error?: string }[]
  artifacts?: Record<string, string>
}
const statuses: Record<string, string> = {
  waiting_docker: "等待 Docker 自动恢复",
  waiting_auth: "等待登录恢复", waiting_quota: "等待额度恢复", running: "开发中", finished: "本轮已完成", failed: "需要处理", stopped: "已停止", interrupted: "已中断", needs_input: "等待你处理",
}

const isActive = (status?: string) => status === "running" || status === "waiting_quota" || status === "waiting_auth" || status === "waiting_docker"

export const Route = createFileRoute("/_layout/develop")({
  component: Develop,
  head: () => ({ meta: [{ title: "开发任务 · Vantage 逆向工具" }] }),
})

function Develop() {
  const queryClient = useQueryClient()
  const [website, setWebsite] = useState("")
  const [pageLimit, setPageLimit] = useState(40)
  const [visualEnabled, setVisualEnabled] = useState(true)
  const [reaEnabled, setReaEnabled] = useState(true)
  const [autoRepair, setAutoRepair] = useState(true)
  const [maxRepairs, setMaxRepairs] = useState(10)
  const [maxHours, setMaxHours] = useState(4)
  const [autoResumeQuota, setAutoResumeQuota] = useState(true)
  const [quotaCheckMinutes, setQuotaCheckMinutes] = useState(15)
  const [requirements, setRequirements] = useState("")
  const [followup, setFollowup] = useState("")
  const [selected, setSelected] = useState<string | null>(null)
  const [error, setError] = useState("")
  const [websiteSession, setWebsiteSession] = useState<WebsiteSession | null>(null)
  const [followupSession, setFollowupSession] = useState<WebsiteSession | null>(null)
  const status = useQuery<{ configured: boolean; message: string; craft?: {installed: boolean; message: string}; rea?: {installed: boolean; version?: string; message: string}; docker?: {status: string; message: string; recoveries: number; last_recovered_at?: number; next_check?: number}; login?: {status: string; url?: string; message: string} }>({
    queryKey: ["agent-status"], queryFn: () => request("/status"), retry: false, refetchInterval: 30000,
  })
  const history = useQuery<Task[]>({
    queryKey: ["agent-tasks"], queryFn: () => request("/tasks"), retry: false, refetchInterval: 3000,
  })
  const selectedId = selected || history.data?.[0]?.id
  const task = useQuery<Task>({
    queryKey: ["agent-task", selectedId], queryFn: () => request(`/tasks/${selectedId}`), enabled: !!selectedId,
    retry: false, refetchInterval: (query) => isActive(query.state.data?.status) ? 2000 : 10000,
  })
  const busy = history.data?.some((item) => isActive(item.status)) || isActive(task.data?.status)
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["agent-status"] })
    queryClient.invalidateQueries({ queryKey: ["agent-tasks"] })
    queryClient.invalidateQueries({ queryKey: ["agent-task"] })
  }
  const action = useMutation({
    mutationFn: ({ path, body }: { path: string; body: unknown }) => request(path, body),
    onSuccess: (result: Task) => { setSelected(result.id); setError(""); setFollowup(""); refresh() },
    onError: (err: Error) => setError(err.message),
  })
  const accountLogin = useMutation({
    mutationFn: () => request("/account-login", {}),
    onSuccess: () => { setError(""); refresh() },
    onError: (err: Error) => setError(err.message),
  })
  const download = useMutation({
    mutationFn: async (id: string) => {
      const blob = await request(`/tasks/${id}/download`, undefined, true)
      const url = URL.createObjectURL(blob)
      const link = document.createElement("a")
      link.href = url; link.download = `开发项目-${id.slice(0, 8)}.zip`; link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    },
    onError: (err: Error) => setError(err.message),
  })
  const message = error || status.error?.message || history.error?.message || task.error?.message
  const fieldClass = "w-full rounded-md border bg-background px-3 py-2 text-sm leading-6 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-bold">Vantage 逆向工具</h1>
        <p className="text-muted-foreground">填写网址、完成网站登录并描述需求，自动分析、开发前后端与数据库，再测试部署到本机。</p>
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <span className={status.data?.configured ? "text-emerald-600 dark:text-emerald-400" : "text-muted-foreground"}>
            {status.isPending ? "正在检查账号连接…" : status.data?.message || "本机任务服务未连接"}
          </span>
          <Button variant="ghost" size="sm" onClick={refresh}><RefreshCw />重新检查</Button>
        </div>
        <section aria-label="自动续登" className="space-y-2 rounded-lg border p-3 text-sm">
          <p>登录自动续期已开启：Codex 登录到期时自动刷新；目标网站复用独立浏览器会话，尝试网站自身的续期与单点登录。需要扫码、验证码或重新授权时在这里提示，登录恢复后任务自动继续。</p>
          {(!status.data?.configured || (task.data?.status === "waiting_auth" && task.data.auth_kind === "codex")) && <Button variant="outline" size="sm" disabled={accountLogin.isPending} onClick={() => accountLogin.mutate()}>{accountLogin.isPending ? "正在准备官方登录…" : "连接或重新授权 Codex 账号"}</Button>}
          {status.data?.login?.status === "waiting" && status.data.login.url && <p><a className="underline text-primary" href={status.data.login.url} target="_blank" rel="noreferrer">打开 Codex 官方授权页面</a> · 完成授权后无需点击继续</p>}
          {status.data?.login?.message && <p role="status" className="text-xs text-muted-foreground">{status.data.login.message}</p>}
        </section>
        <section aria-label="Docker 自动恢复" className="space-y-2 rounded-lg border p-3 text-sm" aria-live="polite">
          <p className="font-medium">Docker 环境自动恢复已开启</p>
          <p>{status.isError ? "工作台暂时连接不上，后台会检查 Docker 并尝试恢复；页面会自动重连，无需点击继续。" : status.data?.docker?.message || "后台每 15 秒检查 Docker 和工作台，环境中断时自动恢复原引擎与连接。"}</p>
          <p className="text-xs text-muted-foreground">恢复时保留代码和已完成阶段，等待不占代码修复次数或开发时长。主动停止工作台会暂停自动恢复；重新启动后开启。</p>
          {!!status.data?.docker?.recoveries && <p>已自动恢复 {status.data.docker.recoveries} 次{status.data.docker.last_recovered_at ? ` · 最近恢复：${new Date(status.data.docker.last_recovered_at * 1000).toLocaleString("zh-CN")}` : ""}</p>}
          {status.data?.docker?.next_check && <p>下次尝试：{new Date(status.data.docker.next_check * 1000).toLocaleString("zh-CN")}</p>}
        </section>
      </header>
      {message && <p role="alert" className="rounded-md border border-destructive/40 p-3 text-sm text-destructive">{message}</p>}
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
        <form className="space-y-5 rounded-xl border p-5" onSubmit={(event) => {
          event.preventDefault()
          action.mutate({ path: "/tasks", body: { website, requirements, page_limit: pageLimit, rea_enabled: reaEnabled, visual_enabled: visualEnabled, auto_repair: autoRepair, max_repairs: maxRepairs, max_hours: maxHours, auto_resume_quota: autoResumeQuota, quota_check_minutes: quotaCheckMinutes, login_id: websiteSession?.status === "saved" ? websiteSession.id : null } })
        }}>
          <h2 className="text-lg font-semibold">新建开发任务</h2>
          <div className="space-y-2">
            <Label htmlFor="website">参考网站网址（选填）</Label>
            <Input id="website" type="url" maxLength={2048} placeholder="https://example.com" value={website} onChange={(e) => { setWebsite(e.target.value); setWebsiteSession(null) }} />
            <p className="text-xs text-muted-foreground">用于理解页面和功能；也可以留空，直接描述你想开发的系统。</p>
          </div>
          <WebsiteLogin website={website} onChange={setWebsiteSession} disabled={!!busy} />
          <section aria-label="REA 深度分析" className="space-y-2 rounded-lg border p-4 text-sm">
            <label htmlFor="rea-enabled" className="flex items-center gap-2 font-medium">
              <input id="rea-enabled" type="checkbox" checked={reaEnabled} onChange={(e) => setReaEnabled(e.target.checked)} />
              补充页面代码与接口证据
            </label>
            <p>{status.data?.rea?.message || "正在检查 REA…"}</p>
            <p className="text-xs leading-6 text-muted-foreground">自动复用已保存的网站登录，逐页补充网络请求、前端脚本、接口与路由证据，再用于设计和开发。报告在下方“分析与验收资料”查看；留空网址时跳过。分析范围是已访问页面与加载请求，后台源码及未触发功能仍需另行确认。</p>
          </section>
          <section aria-label="界面对照" className="space-y-2 rounded-lg border p-4 text-sm">
            <label htmlFor="visual-enabled" className="flex items-center gap-2 font-medium">
              <input id="visual-enabled" type="checkbox" checked={visualEnabled} onChange={(e) => setVisualEnabled(e.target.checked)} />
              对照原站外观并自动修正
            </label>
            <p>检查手机、平板和桌面三种宽度。保存页面截图，找出成品差异，修正后再验收；留空网址时跳过。需要重新设计外观时可关闭。</p>
            <details className="text-xs leading-6 text-muted-foreground"><summary>检查范围与工具状态</summary>
              <p>{status.data?.craft?.message || "正在检查界面对照工具…"}。参考页的初始状态、顶部 900 像素进入自动对照；弹窗、滚动区和业务流程仍需浏览器验收。动态内容与示例数据会影响分数，实际差异保留在报告中。</p>
            </details>
          </section>
          <div className="space-y-2">
            <Label htmlFor="requirements">开发需求</Label>
            <textarea id="requirements" className={fieldClass} rows={7} minLength={5} maxLength={16000} required value={requirements} onChange={(e) => setRequirements(e.target.value)}
              placeholder="例如：开发一个中文客户管理系统。可以新增、编辑和搜索客户，记录联系人与跟进状态。需要前端、后端和数据库，完成后在本机运行预览。" />
          </div>
          <section aria-label="自动开发流程" className="space-y-3 rounded-lg bg-muted/40 p-4 text-sm">
            <h3 className="font-medium">点击开始后，自动完成四步</h3>
            <ol className="grid gap-2 sm:grid-cols-2">
              <li>① 登录检查与页面、功能分析</li><li>② 功能方案、接口与数据库设计</li>
              <li>③ 开发中文前端、后端与数据库</li><li>④ 测试、部署并生成本机预览</li>
            </ol>
            <div className="flex flex-wrap items-center gap-2">
              <Label htmlFor="page-limit">最多分析功能页面数</Label>
              <Input id="page-limit" className="w-24" type="number" min={1} max={100} required value={pageLimit} onChange={(e) => setPageLimit(Number(e.target.value))} />
            </div>
            <p className="text-xs leading-6 text-muted-foreground">沿账号可见的导航和入口逐页分析，相同模板取代表页面。未访问的页面、未知后台规则和待接入服务会列入报告；仅凭网址与账号不代表能获得原站源码或完整覆盖隐藏功能。分析原站时只查看功能，测试数据仅在新项目中使用。</p>
          </section>
          <section aria-label="自动修复设置" className="space-y-3 rounded-lg border p-4 text-sm">
            <label className="flex items-center gap-2 font-medium" htmlFor="auto-repair">
              <input id="auto-repair" type="checkbox" checked={autoRepair} onChange={(e) => setAutoRepair(e.target.checked)} />
              出错或一轮未完成时，自动修复并继续
            </label>
            <p className="text-xs leading-6 text-muted-foreground">保留代码和已完成的阶段，从出错的步骤接着做，重新测试直到验收通过并部署成功。关闭此页面仍会继续，请保持电脑唤醒。</p>
            <div className="flex flex-wrap items-center gap-3">
              <Label htmlFor="max-repairs">每阶段最多自动修复</Label>
              <Input id="max-repairs" className="w-20" type="number" min={1} max={20} required disabled={!autoRepair} value={maxRepairs} onChange={(e) => setMaxRepairs(Number(e.target.value))} /><span>次</span>
              <Label htmlFor="max-hours">实际开发最长运行</Label>
              <Input id="max-hours" className="w-20" type="number" min={1} max={12} required value={maxHours} onChange={(e) => setMaxHours(Number(e.target.value))} /><span>小时</span>
            </div>
            <p className="text-xs leading-6 text-muted-foreground">每轮会消耗当前 Codex 额度。登录过期先自动续登；需要扫码、验证码或外部服务密钥时提示你处理；额度不足按下方设置自动等待。达到修复次数或实际开发时长上限会保留进度并停止。可随时点击“停止开发”。</p>
          </section>
          <section aria-label="额度恢复设置" className="space-y-3 rounded-lg border p-4 text-sm">
            <label className="flex items-center gap-2 font-medium" htmlFor="auto-resume-quota">
              <input id="auto-resume-quota" type="checkbox" checked={autoResumeQuota} onChange={(e) => setAutoResumeQuota(e.target.checked)} />
              额度用尽后自动等待，恢复后接着开发
            </label>
            <div className="flex flex-wrap items-center gap-2">
              <Label htmlFor="quota-check-minutes">自动尝试接续的间隔</Label>
              <Input id="quota-check-minutes" className="w-24" type="number" min={5} max={120} required disabled={!autoResumeQuota} value={quotaCheckMinutes} onChange={(e) => setQuotaCheckMinutes(Number(e.target.value))} /><span>分钟</span>
            </div>
            <p className="text-xs leading-6 text-muted-foreground">按间隔尝试从中断阶段继续；额度仍不足就继续等待，恢复后直接开发。等待不消耗修复次数，也不占开发时长。关闭页面或重启工作台后仍保留等待；电脑需要开机、唤醒并联网。登录过期会先自动刷新，确需人工授权时再提示。</p>
          </section>
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" disabled={!status.data?.configured || busy || action.isPending || (!!websiteSession && websiteSession.status !== "saved")}>
              <Play />{action.isPending ? "正在提交…" : "开始开发"}
            </Button>
            <p className="text-xs text-muted-foreground">{busy ? "已有任务在运行或等待恢复，完成或停止后可提交新任务。" : "使用当前 Codex 账号额度；每个任务保存到独立项目目录。"}</p>
          </div>
        </form>
        <section className="rounded-xl border p-5 space-y-3" aria-label="任务历史">
          <h2 className="font-semibold">任务历史</h2>
          {!history.data?.length && <p className="text-sm text-muted-foreground">还没有开发任务。填写需求后点击“开始开发”。</p>}
          <div className="max-h-96 space-y-2 overflow-auto">
            {history.data?.map((item) => (
              <button key={item.id} type="button" aria-pressed={item.id === selectedId} onClick={() => { setSelected(item.id); setFollowup(""); setFollowupSession(null); setError("") }}
                className={`w-full rounded-lg border p-3 text-left text-sm transition-colors hover:bg-accent ${item.id === selectedId ? "border-primary bg-accent" : "border-transparent"}`}>
                <span className="block line-clamp-2 break-words">{item.requirements.length > 64 ? `${item.requirements.slice(0, 64)}…` : item.requirements}</span>
                <span className="mt-2 block text-xs text-muted-foreground">{statuses[item.status] || item.status} · {new Date(item.created_at * 1000).toLocaleString("zh-CN")}</span>
              </button>
            ))}
          </div>
        </section>
      </div>
      {task.data && <section className="space-y-5 rounded-xl border p-5" aria-label="当前任务">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">{statuses[task.data.status] || "任务记录"}</h2>
            <p className="mt-1 text-xs text-muted-foreground">项目编号：{task.data.id.slice(0, 8)} · 关闭页面后，任务仍在本机继续运行</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {task.data.preview_url && <Button variant="outline" asChild><a href={task.data.preview_url} target="_blank" rel="noreferrer"><ExternalLink />打开项目预览</a></Button>}
            <Button variant="outline" disabled={download.isPending} onClick={() => download.mutate(task.data!.id)}><Download />{download.isPending ? "正在打包…" : "下载项目源码"}</Button>
            {isActive(task.data.status) && <Button variant="destructive" disabled={action.isPending} onClick={() => action.mutate({ path: `/tasks/${task.data!.id}/stop`, body: {} })}><Square />停止开发</Button>}
          </div>
        </div>
        {task.data.status === "waiting_docker" && <section aria-label="Docker 等待状态" className="space-y-2 rounded-lg border border-amber-500/40 p-4 text-sm" aria-live="polite">
          <p>正在等待 Docker 环境自动恢复，代码和已完成阶段已保存。</p>
          <p>恢复后自动接续当前阶段，无需点击“继续”。等待不消耗代码修复次数和开发时长；点击“停止开发”可取消任务接续。</p>
        </section>}
        {task.data.status === "waiting_auth" && <section aria-label="登录等待状态" className="space-y-3 rounded-lg border border-amber-500/40 p-4 text-sm" aria-live="polite">
          <h3 className="font-medium">已保存进度，等待{task.data.auth_kind === "website" ? "目标网站" : "Codex 账号"}登录恢复</h3>
          <p>已先尝试自动续登。完成下面的登录操作后，最多约 15 秒自动从中断阶段接着开发；等待不占开发时长和修复次数。可随时停止。</p>
          {task.data.auth_kind === "website" ? <WebsiteLogin website={task.data.website} onChange={setFollowupSession} disabled={false} /> : <>
            <p>网络暂时异常会每 5 分钟自动重试。若授权已失效，请打开官方登录完成授权；也可以在 Codex 中重新登录。</p>
            <Button variant="outline" disabled={accountLogin.isPending} onClick={() => accountLogin.mutate()}>重新授权 Codex 账号</Button>
            {status.data?.login?.url && <a className="block underline text-primary" href={status.data.login.url} target="_blank" rel="noreferrer">打开 Codex 官方授权页面</a>}
          </>}
        </section>}
        {task.data.status === "waiting_quota" && <section aria-label="额度等待状态" className="space-y-2 rounded-lg border border-amber-500/40 bg-amber-500/5 p-4 text-sm" aria-live="polite">
          <h3 className="font-medium">已保存进度，正在等待额度恢复</h3>
          <p>无需点击“继续”，将自动从中断阶段接着做。已自动检查 {task.data.quota_checks || 0} 次。</p>
          {task.data.next_quota_check && <p>下次自动尝试：{new Date(task.data.next_quota_check * 1000).toLocaleString("zh-CN")}</p>}
          {task.data.quota_reset_at && <p>接口报告的预计恢复时间：{new Date(task.data.quota_reset_at * 1000).toLocaleString("zh-CN")}（以实际可用额度为准）</p>}
          <p className="text-xs text-muted-foreground">每 {task.data.quota_check_minutes || 15} 分钟尝试接续，等待不占开发时长。点击“停止开发”会取消后续自动接续。</p>
        </section>}
        {task.data.auto_repair !== undefined && <p className="text-sm text-muted-foreground" aria-label="自动修复状态">
          自动修复{task.data.auto_repair ? "已开启" : "已关闭"} · 已接续 {task.data.workflow?.reduce((sum, stage) => sum + (stage.repairs || 0), 0) || 0} 次 · 每阶段上限 {task.data.max_repairs} 次 · 实际开发时长上限 {task.data.max_hours} 小时
        </p>}
        {task.data.rea_enabled && <p aria-label="REA 任务状态" className="text-sm text-muted-foreground">REA 深度分析已开启 · {task.data.artifacts?.["REA深度分析.md"] ? "分析证据已生成，后续阶段自动使用" : "页面分析完成后，自动复用登录采集证据"}</p>}
        {task.data.visual_enabled && <p aria-label="界面对照任务状态" className="text-sm text-muted-foreground">界面对照已开启 · {task.data.artifacts?.["界面对照.md"] ? "对照结果已生成，可在下方资料中查看" : "采集原站截图，开发后自动对照并修正"}</p>}
        {task.data.workflow && <section aria-label="流程进度" className="space-y-3">
          <h3 className="font-medium">流程进度</h3>
          <ol className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {task.data.workflow.map((stage, index) => <li key={stage.id} aria-current={["running", "retrying"].includes(stage.status) ? "step" : undefined}
              className={`rounded-lg border p-3 ${stage.status === "completed" ? "border-emerald-500/40 bg-emerald-500/5" : ["running", "retrying"].includes(stage.status) ? "border-primary bg-accent" : ""}`}>
              <p className="text-sm font-medium">{index + 1}. {stage.label}</p>
              <p className="mt-2 text-xs text-muted-foreground">{{pending:"等待前一步",running:"执行中",retrying:"等待自动接续",waiting_docker:"等待 Docker 自动恢复",waiting_auth:"等待登录恢复",waiting_quota:"等待额度恢复",completed:"已完成",failed:"需要处理",needs_input:"等待你处理",stopped:"已停止",interrupted:"已中断"}[stage.status] || stage.status}</p>
              {!!stage.repairs && <p className="mt-2 text-xs">已自动接续 {stage.repairs} 次</p>}
              {stage.last_error && <details className="mt-2 text-xs"><summary className="cursor-pointer text-muted-foreground">最近一次问题</summary><p className="mt-2 break-words leading-5">{stage.last_error}</p></details>}
              {stage.message && <p className="mt-2 break-words text-xs leading-5">{stage.message}</p>}
            </li>)}
          </ol>
        </section>}
        {task.data.artifacts && Object.keys(task.data.artifacts).length > 0 && <section aria-label="分析与验收资料" className="space-y-2">
          <h3 className="font-medium">分析与验收资料</h3>
          <p className="text-xs text-muted-foreground">可在这里查看已分析的页面、功能方案和实际验收结果；文件也包含在源码下载中。</p>
          {Object.entries(task.data.artifacts).map(([name, content]) => <details key={name} className="rounded-lg border p-3 text-sm">
            <summary className="cursor-pointer font-medium">{name}</summary>
            <pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap break-words font-sans text-xs leading-6">{content}</pre>
          </details>)}
        </section>}
        {task.data.error && <p role="status" className="text-sm text-amber-600 dark:text-amber-400">{task.data.error}</p>}
        <details className="text-sm"><summary className="cursor-pointer text-muted-foreground">查看本轮需求</summary><p className="mt-3 whitespace-pre-wrap break-words leading-6">{task.data.requirements}</p></details>
        {task.data.report && <div className="space-y-2"><h3 className="font-medium">开发反馈</h3><p className="max-h-80 overflow-auto whitespace-pre-wrap break-words text-sm leading-7">{task.data.report}</p></div>}
        <div className="space-y-2"><h3 className="font-medium">运行进度</h3><pre aria-live="off" className="max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-muted p-4 font-sans text-sm leading-6">{task.data.log || "正在准备开发环境…"}</pre></div>
        <p className="break-all text-xs text-muted-foreground">源码保存在：{task.data.project_path}</p>
        <details className="text-sm"><summary className="cursor-pointer text-muted-foreground">查看详细运行日志</summary><pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap break-all text-xs">{task.data.technical_log || "暂无详细日志"}</pre></details>
        {!isActive(task.data.status) && <form className="space-y-3 border-t pt-5" onSubmit={(event) => {
          event.preventDefault(); action.mutate({ path: `/tasks/${task.data!.id}/continue`, body: { website: task.data!.website, requirements: followup, login_id: followupSession?.status === "saved" ? followupSession.id : null } })
        }}>
          <WebsiteLogin website={task.data.website} onChange={setFollowupSession} disabled={!!busy} />
          <Label htmlFor="followup">补充需求，在这个项目上继续开发</Label>
          <textarea id="followup" className={fieldClass} rows={3} required minLength={5} maxLength={16000} value={followup} onChange={(e) => setFollowup(e.target.value)} placeholder="说明需要增加的功能，或描述预览时遇到的问题。" />
          <Button disabled={busy || action.isPending || !status.data?.configured || (!!followupSession && followupSession.status !== "saved")} type="submit"><Play />继续开发</Button>
        </form>}
      </section>}
    </div>
  )
}
