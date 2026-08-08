import type { WorkerEvent } from '../shared/types'

export type WorkerEventTarget = {
  isDestroyed: () => boolean
  webContents: {
    isDestroyed: () => boolean
    send: (channel: string, event: WorkerEvent) => void
  }
}

export function sendWorkerEvent(
  target: WorkerEventTarget | null,
  event: WorkerEvent
): boolean {
  if (!target || target.isDestroyed() || target.webContents.isDestroyed()) return false
  target.webContents.send('worker:event', event)
  return true
}
