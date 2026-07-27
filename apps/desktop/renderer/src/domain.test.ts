import { describe, expect, it } from 'vitest'
import { parseDesktopError, reduceMonitorEvent, validateCredentials } from './domain'

describe('validateCredentials', () => {
  it('accepts a complete Telegram credential set', () => {
    expect(
      validateCredentials({
        apiId: '123456',
        apiHash: 'abcdef0123456789abcdef0123456789',
        phone: '+357 99 123456'
      })
    ).toBeNull()
  })

  it.each([
    [{ apiId: 'no', apiHash: 'abcdef0123456789abcdef0123456789', phone: '+35799123456' }, 'API ID'],
    [{ apiId: '1', apiHash: 'short', phone: '+35799123456' }, 'API Hash'],
    [{ apiId: '1', apiHash: 'abcdef0123456789abcdef0123456789', phone: '99123456' }, 'международном']
  ])('rejects invalid values', (values, message) => {
    expect(validateCredentials(values)).toContain(message)
  })
})

describe('reduceMonitorEvent', () => {
  const initial = { state: 'paused' as const, counts: {}, lastEvent: null }

  it('replaces monitor status', () => {
    expect(
      reduceMonitorEvent(initial, {
        event: 'monitor.status',
        payload: { state: 'monitoring', counts: { sent: 2 } }
      })
    ).toMatchObject({ state: 'monitoring', counts: { sent: 2 } })
  })

  it('increments outcome counters and handles worker exit', () => {
    const processed = reduceMonitorEvent(initial, {
      event: 'message.processed',
      payload: { outcome: 'sent' }
    })
    expect(processed.counts.sent).toBe(1)
    expect(
      reduceMonitorEvent(processed, { event: 'worker.exit', payload: {} }).state
    ).toBe('offline')
  })
})

describe('parseDesktopError', () => {
  it('translates a known worker message', () => {
    const error = new Error(
      'Error invoking remote method: {"code":"validation_error","message":"Choose at least one source chat"}'
    )
    expect(parseDesktopError(error)).toBe('Выберите хотя бы один источник.')
  })

  it('uses a translated error-code fallback', () => {
    const error = new Error(
      'Error invoking remote method: {"code":"telegram_transient","message":"Unknown gateway failure"}'
    )
    expect(parseDesktopError(error)).toBe(
      'Telegram временно недоступен. Повторите попытку позже.'
    )
  })
})
