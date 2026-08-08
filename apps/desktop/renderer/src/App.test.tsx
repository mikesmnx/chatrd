import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { AppSnapshot, ChatRDDesktopApi } from '../../shared/types'
import { App } from './App'

const snapshot: AppSnapshot = {
  authenticated: true,
  settings: {
    destination_peer_id: 42,
    delivery_mode: 'copy',
    paused: true,
    ai_enabled: false,
    ollama_base_url: 'http://127.0.0.1:11434',
    ollama_model: 'gpt-oss:20b',
    ollama_prompt: '',
    ollama_timeout_seconds: 120,
    ollama_temperature: 0
  },
  sources: [],
  rules: [],
  monitor: { state: 'paused', counts: {} }
}

describe('Ollama settings', () => {
  const call = vi.fn(async (method: string) => {
    if (method === 'system.snapshot') return snapshot
    if (method === 'ollama.chat') {
      return { model: 'gpt-oss:20b', message: 'Ответ локальной модели' }
    }
    return { ok: true }
  })

  beforeEach(() => {
    call.mockClear()
    const api: ChatRDDesktopApi = {
      call: call as unknown as ChatRDDesktopApi['call'],
      onWorkerEvent: () => () => undefined,
      platform: 'win32'
    }
    Object.defineProperty(window, 'chatrd', { configurable: true, value: api })
  })

  it('saves visible settings with internal generation defaults', async () => {
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: /Настройки/ }))

    fireEvent.change(screen.getByLabelText('Адрес сервера Ollama'), {
      target: { value: 'http://localhost:11434' }
    })
    fireEvent.change(screen.getByLabelText('Модель'), {
      target: { value: 'gpt-oss:20b' }
    })
    expect(screen.queryByLabelText('Инструкция отбора сообщений')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Тайм-аут, секунд')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Температура')).not.toBeInTheDocument()
    expect(screen.queryByText(/ollama pull/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }))

    await waitFor(() =>
      expect(call).toHaveBeenCalledWith('settings.update', {
        values: {
          ai_enabled: false,
          ollama_base_url: 'http://localhost:11434',
          ollama_model: 'gpt-oss:20b',
          ollama_prompt: '',
          ollama_timeout_seconds: 120,
          ollama_temperature: 0
        }
      })
    )
  })

  it('sends a test message and displays the model answer', async () => {
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: /Настройки/ }))
    fireEvent.change(screen.getByLabelText('Тестовое сообщение'), {
      target: { value: 'Привет, Ollama' }
    })
    fireEvent.click(screen.getByRole('button', { name: 'Отправить' }))

    expect(await screen.findByText('Ответ локальной модели')).toBeInTheDocument()
    expect(call).toHaveBeenCalledWith('ollama.chat', {
      message: 'Привет, Ollama'
    })
  })
})
