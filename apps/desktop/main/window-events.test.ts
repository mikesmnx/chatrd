import { describe, expect, it, vi } from 'vitest'

import { sendWorkerEvent, type WorkerEventTarget } from './window-events'

function target(options: { windowDestroyed?: boolean; contentsDestroyed?: boolean } = {}) {
  const send = vi.fn()
  const value: WorkerEventTarget = {
    isDestroyed: () => Boolean(options.windowDestroyed),
    webContents: {
      isDestroyed: () => Boolean(options.contentsDestroyed),
      send
    }
  }
  return { send, value }
}

describe('sendWorkerEvent', () => {
  const event = { event: 'monitor.status', payload: { state: 'paused' } }

  it('sends an event to a live renderer', () => {
    const { send, value } = target()
    expect(sendWorkerEvent(value, event)).toBe(true)
    expect(send).toHaveBeenCalledWith('worker:event', event)
  })

  it('ignores events after the window is gone', () => {
    expect(sendWorkerEvent(null, event)).toBe(false)

    const destroyedWindow = target({ windowDestroyed: true })
    expect(sendWorkerEvent(destroyedWindow.value, event)).toBe(false)
    expect(destroyedWindow.send).not.toHaveBeenCalled()

    const destroyedContents = target({ contentsDestroyed: true })
    expect(sendWorkerEvent(destroyedContents.value, event)).toBe(false)
    expect(destroyedContents.send).not.toHaveBeenCalled()
  })
})
