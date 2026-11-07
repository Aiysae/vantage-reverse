import { Button } from "@/components/ui/button"
import { createFileRoute, Link } from "@tanstack/react-router"

import useAuth from "@/hooks/useAuth"

export const Route = createFileRoute("/_layout/")({
  component: Dashboard,
  head: () => ({
    meta: [
      {
        title: "首页 · Vantage 逆向工具",
      },
    ],
  }),
})

function Dashboard() {
  const { user: currentUser } = useAuth()

  return (
    <div>
      <div>
        <h1 className="text-2xl truncate max-w-sm">
          你好，{currentUser?.full_name || currentUser?.email} 👋
        </h1>
        <p className="text-muted-foreground">
          填写网站网址和开发需求，让 OpenHands 开始开发。
        </p>
        <Button className="mt-5" asChild><Link to="/develop">新建开发任务</Link></Button>
      </div>
    </div>
  )
}
