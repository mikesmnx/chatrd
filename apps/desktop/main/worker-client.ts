import { ChildProcessWithoutNullStreams, spawn } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { EventEmitter } from 'node:events'
import { existsSync } from 'node:fs'
import { createInterface } from 'node:readline'
import { join, resolve } from 'node:path'
import { app } from 'electron'

type PendingRequest = {
  resolve: (value: unknown) => void
  reject: (error: Error) => void
  timer: NodeJS.Timeout
}

type ResponseFrame = {
  protocolVersion: number
  type: 'response' | 'error' | 'event'
  id?: string
  result?: unknown
  event?: string
  payload?: Record<string, unknown>
  error?: { code: string; message: string }
}

export class WorkerRequestError extends Error {
  constructor(
    public readonly code: string,
    message: string
  ) {
    super(message)
    this.name = 'WorkerRequestError'
  }
}

export class WorkerClient extends EventEmitter {
  private process: ChildProcessWithoutNullStreams | null = null
  private readonly pending = new Map<string, PendingRequest>()
  private stopping = false

  async start(): Promise<void> {
    if (this.process) return
    const spec = workerCommand()
    this.stopping = false
    this.process = spawn(spec.command, spec.args, {
      cwd: spec.cwd,
      env: {
        ...process.env,
        ...spec.env,
        CHATRD_DATA_DIR: app.getPath('userData')
      },
      windowsHide: true,
      stdio: ['pipe', 'pipe', 'pipe']
    })

    const output = createInterface({ input: this.process.stdout })
    output.on('line', (line) => this.handleLine(line))
    this.process.stderr.on('data', (chunk: Buffer) => {
      const message = chunk.toString('utf8').trim()
      if (message) console.error(`[worker] ${message}`)
    })
    this.process.on('exit', (code) => {
      const error = new WorkerRequestError(
        'worker_exited',
        `The local Telegram worker stopped unexpectedly (${code ?? 'unknown'}).`
      )
      for (const request of this.pending.values()) {
        clearTimeout(request.timer)
        request.reject(error)
      }
      this.pending.clear()
      this.process = null
      if (!this.stopping) this.emit('exit', { code })
    })

    await this.request('system.ping', {}, 15_000)
  }

  request<T = unknown>(
    method: string,
    payload: Record<string, unknown> = {},
    timeoutMs = method === 'monitor.start' ? 10 * 60_000 : 30_000
  ): Promise<T> {
    if (!this.process) {
      return Promise.reject(
        new WorkerRequestError('worker_unavailable', 'The local worker is not running.')
      )
    }
    const id = randomUUID()
    const frame = JSON.stringify({
      protocolVersion: 1,
      type: 'request',
      id,
      method,
      payload
    })
    if (Buffer.byteLength(frame, 'utf8') > 1_048_576) {
      return Promise.reject(
        new WorkerRequestError('frame_too_large', 'The request is too large.')
      )
    }
    return new Promise<T>((resolvePromise, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id)
        reject(new WorkerRequestError('worker_timeout', 'The local worker did not respond.'))
      }, timeoutMs)
      this.pending.set(id, {
        resolve: resolvePromise as (value: unknown) => void,
        reject,
        timer
      })
      this.process?.stdin.write(`${frame}\n`)
    })
  }

  async stop(): Promise<void> {
    this.stopping = true
    if (!this.process) return
    const active = this.process
    try {
      await this.request('system.shutdown', {}, 5_000)
    } catch {
      // Forced termination is safe because processing state is durable.
    }
    if (!active.killed) active.kill()
    this.process = null
  }

  private handleLine(line: string): void {
    let frame: ResponseFrame
    try {
      frame = JSON.parse(line) as ResponseFrame
    } catch {
      this.emit('protocol-error', { code: 'invalid_json' })
      return
    }
    if (frame.protocolVersion !== 1) {
      this.emit('protocol-error', { code: 'protocol_mismatch' })
      return
    }
    if (frame.type === 'event' && frame.event) {
      this.emit('event', { event: frame.event, payload: frame.payload ?? {} })
      return
    }
    if (!frame.id) return
    const request = this.pending.get(frame.id)
    if (!request) return
    clearTimeout(request.timer)
    this.pending.delete(frame.id)
    if (frame.type === 'error') {
      request.reject(
        new WorkerRequestError(
          frame.error?.code ?? 'worker_error',
          frame.error?.message ?? 'The local worker reported an error.'
        )
      )
    } else {
      request.resolve(frame.result)
    }
  }
}

function workerCommand(): {
  command: string
  args: string[]
  cwd: string
  env: Record<string, string>
} {
  if (app.isPackaged) {
    const filename = process.platform === 'win32' ? 'chatrd-worker.exe' : 'chatrd-worker'
    const command = join(process.resourcesPath, 'worker', filename)
    if (!existsSync(command)) {
      throw new Error(`Packaged worker is missing: ${command}`)
    }
    return { command, args: [], cwd: app.getPath('userData'), env: {} }
  }

  const root = resolve(process.cwd())
  const source = join(root, 'services', 'telegram-worker', 'src')
  return {
    command: process.env.CHATRD_PYTHON || 'python',
    args: ['-m', 'chatrd_worker.main'],
    cwd: root,
    env: { PYTHONPATH: source }
  }
}
