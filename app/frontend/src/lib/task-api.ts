const API = "http://127.0.0.1:18781"
export async function request(path: string, body?: unknown, download = false) {
  const response = await fetch(`${API}${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: {
      Authorization: `Bearer ${localStorage.getItem("access_token") || ""}`,
      "X-Workbench": "1",
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  }).catch(() => { throw new Error("本机任务服务尚未连接，请稍后点击重新检查。") })
  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    throw new Error(typeof error.detail === "string" ? error.detail : "请求未完成，请重试")
  }
  return download ? response.blob() : response.json()
}
