// Runs inside the private Playwright MCP process, never inside the visited website.
import fs from 'node:fs'
import path from 'node:path'
const directory = __SESSION_DIR__
const initialized = new WeakSet()
let snapshots: Record<string, [string, string][]> = {}
let pending = Promise.resolve()
function save(name: string, value: string) {
  const target = path.join(directory, name)
  fs.writeFileSync(`${target}.tmp`, value, { mode: 0o600 })
  fs.renameSync(`${target}.tmp`, target)
}
export default async ({ page }) => {
  const context = page.context()
  if (!initialized.has(context)) {
    initialized.add(context)
    const cookiePath = path.join(directory, 'cookies.json')
    if (fs.existsSync(cookiePath)) {
      await context.clearCookies()
      await context.addCookies(JSON.parse(fs.readFileSync(cookiePath, 'utf8')))
    }
    const close = context.close.bind(context)
    context.close = async (...args) => {
      await pending
      try { save('cookies.json', JSON.stringify(await context.cookies())) } catch {}
      return close(...args)
    }
    const snapshotPath = path.join(directory, 'session-storage.json')
    if (fs.existsSync(snapshotPath)) snapshots = JSON.parse(fs.readFileSync(snapshotPath, 'utf8'))
  }
  const capture = () => {
    pending = pending.then(async () => {
      save('cookies.json', JSON.stringify(await context.cookies()))
      if (!page.isClosed() && /^https?:/.test(page.url())) {
        const data = await page.evaluate(() => ({ origin: location.origin, entries: Object.entries(sessionStorage) }))
        snapshots[data.origin] = data.entries
        save('session-storage.json', JSON.stringify(snapshots))
        save('session-storage.js', `(() => { const data = ${JSON.stringify(snapshots)}; for (const [key,value] of data[location.origin] || []) if (sessionStorage.getItem(key) === null) sessionStorage.setItem(key,value); })();`)
      }
    }).catch(() => {}) // A closing or navigating page is captured on its next response.
  }
  page.on('requestfinished', capture)
  page.on('domcontentloaded', capture)
}
