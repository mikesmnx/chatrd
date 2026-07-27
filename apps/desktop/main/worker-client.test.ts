import { describe, expect, it } from 'vitest'
import { WorkerRequestError } from './worker-client'

describe('WorkerRequestError', () => {
  it('preserves a stable safe code', () => {
    const error = new WorkerRequestError('worker_timeout', 'Worker timed out')
    expect(error.code).toBe('worker_timeout')
    expect(error.message).toBe('Worker timed out')
    expect(error.name).toBe('WorkerRequestError')
  })
})

