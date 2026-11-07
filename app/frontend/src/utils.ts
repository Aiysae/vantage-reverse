import { AxiosError } from "axios"

const errorMessages: Record<string, string> = {
  "Incorrect email or password": "邮箱或密码错误",
  "Incorrect password": "当前密码错误",
  "Inactive user": "账号已停用",
  "Could not validate credentials": "登录状态已失效，请重新进入工作台",
  "Invalid token": "重置链接已失效，请重新申请",
  "User not found": "用户不存在",
  "Item not found": "记录不存在或已被删除",
  "Not enough permissions": "当前账号没有操作权限",
  "The user doesn't have enough privileges": "当前账号没有操作权限",
  "User with this email already exists": "该邮箱已被使用",
  "The user with this email already exists in the system": "该邮箱已被使用",
  "The user with this email already exists in the system.": "该邮箱已被使用",
  "The user with this id does not exist in the system": "用户不存在",
  "The user with this username does not exist in the system.": "用户不存在",
  "New password cannot be the same as the current one": "新密码需要与当前密码不同",
  "Super users are not allowed to delete themselves": "管理员账号不支持自行删除",
}

function extractErrorMessage(err: Error): string {
  if (err instanceof AxiosError) {
    const detail = err.response?.data?.detail
    if (typeof detail === "string" && errorMessages[detail]) {
      return errorMessages[detail]
    }
    if (Array.isArray(detail) || err.response?.status === 422) {
      return "填写的信息不符合要求，请检查后重试"
    }
    if (!err.response) return "连接服务失败，请检查工作台是否正在运行"
    if (err.response.status >= 500) return "服务暂时出错，请稍后重试"
    if (err.response.status === 401) return "登录状态已失效，请重新进入工作台"
    if (err.response.status === 403) return "当前账号没有操作权限"
    if (err.response.status === 404) return "请求的内容不存在或已被删除"
  }
  return "操作未完成，请稍后重试"
}

export const handleError = function (this: (msg: string) => void, err: Error) {
  const errorMessage = extractErrorMessage(err)
  this(errorMessage)
}

export const getInitials = (name: string): string => {
  return name
    .split(" ")
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase()
}
