import { contextBridge, ipcRenderer } from 'electron'
import type { ChatRDDesktopApi, WorkerEvent } from '../shared/types'

const api: ChatRDDesktopApi = {
  call: <T>(method: string, payload: Record<string, unknown> = {}) =>
    ipcRenderer.invoke('worker:call', method, payload) as Promise<T>,
  onWorkerEvent: (callback: (event: WorkerEvent) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, value: WorkerEvent) => callback(value)
    ipcRenderer.on('worker:event', listener)
    return () => ipcRenderer.removeListener('worker:event', listener)
  },
  platform: process.platform
}

contextBridge.exposeInMainWorld('chatrd', Object.freeze(api))
