const accessTokenKey = "access_token"
const localDesktopModeKey = "local_desktop_mode"
const localSessionRejectedKey = "local_session_rejected"

let localSessionAttempt: Promise<boolean> | undefined

export const isLocalDesktopMode = () =>
  localStorage.getItem(localDesktopModeKey) === "true"

const isExpired = (token: string) => {
  try {
    const payload = JSON.parse(atob(token.split(".")[1])) as { exp?: number }
    return typeof payload.exp === "number" && payload.exp * 1000 <= Date.now()
  } catch {
    return false
  }
}

export const rejectCurrentLocalToken = () => {
  if (!isLocalDesktopMode()) return false

  const token = localStorage.getItem(accessTokenKey)
  if (token && !isExpired(token)) {
    sessionStorage.setItem(localSessionRejectedKey, "true")
  }
  localStorage.removeItem(accessTokenKey)
  localStorage.removeItem(localDesktopModeKey)
  return true
}

export const ensureLocalSession = () => {
  if (sessionStorage.getItem(localSessionRejectedKey) === "true") {
    return Promise.resolve(false)
  }

  if (!localSessionAttempt) {
    localSessionAttempt = fetch("/api/v1/login/local-session", {
      method: "POST",
      headers: { "X-Local-Desktop": "1" },
    })
      .then(async (response) => {
        if (response.ok) {
          const token = (await response.json()) as { access_token: string }
          localStorage.setItem(accessTokenKey, token.access_token)
          localStorage.setItem(localDesktopModeKey, "true")
          return true
        }

        localStorage.removeItem(localDesktopModeKey)
        if (response.status !== 404) {
          localStorage.removeItem(accessTokenKey)
        }
        return false
      })
      .catch(() => {
        localStorage.removeItem(accessTokenKey)
        localStorage.removeItem(localDesktopModeKey)
        return false
      })
  }

  return localSessionAttempt
}
