import { Link } from "@tanstack/react-router"
import { LayoutDashboard } from "lucide-react"

import { cn } from "@/lib/utils"

interface LogoProps {
  variant?: "full" | "icon" | "responsive"
  className?: string
  asLink?: boolean
}

export function Logo({
  variant = "full",
  className,
  asLink = true,
}: LogoProps) {
  const content = (
    <span className={cn("inline-flex items-center gap-2 whitespace-nowrap font-semibold text-lg", className)}>
      <LayoutDashboard className="size-5 shrink-0" aria-hidden="true" />
      {variant !== "icon" && (
        <span className={variant === "responsive" ? "group-data-[collapsible=icon]:hidden" : undefined}>
          Vantage 逆向工具
        </span>
      )}
    </span>
  )

  return asLink ? <Link to="/" aria-label="Vantage 逆向工具首页">{content}</Link> : content
}
