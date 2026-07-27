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
    return 'API ID должен быть положительным числом.'
  }
  if (!/^[a-fA-F0-9]{32}$/.test(values.apiHash)) {
    return 'API Hash должен содержать 32 шестнадцатеричных символа.'
  }
  if (!/^\+[1-9]\d{6,14}$/.test(values.phone.replace(/\s/g, ''))) {
    return 'Введите номер в международном формате, например +35799123456.'
  }
  return null
}

export function parseDesktopError(error: unknown): string {
  if (!(error instanceof Error)) return 'Произошла ошибка.'
  const marker = error.message.indexOf('{"code"')
  if (marker >= 0) {
    try {
      const parsed = JSON.parse(error.message.slice(marker)) as {
        code?: string
        message?: string
      }
      if (parsed.message && WORKER_MESSAGE_TRANSLATIONS[parsed.message]) {
        return WORKER_MESSAGE_TRANSLATIONS[parsed.message]
      }
      if (parsed.code && ERROR_CODE_MESSAGES[parsed.code]) {
        return ERROR_CODE_MESSAGES[parsed.code]
      }
    } catch {
      // Используем безопасное общее сообщение ниже.
    }
  }
  return 'Произошла ошибка. Повторите действие.'
}

const ERROR_CODE_MESSAGES: Record<string, string> = {
  authentication_required: 'Требуется повторный вход в Telegram.',
  telegram_transient: 'Telegram временно недоступен. Повторите попытку позже.',
  telegram_permanent: 'Telegram отклонил операцию.',
  telegram_flood_wait: 'Telegram ограничил частоту запросов. Повторите попытку позже.',
  validation_error: 'Проверьте введённые данные.',
  worker_exited: 'Локальный процесс Telegram завершился.',
  worker_unavailable: 'Локальный процесс Telegram не запущен.',
  worker_timeout: 'Локальный процесс Telegram не ответил вовремя.',
  frame_too_large: 'Запрос слишком большой.',
  method_not_allowed: 'Это действие недоступно.',
  invalid_request: 'Некорректный запрос.',
  desktop_error: 'Ошибка приложения.'
}

const WORKER_MESSAGE_TRANSLATIONS: Record<string, string> = {
  'Telegram sign-in is required': 'Требуется вход в Telegram.',
  'Request a Telegram login code first': 'Сначала запросите код входа Telegram.',
  'Telegram authorization is invalid or expired': 'Сессия Telegram недействительна или истекла.',
  'Telegram does not allow forwarding this message': 'Telegram запрещает пересылку этого сообщения.',
  'Telegram is temporarily unavailable': 'Telegram временно недоступен.',
  'Telegram rejected the requested operation': 'Telegram отклонил операцию.',
  'Telegram connection is unavailable': 'Нет подключения к Telegram.',
  'Telegram accepted the send but confirmation is pending': 'Сообщение отправлено, подтверждение ещё не получено.',
  'Choose a destination chat before monitoring': 'Перед запуском выберите чат назначения.',
  'Telegram session has expired': 'Сессия Telegram истекла.',
  'Settings values are required': 'Не указаны настройки.',
  'Destination chat cannot also be a source': 'Чат назначения не может быть источником.',
  'Destination must be an available writable chat': 'Выберите доступный чат, в который можно отправлять сообщения.',
  'Rule ID and values are required': 'Не указаны данные правила.',
  'Choose at least one source chat': 'Выберите хотя бы один источник.',
  'Create at least one enabled rule': 'Добавьте хотя бы одно включённое правило.',
  'Start Telegram sign-in first': 'Сначала начните вход в Telegram.',
  'Rule pattern cannot be empty': 'Текст правила не может быть пустым.',
  'Rule pattern cannot exceed 256 characters': 'Текст правила не может быть длиннее 256 символов.',
  'A hashtag may contain only letters, numbers, and underscores': 'Хэштег может содержать только буквы, цифры и знак подчёркивания.',
  'Whole-word matching is available only for keyword rules': 'Поиск целых слов доступен только для ключевых слов.',
  'Invalid initial scan mode': 'Некорректный режим начальной загрузки.',
  'Initial scan value must be between 1 and 10,000': 'Значение начальной загрузки должно быть от 1 до 10 000.',
  'Selected source chat is not available': 'Выбранный источник недоступен.',
  'Invalid rule type': 'Некорректный тип правила.',
  'Rule not found': 'Правило не найдено.'
}
