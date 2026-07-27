import type { MonitorSnapshot, WorkerEvent } from '../../shared/types'

export type MonitorViewState = MonitorSnapshot & {
  lastEvent: string | null
}

export function reduceMonitorEvent(
  state: MonitorViewState,
  event: WorkerEvent
): MonitorViewState {
  if (event.event === 'monitor.status') {
    return {
      ...state,
      ...(event.payload as unknown as MonitorSnapshot),
      lastEvent: event.event
    }
  }
  if (event.event === 'message.processed') {
    const outcome = String(event.payload.outcome ?? 'unknown')
    return {
      ...state,
      counts: {
        ...state.counts,
        [outcome]: (state.counts[outcome] ?? 0) + 1
      },
      lastEvent: event.event
    }
  }
  if (event.event === 'worker.exit') {
    return { ...state, state: 'offline', lastEvent: event.event }
  }
  return { ...state, lastEvent: event.event }
}

export function validateCredentials(values: {
  apiId: string
  apiHash: string
  phone: string
}): string | null {
  if (!/^\d+$/.test(values.apiId) || Number(values.apiId) <= 0) {
    return 'API ID must be a positive number.'
  }
  if (!/^[a-fA-F0-9]{32}$/.test(values.apiHash)) {
    return 'API hash must contain 32 hexadecimal characters.'
  }
  if (!/^\+[1-9]\d{6,14}$/.test(values.phone.replace(/\s/g, ''))) {
    return 'Use an international phone number such as +35799123456.'
  }
  return null
}

export function parseDesktopError(error: unknown): string {
  if (!(error instanceof Error)) return 'Something went wrong.'
  const marker = error.message.indexOf('{"code"')
  if (marker >= 0) {
    try {
      const parsed = JSON.parse(error.message.slice(marker)) as { message?: string }
      if (parsed.message) return parsed.message
    } catch {
      // Fall through to the safe generic message below.
    }
  }
  return error.message || 'Something went wrong.'
}

