import { join } from 'node:path'
import { app, BrowserWindow, ipcMain, shell } from 'electron'
import { SecretStore, TelegramSecret } from './secret-store'
import { WorkerClient, WorkerRequestError } from './worker-client'
import { sendWorkerEvent } from './window-events'

const ALLOWED_METHODS = new Set([
  'system.snapshot',
  'auth.status',
  'auth.start',
  'auth.submitCode',
  'auth.submitPassword',
  'auth.logout',
  'chats.list',
  'settings.get',
  'settings.update',
  'ollama.chat',
  'sources.list',
  'sources.upsert',
  'sources.remove',
  'rules.list',
  'rules.create',
  'rules.update',
  'rules.delete',
  'monitor.start',
  'monitor.pause',
  'monitor.status',
  'processing.skip',
  'processing.retry'
])

let mainWindow: BrowserWindow | null = null
const worker = new WorkerClient()
let secretStore: SecretStore
let pendingCredentials: Pick<TelegramSecret, 'api_id' | 'api_hash'> | null = null
let gracefulQuitStarted = false

const hasLock = app.requestSingleInstanceLock()
if (!hasLock) app.quit()

app.on('second-instance', () => {
  if (!mainWindow || mainWindow.isDestroyed()) return
  if (mainWindow.isMinimized()) mainWindow.restore()
  mainWindow.focus()
})

app.whenReady().then(async () => {
  secretStore = new SecretStore(join(app.getPath('userData'), 'secrets.bin'))
  await worker.start()
  let saved: TelegramSecret | null = null
  try {
    saved = await secretStore.load()
  } catch {
    console.error('Saved Telegram session could not be decrypted.')
  }
  if (saved) {
    try {
      await worker.request('auth.restore', saved)
    } catch (error) {
      console.error(`Saved Telegram session could not be restored: ${safeErrorCode(error)}`)
    }
  }
  registerIpc()
  createWindow()

  worker.on('event', (event) => {
    sendWorkerEvent(mainWindow, event)
  })
  worker.on('exit', () => {
    sendWorkerEvent(mainWindow, {
      event: 'worker.exit',
      payload: { code: 'worker_exited' }
    })
  })
})

app.on('window-all-closed', () => {
  app.quit()
})

app.on('before-quit', (event) => {
  if (gracefulQuitStarted) return
  event.preventDefault()
  gracefulQuitStarted = true
  void worker.stop().finally(() => app.quit())
})

function createWindow(): void {
  const window = new BrowserWindow({
    width: 1180,
    height: 780,
    minWidth: 920,
    minHeight: 640,
    show: false,
    backgroundColor: '#f5f3ee',
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
    webPreferences: {
      preload: join(__dirname, '../preload/index.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  })
  mainWindow = window
  window.once('ready-to-show', () => {
    if (!window.isDestroyed()) window.show()
  })
  window.once('closed', () => {
    if (mainWindow === window) mainWindow = null
  })
  window.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('https://')) void shell.openExternal(url)
    return { action: 'deny' }
  })

  if (process.env.ELECTRON_RENDERER_URL) {
    void window.loadURL(process.env.ELECTRON_RENDERER_URL)
  } else {
    void window.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

function registerIpc(): void {
  ipcMain.handle(
    'worker:call',
    async (_event, method: unknown, payload: unknown = {}) => {
      if (typeof method !== 'string' || !ALLOWED_METHODS.has(method)) {
        throw new WorkerRequestError('method_not_allowed', 'This desktop action is not allowed.')
      }
      if (!isPlainObject(payload)) {
        throw new WorkerRequestError('invalid_request', 'Request payload must be an object.')
      }

      if (method === 'auth.start') {
        pendingCredentials = {
          api_id: Number(payload.api_id),
          api_hash: String(payload.api_hash ?? '')
        }
      }

      let result: any
      try {
        result = await worker.request<any>(
          method,
          payload,
          method === 'ollama.chat' ? 10 * 60_000 : undefined
        )
      } catch (error) {
        throw new Error(JSON.stringify({
          code: safeErrorCode(error),
          message: error instanceof Error ? error.message : 'The request failed.'
        }))
      }

      if (
        result &&
        typeof result === 'object' &&
        typeof result._sensitive_session === 'string'
      ) {
        const credentials = pendingCredentials ?? {
          api_id: Number(result._sensitive_api_id),
          api_hash: String(result._sensitive_api_hash)
        }
        await secretStore.save({
          ...credentials,
          session: result._sensitive_session
        })
        delete result._sensitive_session
        delete result._sensitive_api_id
        delete result._sensitive_api_hash
        pendingCredentials = null
      }
      if (method === 'auth.logout') {
        await secretStore.clear()
        pendingCredentials = null
      }
      return result
    }
  )
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function safeErrorCode(error: unknown): string {
  return error instanceof WorkerRequestError ? error.code : 'desktop_error'
}
