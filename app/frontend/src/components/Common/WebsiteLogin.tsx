import { useEffect } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { LogIn, Save, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { request } from "@/lib/task-api"

export type WebsiteSession = { id: string; status: string; message: string; origin: string }

export function WebsiteLogin({ website, onChange, disabled }: {
  website: string
  onChange: (session: WebsiteSession | null) => void
  disabled: boolean
}) {
  const queryClient = useQueryClient()
  let valid = false
  try { valid = ["http:", "https:"].includes(new URL(website).protocol) } catch { /* wait for a complete address */ }
  const queryKey = ["website-login", website]
  const session = useQuery<WebsiteSession | null>({
    queryKey, queryFn: () => request(`/website-login?website=${encodeURIComponent(website)}`),
    enabled: valid, retry: false,
    refetchInterval: (query) => ["opening", "waiting"].includes(query.state.data?.status || "") ? 1500 : false,
  })
  useEffect(() => { onChange(valid ? session.data ?? null : null) }, [valid, session.data, onChange])
  const change = useMutation({
    mutationFn: (operation: "open" | "save" | "clear") => operation === "open"
      ? request("/website-login", { website })
      : request(`/website-login/${session.data?.id}/${operation}`, {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["website-login"] }),
  })
  const record = valid ? session.data : null
  const waiting = record?.status === "waiting"
  const opening = record?.status === "opening"
  const error = change.error?.message || session.error?.message
  return (
    <section className="space-y-3 rounded-lg border bg-muted/30 p-4" aria-label="目标网站登录">
      <h3 className="text-sm font-medium">目标网站登录</h3>
      <p className="text-xs leading-6 text-muted-foreground">需要账号时，点击下方按钮，在打开的网站窗口填写账号密码或扫码；登录成功后回到这里保存。账号密码不用写进开发需求。</p>
      <div className="flex flex-wrap gap-2">
        {!waiting && !opening && <Button type="button" variant="outline" size="sm" disabled={!valid || disabled || change.isPending} onClick={() => change.mutate("open")}>
          <LogIn />{record?.status === "saved" ? "重新登录目标网站" : "登录目标网站"}
        </Button>}
        {waiting && <Button type="button" size="sm" disabled={change.isPending || disabled} onClick={() => change.mutate("save")}><Save />已登录，保存登录状态</Button>}
        {record && <Button type="button" variant="ghost" size="sm" disabled={change.isPending || disabled} onClick={() => change.mutate("clear")}><Trash2 />{record.status === "saved" ? "清除登录状态" : "取消登录"}</Button>}
      </div>
      <p role="status" className={`text-xs leading-6 ${record?.status === "saved" ? "text-emerald-600 dark:text-emerald-400" : "text-muted-foreground"}`}>
        {!valid ? "先填写上方的网站网址，再打开登录窗口。" : record?.message || "尚未保存登录状态。公开网站可直接开始开发。"}
      </p>
      {record?.status === "saved" && <p className="text-xs text-muted-foreground">登录状态仅保存在这台电脑，不包含在源码下载中。网站可自动续期时直接续用；仍需扫码或验证码时再提示。登录后点击保存，等待中的任务会自动接续。</p>}
      {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
    </section>
  )
}
