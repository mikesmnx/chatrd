import { useCallback, useEffect, useMemo, useState } from 'react'
import type {
  AppSnapshot,
  Peer,
  Rule,
  Source,
  Settings,
  TestingEvaluation
} from '../../shared/types'
import { parseDesktopError, reduceMonitorEvent, validateCredentials } from './domain'

type Page = 'dashboard' | 'sources' | 'rules' | 'testing' | 'settings'

export function App() {
  const [snapshot, setSnapshot] = useState<AppSnapshot | null>(null)
  const [fatalError, setFatalError] = useState<string | null>(null)

  const reload = useCallback(async () => {
    try {
      const value = await window.chatrd.call<AppSnapshot>('system.snapshot')
      setSnapshot(value)
      setFatalError(null)
    } catch (error) {
      setFatalError(parseDesktopError(error))
    }
  }, [])

  useEffect(() => {
    void reload()
  }, [reload])

  useEffect(
    () =>
      window.chatrd.onWorkerEvent((event) => {
        setSnapshot((current) => {
          if (!current) return current
          return {
            ...current,
            monitor: reduceMonitorEvent(
              { ...current.monitor, lastEvent: null },
              event
            )
          }
        })
      }),
    []
  )

  if (fatalError && !snapshot) {
    return (
      <Centered>
        <div className="error-card">
          <p className="eyebrow">Ошибка запуска</p>
          <h1>Не удалось запустить ChatRD</h1>
          <p>{fatalError}</p>
          <button onClick={() => void reload()}>Повторить</button>
        </div>
      </Centered>
    )
  }

  if (!snapshot) {
    return (
      <Centered>
        <div className="brand-loader">
          <Logo />
          <p>Запуск…</p>
        </div>
      </Centered>
    )
  }

  if (!snapshot.authenticated) {
    return <Onboarding onAuthorized={reload} />
  }

  return <Workspace snapshot={snapshot} onReload={reload} />
}

function Onboarding({ onAuthorized }: { onAuthorized: () => Promise<void> }) {
  const [step, setStep] = useState<'credentials' | 'code' | 'password'>('credentials')
  const [apiId, setApiId] = useState('')
  const [apiHash, setApiHash] = useState('')
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function startLogin(event: React.FormEvent) {
    event.preventDefault()
    const validation = validateCredentials({ apiId, apiHash, phone })
    if (validation) {
      setError(validation)
      return
    }
    setBusy(true)
    setError(null)
    try {
      await window.chatrd.call('auth.start', {
        api_id: Number(apiId),
        api_hash: apiHash,
        phone: phone.replace(/\s/g, '')
      })
      setStep('code')
    } catch (caught) {
      setError(parseDesktopError(caught))
    } finally {
      setBusy(false)
    }
  }

  async function submitCode(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const result = await window.chatrd.call<{ status: string }>('auth.submitCode', {
        code
      })
      setCode('')
      if (result.status === 'password_required') setStep('password')
      else await onAuthorized()
    } catch (caught) {
      setError(parseDesktopError(caught))
    } finally {
      setBusy(false)
    }
  }

  async function submitPassword(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await window.chatrd.call('auth.submitPassword', { password })
      setPassword('')
      await onAuthorized()
    } catch (caught) {
      setError(parseDesktopError(caught))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="onboarding">
      <aside className="onboarding-story">
        <Logo />
        <div>
          <p className="eyebrow light">Настройка</p>
          <h1>Подключение к Telegram</h1>
          <p>Войдите в Telegram, чтобы выбрать чаты и настроить правила.</p>
        </div>
        <div className="privacy-note">
          <LockIcon />
          <span>Сессия и настройки хранятся на этом компьютере.</span>
        </div>
      </aside>
      <main className="onboarding-panel">
        <div className="step-indicator">
          <span className={step === 'credentials' ? 'active' : 'done'}>1</span>
          <i />
          <span className={step === 'code' ? 'active' : step === 'password' ? 'done' : ''}>2</span>
          <i />
          <span className={step === 'password' ? 'active' : ''}>3</span>
        </div>

        {step === 'credentials' && (
          <form onSubmit={startLogin} className="form-card">
            <p className="eyebrow">Telegram</p>
            <h2>Вход в личный аккаунт</h2>
            <p className="muted">
              Создайте приложение API на{' '}
              <a href="https://my.telegram.org/apps" target="_blank" rel="noreferrer">
                my.telegram.org
              </a>{' '}
              и введите полученные данные.
            </p>
            <Field label="API ID">
              <input
                value={apiId}
                onChange={(event) => setApiId(event.target.value)}
                inputMode="numeric"
                autoComplete="off"
                placeholder="12345678"
              />
            </Field>
            <Field label="API Hash">
              <input
                value={apiHash}
                onChange={(event) => setApiHash(event.target.value)}
                autoComplete="off"
                spellCheck={false}
                placeholder="32 символа"
                type="password"
              />
            </Field>
            <Field label="Номер телефона">
              <input
                value={phone}
                onChange={(event) => setPhone(event.target.value)}
                autoComplete="tel"
                placeholder="+357 99 123456"
              />
            </Field>
            <FormError message={error} />
            <button className="primary wide" disabled={busy}>
              {busy ? 'Подключение…' : 'Получить код'}
            </button>
          </form>
        )}

        {step === 'code' && (
          <form onSubmit={submitCode} className="form-card compact">
            <p className="eyebrow">Проверка</p>
            <h2>Введите код из Telegram</h2>
            <p className="muted">Код обычно приходит в приложение Telegram.</p>
            <Field label="Код">
              <input
                className="code-input"
                value={code}
                onChange={(event) => setCode(event.target.value.replace(/\D/g, ''))}
                inputMode="numeric"
                autoFocus
                autoComplete="one-time-code"
              />
            </Field>
            <FormError message={error} />
            <button className="primary wide" disabled={busy || !code}>
              {busy ? 'Проверка…' : 'Продолжить'}
            </button>
          </form>
        )}

        {step === 'password' && (
          <form onSubmit={submitPassword} className="form-card compact">
            <p className="eyebrow">Двухэтапная аутентификация</p>
            <h2>Введите пароль Telegram</h2>
            <p className="muted">Пароль используется только для входа и не сохраняется.</p>
            <Field label="Пароль">
              <input
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                type="password"
                autoFocus
                autoComplete="current-password"
              />
            </Field>
            <FormError message={error} />
            <button className="primary wide" disabled={busy || !password}>
              {busy ? 'Вход…' : 'Войти'}
            </button>
          </form>
        )}
      </main>
    </div>
  )
}

function Workspace({
  snapshot,
  onReload
}: {
  snapshot: AppSnapshot
  onReload: () => Promise<void>
}) {
  const [page, setPage] = useState<Page>('dashboard')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function action(work: () => Promise<unknown>) {
    setBusy(true)
    setError(null)
    try {
      await work()
      await onReload()
    } catch (caught) {
      setError(parseDesktopError(caught))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <Logo />
        <nav aria-label="Основная навигация">
          <NavButton icon="◫" active={page === 'dashboard'} onClick={() => setPage('dashboard')}>
            Состояние
          </NavButton>
          <NavButton icon="⌁" active={page === 'sources'} onClick={() => setPage('sources')}>
            Источники
          </NavButton>
          <NavButton icon="✦" active={page === 'rules'} onClick={() => setPage('rules')}>
            Правила
          </NavButton>
          <NavButton icon="◇" active={page === 'testing'} onClick={() => setPage('testing')}>
            Тестирование
          </NavButton>
          <NavButton icon="⚙" active={page === 'settings'} onClick={() => setPage('settings')}>
            Настройки
          </NavButton>
        </nav>
        <div className="sidebar-foot">
          <StatusDot state={snapshot.monitor.state} />
          <div>
            <strong>{statusLabel(snapshot.monitor.state)}</strong>
            <span>Локальная обработка</span>
          </div>
        </div>
      </aside>

      <main className="content">
        {error && <div className="banner error">{error}</div>}
        {page === 'dashboard' && (
          <Dashboard snapshot={snapshot} busy={busy} action={action} />
        )}
        {page === 'sources' && <Sources snapshot={snapshot} action={action} />}
        {page === 'rules' && <Rules snapshot={snapshot} action={action} />}
        {page === 'testing' && <TestingPage snapshot={snapshot} />}
        {page === 'settings' && (
          <SettingsPage snapshot={snapshot} action={action} onReload={onReload} />
        )}
      </main>
    </div>
  )
}

function Dashboard({
  snapshot,
  busy,
  action
}: {
  snapshot: AppSnapshot
  busy: boolean
  action: (work: () => Promise<unknown>) => Promise<void>
}) {
  const total = Object.values(snapshot.monitor.counts).reduce((sum, count) => sum + count, 0)
  const configured = Boolean(
    snapshot.settings.destination_peer_id &&
      snapshot.sources.length &&
      (snapshot.rules.length || snapshot.settings.ai_enabled)
  )
  return (
    <>
      <PageHeader
        eyebrow="Состояние"
        title="Мониторинг"
        description="Обработка сообщений выполняется на этом компьютере."
      >
        {snapshot.monitor.state === 'monitoring' || snapshot.monitor.state === 'catching_up' ? (
          <button
            className="secondary"
            disabled={busy}
            onClick={() => action(() => window.chatrd.call('monitor.pause'))}
          >
            Приостановить
          </button>
        ) : (
          <button
            className="primary"
            disabled={busy || !configured}
            onClick={() => action(() => window.chatrd.call('monitor.start'))}
          >
            {busy ? 'Запуск…' : 'Запустить'}
          </button>
        )}
      </PageHeader>

      {!configured && (
        <div className="banner info">
          Перед запуском выберите чат назначения, источник и добавьте правило или включите ИИ-фильтр.
        </div>
      )}

      <section className="hero-status">
        <div>
          <span className={`pulse ${snapshot.monitor.state}`} />
          <p className="eyebrow">{statusLabel(snapshot.monitor.state)}</p>
          <h2>
            {snapshot.monitor.state === 'monitoring'
              ? 'Мониторинг запущен'
              : snapshot.monitor.state === 'catching_up'
                ? 'Загрузка истории'
                : 'Мониторинг приостановлен'}
          </h2>
          <p className="muted">
            {formatCount(snapshot.sources.length, ['источник', 'источника', 'источников'])} ·{' '}
            {formatCount(snapshot.rules.length, ['правило', 'правила', 'правил'])}
          </p>
        </div>
        <div className="radar" aria-hidden="true">
          <i />
          <i />
          <i />
          <span />
        </div>
      </section>

      <section className="stats-grid">
        <Stat label="Отправлено" value={snapshot.monitor.counts.sent ?? 0} tone="green" />
        <Stat label="Проверено" value={total} tone="ink" />
        <Stat label="Без совпадений" value={snapshot.monitor.counts.no_match ?? 0} tone="sand" />
        <Stat
          label="Ошибки"
          value={snapshot.monitor.counts.permanently_failed ?? 0}
          tone="red"
        />
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Источники</p>
            <h3>Выбранные чаты</h3>
          </div>
        </div>
        {snapshot.sources.length === 0 ? (
          <Empty title="Нет источников" text="Добавьте чаты на странице «Источники»." />
        ) : (
          <div className="source-list">
            {snapshot.sources.map((source) => (
              <div className="source-row" key={source.peer_id}>
                <Avatar name={source.display_name} />
                <div className="grow">
                  <strong>{source.display_name}</strong>
                  <span>
                    {source.last_terminal_message_id
                      ? `Последнее сообщение: ${source.last_terminal_message_id}`
                      : 'Ещё не запускался'}
                  </span>
                </div>
                <span className={`pill ${source.error_code ? 'danger' : source.enabled ? 'ok' : ''}`}>
                  {source.error_code ? 'Ошибка' : source.enabled ? 'Включён' : 'Выключен'}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>
    </>
  )
}

function Sources({
  snapshot,
  action
}: {
  snapshot: AppSnapshot
  action: (work: () => Promise<unknown>) => Promise<void>
}) {
  const [peers, setPeers] = useState<Peer[]>([])
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const sourceIds = useMemo(() => new Set(snapshot.sources.map((item) => item.peer_id)), [snapshot.sources])

  const loadPeers = useCallback(() => {
    setLoading(true)
    setLoadError(null)
    window.chatrd
      .call<Peer[]>('chats.list')
      .then(setPeers)
      .catch((error) => {
        setPeers([])
        setLoadError(parseDesktopError(error))
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    loadPeers()
  }, [loadPeers])

  const destination = peers.find((peer) => peer.peer_id === snapshot.settings.destination_peer_id)
  return (
    <>
      <PageHeader
        eyebrow="Чаты"
        title="Источники и назначение"
        description="Выберите чат для отправки результатов и чаты для мониторинга."
      />
      <section className="panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Шаг 1</p>
            <h3>Чат назначения</h3>
          </div>
          {destination && <span className="pill ok">Выбран</span>}
        </div>
        {loadError && (
          <div className="inline-load-error" role="alert">
            <span>
              <strong>Не удалось загрузить чаты Telegram.</strong>
              {loadError}
            </span>
            <button className="secondary" onClick={loadPeers}>Повторить</button>
          </div>
        )}
        <label className="select-label">
          Чат назначения
          <select
            value={snapshot.settings.destination_peer_id ?? ''}
            onChange={(event) =>
              action(() =>
                window.chatrd.call('settings.update', {
                  values: { destination_peer_id: Number(event.target.value) }
                })
              )
            }
          >
            <option value="" disabled>
              Выберите чат
            </option>
            {peers
              .filter((peer) => peer.can_write && !sourceIds.has(peer.peer_id))
              .map((peer) => (
                <option key={peer.peer_id} value={peer.peer_id}>
                  {peer.display_name}
                </option>
              ))}
          </select>
        </label>
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Шаг 2</p>
            <h3>Источники</h3>
          </div>
          <span className="muted small">{formatCount(sourceIds.size, ['выбран', 'выбрано', 'выбрано'])}</span>
        </div>
        {loading ? (
          <Empty title="Загрузка чатов…" text="Подождите." />
        ) : loadError ? (
          <Empty title="Источники недоступны" text="Проверьте ошибку выше и повторите загрузку." />
        ) : peers.length === 0 ? (
          <div className="empty">
            <span>· · ·</span>
            <strong>Чаты не найдены</strong>
            <p>Обновите список или проверьте, что в аккаунте есть чаты.</p>
            <button className="secondary empty-action" onClick={loadPeers}>Обновить</button>
          </div>
        ) : (
          <div className="chat-grid">
            {peers
              .filter((peer) => peer.peer_id !== snapshot.settings.destination_peer_id)
              .map((peer) => {
                const source = snapshot.sources.find((item) => item.peer_id === peer.peer_id)
                return (
                  <SourceCard
                    key={peer.peer_id}
                    peer={peer}
                    source={source}
                    onToggle={(enabled) =>
                      action(() =>
                        enabled
                          ? window.chatrd.call('sources.upsert', {
                              peer_id: peer.peer_id,
                              enabled: true,
                              initial_scan_mode: 'now'
                            })
                          : window.chatrd.call('sources.remove', { peer_id: peer.peer_id })
                      )
                    }
                    onPolicy={(mode, value) =>
                      action(() =>
                        window.chatrd.call('sources.upsert', {
                          peer_id: peer.peer_id,
                          enabled: true,
                          initial_scan_mode: mode,
                          initial_scan_value: value
                        })
                      )
                    }
                  />
                )
              })}
          </div>
        )}
      </section>
    </>
  )
}

function SourceCard({
  peer,
  source,
  onToggle,
  onPolicy
}: {
  peer: Peer
  source?: Source
  onToggle: (enabled: boolean) => void
  onPolicy: (mode: Source['initial_scan_mode'], value: number | null) => void
}) {
  return (
    <div className={`chat-card ${source ? 'selected' : ''}`}>
      <label className="chat-card-main">
        <input
          type="checkbox"
          checked={Boolean(source)}
          onChange={(event) => onToggle(event.target.checked)}
        />
        <Avatar name={peer.display_name} />
        <span className="grow">
          <strong>{peer.display_name}</strong>
          <small>{peerTypeLabel(peer.peer_type)}</small>
        </span>
      </label>
      {source && source.last_terminal_message_id === null && (
        <div className="scan-policy">
          <select
            aria-label={`Начальная загрузка для ${peer.display_name}`}
            value={source.initial_scan_mode}
            onChange={(event) => {
              const mode = event.target.value as Source['initial_scan_mode']
              onPolicy(mode, mode === 'now' ? null : 24)
            }}
          >
            <option value="now">Только новые сообщения</option>
            <option value="latest_count">Последние сообщения</option>
            <option value="recent_window">За последние часы</option>
          </select>
          {source.initial_scan_mode !== 'now' && (
            <input
              aria-label="Количество для начальной загрузки"
              type="number"
              min="1"
              max="10000"
              key={`${source.peer_id}-${source.initial_scan_mode}-${source.initial_scan_value}`}
              defaultValue={source.initial_scan_value ?? 24}
              onBlur={(event) =>
                onPolicy(source.initial_scan_mode, Number(event.target.value))
              }
            />
          )}
        </div>
      )}
    </div>
  )
}

function Rules({
  snapshot,
  action
}: {
  snapshot: AppSnapshot
  action: (work: () => Promise<unknown>) => Promise<void>
}) {
  const [pattern, setPattern] = useState('')
  const [type, setType] = useState<Rule['type']>('keyword')
  const [scope, setScope] = useState<string>('global')
  const [wholeWord, setWholeWord] = useState(false)

  async function create(event: React.FormEvent) {
    event.preventDefault()
    if (!pattern.trim()) return
    await action(() =>
      window.chatrd.call('rules.create', {
        source_peer_id: scope === 'global' ? null : Number(scope),
        type,
        pattern,
        whole_word: type === 'keyword' && wholeWord
      })
    )
    setPattern('')
  }

  return (
    <>
      <PageHeader
        eyebrow="Фильтры"
        title="Правила"
        description="Сообщение отправляется, если сработало хотя бы одно правило."
      />
      <section className="rule-layout">
        <form className="panel rule-builder" onSubmit={create}>
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Новое правило</p>
              <h3>Добавить правило</h3>
            </div>
          </div>
          <Field label="Тип">
            <div className="segmented">
              {(['keyword', 'phrase', 'hashtag'] as const).map((value) => (
                <button
                  type="button"
                  className={type === value ? 'active' : ''}
                  onClick={() => {
                    setType(value)
                    if (value !== 'keyword') setWholeWord(false)
                  }}
                  key={value}
                >
                  {ruleTypeLabel(value)}
                </button>
              ))}
            </div>
          </Field>
          <Field label={type === 'hashtag' ? 'Хэштег' : 'Текст'}>
            <input
              value={pattern}
              onChange={(event) => setPattern(event.target.value)}
              placeholder={type === 'hashtag' ? '#решение' : 'выпуск версии'}
              maxLength={256}
            />
          </Field>
          <Field label="Применить к">
            <select value={scope} onChange={(event) => setScope(event.target.value)}>
              <option value="global">Всем источникам</option>
              {snapshot.sources.map((source) => (
                <option key={source.peer_id} value={source.peer_id}>
                  {source.display_name}
                </option>
              ))}
            </select>
          </Field>
          {type === 'keyword' && (
            <label className="toggle-row">
              <input
                type="checkbox"
                checked={wholeWord}
                onChange={(event) => setWholeWord(event.target.checked)}
              />
              <span>
                <strong>Только целые слова</strong>
                <small>«кот» не совпадёт со словом «котёнок»</small>
              </span>
            </label>
          )}
          <button className="primary wide" disabled={!pattern.trim()}>
            Добавить
          </button>
        </form>

        <section className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Список</p>
              <h3>{formatCount(snapshot.rules.length, ['правило', 'правила', 'правил'])}</h3>
            </div>
          </div>
          {snapshot.rules.length === 0 ? (
            <Empty title="Нет правил" text="Добавьте ключевое слово, фразу или хэштег." />
          ) : (
            <div className="rule-list">
              {snapshot.rules.map((rule) => {
                const source = snapshot.sources.find(
                  (item) => item.peer_id === rule.source_peer_id
                )
                return (
                  <div className={`rule-row ${rule.enabled ? '' : 'disabled'}`} key={rule.id}>
                    <span className="rule-glyph">{rule.type === 'hashtag' ? '#' : '“'}</span>
                    <div className="grow">
                      <strong>{rule.pattern}</strong>
                      <span>
                        {source?.display_name ?? 'Все источники'} · {ruleTypeLabel(rule.type)}
                        {rule.whole_word ? ' · целое слово' : ''}
                      </span>
                    </div>
                    <label className="switch" title={rule.enabled ? 'Выключить правило' : 'Включить правило'}>
                      <input
                        type="checkbox"
                        checked={rule.enabled}
                        onChange={(event) =>
                          action(() =>
                            window.chatrd.call('rules.update', {
                              id: rule.id,
                              values: { enabled: event.target.checked }
                            })
                          )
                        }
                      />
                      <i />
                    </label>
                    <button
                      className="icon-button danger-text"
                      aria-label={`Удалить ${rule.pattern}`}
                      onClick={() =>
                        action(() => window.chatrd.call('rules.delete', { id: rule.id }))
                      }
                    >
                      ×
                    </button>
                  </div>
                )
              })}
            </div>
          )}
        </section>
      </section>
    </>
  )
}

function TestingPage({ snapshot }: { snapshot: AppSnapshot }) {
  const [sourcePeerId, setSourcePeerId] = useState(
    snapshot.sources[0] ? String(snapshot.sources[0].peer_id) : ''
  )
  const [message, setMessage] = useState('')
  const [result, setResult] = useState<TestingEvaluation | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function evaluate(event: React.FormEvent) {
    event.preventDefault()
    if (!sourcePeerId || !message.trim()) return
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const evaluation = await window.chatrd.call<TestingEvaluation>('testing.evaluate', {
        source_peer_id: Number(sourcePeerId),
        message
      })
      setResult(evaluation)
    } catch (caught) {
      setError(parseDesktopError(caught))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Проверка правил"
        title="Тестирование"
        description="Проверьте, какие правила сработают для сообщения из выбранного источника. Сообщение никуда не отправляется и не сохраняется."
      />
      <section className="testing-layout">
        <form className="panel testing-composer" onSubmit={evaluate}>
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Тестовое сообщение</p>
              <h3>Составить сообщение</h3>
            </div>
            <span className="pill">Без отправки</span>
          </div>
          {snapshot.sources.length === 0 ? (
            <Empty
              title="Нет источников"
              text="Сначала добавьте хотя бы один чат на странице «Источники»."
            />
          ) : (
            <>
              <Field label="Источник">
                <select
                  value={sourcePeerId}
                  onChange={(event) => {
                    setSourcePeerId(event.target.value)
                    setResult(null)
                  }}
                >
                  {snapshot.sources.map((source) => (
                    <option key={source.peer_id} value={source.peer_id}>
                      {source.display_name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Сообщение">
                <textarea
                  value={message}
                  onChange={(event) => {
                    setMessage(event.target.value)
                    setResult(null)
                  }}
                  placeholder="Введите текст сообщения или подпись к медиа…"
                  rows={9}
                  maxLength={8000}
                />
              </Field>
              <FormError message={error} />
              <button className="primary wide" disabled={busy || !message.trim()}>
                {busy ? 'Проверка…' : 'Отправить тест'}
              </button>
            </>
          )}
        </form>

        <section className="panel testing-result" aria-live="polite">
          {!result ? (
            <Empty
              title="Результат появится здесь"
              text="Выберите источник, введите сообщение и запустите проверку."
            />
          ) : (
            <>
              <div className={`testing-decision ${result.would_send ? 'send' : 'skip'}`}>
                <span aria-hidden="true">{result.would_send ? '✓' : '×'}</span>
                <div>
                  <p className="eyebrow">Результат</p>
                  <h2>{testingDecisionTitle(result)}</h2>
                  <p>{testingDecisionDescription(result)}</p>
                </div>
              </div>
              <div className="testing-rule-summary">
                <strong>
                  {formatCount(
                    result.evaluated_rules.filter((rule) => rule.matched).length,
                    ['сработало', 'сработали', 'сработали']
                  )}
                </strong>
                <span>
                  из {formatCount(result.evaluated_rules.length, ['правила', 'правил', 'правил'])}
                </span>
              </div>
              {result.evaluated_rules.length === 0 ? (
                <Empty
                  title="Нет применимых правил"
                  text="Для этого источника нет включённых глобальных или локальных правил."
                />
              ) : (
                <div className="testing-rule-list">
                  {result.evaluated_rules.map((rule) => {
                    const source = snapshot.sources.find(
                      (item) => item.peer_id === rule.source_peer_id
                    )
                    return (
                      <div className={`testing-rule ${rule.matched ? 'matched' : ''}`} key={rule.id}>
                        <span className="testing-rule-mark" aria-hidden="true">
                          {rule.matched ? '✓' : '–'}
                        </span>
                        <div className="grow">
                          <strong>{rule.pattern}</strong>
                          <span>
                            {source?.display_name ?? 'Все источники'} · {ruleTypeLabel(rule.type)}
                            {rule.whole_word ? ' · целое слово' : ''}
                            {rule.case_sensitive ? ' · с учётом регистра' : ''}
                          </span>
                        </div>
                        <span className={`pill ${rule.matched ? 'ok' : ''}`}>
                          {rule.matched ? 'Сработало' : 'Не сработало'}
                        </span>
                      </div>
                    )
                  })}
                </div>
              )}
            </>
          )}
        </section>
      </section>
    </>
  )
}

function SettingsPage({
  snapshot,
  action,
  onReload
}: {
  snapshot: AppSnapshot
  action: (work: () => Promise<unknown>) => Promise<void>
  onReload: () => Promise<void>
}) {
  const [ollama, setOllama] = useState(() => ollamaForm(snapshot.settings))
  const [testing, setTesting] = useState(false)
  const [testMessage, setTestMessage] = useState('')
  const [testStatus, setTestStatus] = useState<string | null>(null)
  const [testError, setTestError] = useState(false)

  useEffect(() => {
    setOllama(ollamaForm(snapshot.settings))
  }, [snapshot.settings])

  function updateOllama<K extends keyof typeof ollama>(key: K, value: (typeof ollama)[K]) {
    setOllama((current) => ({ ...current, [key]: value }))
    setTestStatus(null)
  }

  function ollamaValues(): Partial<Settings> {
    return {
      ai_enabled: ollama.ai_enabled,
      ollama_base_url: ollama.ollama_base_url,
      ollama_model: ollama.ollama_model,
      ollama_prompt: ollama.ollama_prompt,
      ollama_timeout_seconds: 120,
      ollama_temperature: 0
    }
  }

  async function saveOllama(event: React.FormEvent) {
    event.preventDefault()
    setTestStatus(null)
    await action(() =>
      window.chatrd.call('settings.update', { values: ollamaValues() })
    )
  }

  async function testOllama() {
    if (!testMessage.trim()) return
    setTesting(true)
    setTestStatus(null)
    setTestError(false)
    try {
      await window.chatrd.call('settings.update', { values: ollamaValues() })
      const result = await window.chatrd.call<{ model: string; message: string }>(
        'ollama.chat',
        { message: testMessage }
      )
      await onReload()
      setTestStatus(result.message)
    } catch (caught) {
      setTestError(true)
      setTestStatus(parseDesktopError(caught))
    } finally {
      setTesting(false)
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Параметры"
        title="Настройки"
        description="Формат отправки, локальная ИИ-фильтрация и сессия Telegram."
      />
      <section className="panel settings-panel">
        <div>
          <h3>Формат отправки</h3>
          <p className="muted">
            Копия содержит источник, автора, время, сработавшие правила и ссылку.
          </p>
        </div>
        <div className="choice-grid">
          {(['copy', 'forward'] as const).map((mode) => (
            <label className={`choice-card ${snapshot.settings.delivery_mode === mode ? 'selected' : ''}`} key={mode}>
              <input
                type="radio"
                name="delivery"
                value={mode}
                checked={snapshot.settings.delivery_mode === mode}
                onChange={() =>
                  action(() =>
                    window.chatrd.call('settings.update', {
                      values: { delivery_mode: mode }
                    })
                  )
                }
              />
              <strong>{mode === 'copy' ? 'Форматированная копия' : 'Пересылка Telegram'}</strong>
              <span>
                {mode === 'copy'
                  ? 'Текст с информацией об источнике'
                  : 'Исходное сообщение вместе с медиа'}
              </span>
            </label>
          ))}
        </div>
      </section>
      <form className="panel ollama-panel" onSubmit={saveOllama}>
        <div className="panel-heading ollama-heading">
          <div>
            <p className="eyebrow">Локальная модель</p>
            <h3>Ollama · gpt-oss:20b</h3>
          </div>
          <label className="switch labeled-switch">
            <input
              type="checkbox"
              checked={ollama.ai_enabled}
              onChange={(event) => updateOllama('ai_enabled', event.target.checked)}
            />
            <i />
            <span>{ollama.ai_enabled ? 'Включено' : 'Выключено'}</span>
          </label>
        </div>

        <div className="ollama-form-grid">
          <Field label="Адрес сервера Ollama">
            <input
              type="url"
              value={ollama.ollama_base_url}
              onChange={(event) => updateOllama('ollama_base_url', event.target.value)}
              placeholder="http://127.0.0.1:11434"
              required
              spellCheck={false}
            />
          </Field>
          <Field label="Модель">
            <input
              value={ollama.ollama_model}
              onChange={(event) => updateOllama('ollama_model', event.target.value)}
              placeholder="gpt-oss:20b"
              required
              spellCheck={false}
            />
          </Field>
        </div>

        <div className="ollama-actions">
          <button className="primary">Сохранить</button>
        </div>

        <section className="ollama-test">
          <div>
            <p className="eyebrow">Проверка</p>
            <h3>Диалог с моделью</h3>
          </div>
          <Field label="Тестовое сообщение">
            <textarea
              value={testMessage}
              onChange={(event) => {
                setTestMessage(event.target.value)
                setTestStatus(null)
              }}
              placeholder="Напишите сообщение для gpt-oss:20b"
              maxLength={8000}
              rows={3}
            />
          </Field>
          <button
            type="button"
            className="secondary ollama-send"
            disabled={testing || !testMessage.trim()}
            onClick={() => void testOllama()}
          >
            {testing ? 'Ожидание ответа…' : 'Отправить'}
          </button>
          {testStatus && (
            <div className={`connection-status ${testError ? 'error' : 'success'}`} role="status">
              {testStatus}
            </div>
          )}
        </section>
      </form>
      <section className="panel danger-zone">
        <div>
          <h3>Сессия Telegram</h3>
          <p className="muted">
            При выходе сессия будет отозвана в Telegram и удалена с этого компьютера.
          </p>
        </div>
        <button
          className="danger-button"
          onClick={() => {
            if (window.confirm('Выйти из Telegram на этом компьютере?')) {
              void action(() => window.chatrd.call('auth.logout'))
            }
          }}
        >
          Выйти
        </button>
      </section>
      <div className="privacy-footer">
        <LockIcon />
        <p>
          Тексты сообщений не сохраняются в локальной базе данных и журналах.
        </p>
      </div>
    </>
  )
}

function ollamaForm(settings: Settings) {
  return {
    ai_enabled: settings.ai_enabled,
    ollama_base_url: settings.ollama_base_url,
    ollama_model: settings.ollama_model,
    ollama_prompt: settings.ollama_prompt
  }
}

function PageHeader({
  eyebrow,
  title,
  description,
  children
}: {
  eyebrow: string
  title: string
  description: string
  children?: React.ReactNode
}) {
  return (
    <header className="page-header">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {children && <div className="page-actions">{children}</div>}
    </header>
  )
}

function Centered({ children }: { children: React.ReactNode }) {
  return <main className="centered">{children}</main>
}

function Logo() {
  return (
    <div className="logo" aria-label="ChatRD">
      <span>CR</span>
      <strong>ChatRD</strong>
    </div>
  )
}

function LockIcon() {
  return <span className="lock-icon" aria-hidden="true">⌾</span>
}

function NavButton({
  active,
  icon,
  onClick,
  children
}: {
  active: boolean
  icon: string
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button className={active ? 'active' : ''} onClick={onClick}>
      <span aria-hidden="true">{icon}</span>
      {children}
    </button>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  )
}

function FormError({ message }: { message: string | null }) {
  return message ? <div className="form-error" role="alert">{message}</div> : null
}

function StatusDot({ state }: { state: string }) {
  return <span className={`status-dot ${state}`} aria-hidden="true" />
}

function statusLabel(state: string): string {
  return {
    monitoring: 'Работает',
    catching_up: 'Загрузка истории',
    paused: 'Приостановлен',
    offline: 'Нет подключения',
    action_required: 'Требуется действие'
  }[state] ?? 'Запуск'
}

function ruleTypeLabel(type: Rule['type']): string {
  return {
    keyword: 'Ключевое слово',
    phrase: 'Фраза',
    hashtag: 'Хэштег'
  }[type]
}

function testingDecisionTitle(result: TestingEvaluation): string {
  if (result.would_send) return 'Будет отправлено в итоговый чат'
  if (result.reason === 'destination_missing') return 'Правила сработали, но отправка невозможна'
  if (result.reason === 'source_disabled') return 'Источник выключен'
  return 'Не будет отправлено в итоговый чат'
}

function testingDecisionDescription(result: TestingEvaluation): string {
  if (result.would_send) {
    return result.delivery_mode === 'forward'
      ? 'При работающем мониторинге Telegram перешлёт исходное сообщение.'
      : 'При работающем мониторинге ChatRD отправит форматированную копию.'
  }
  if (result.reason === 'destination_missing') {
    return 'Выберите итоговый чат на странице «Источники».'
  }
  if (result.reason === 'source_disabled') {
    return 'Сообщения из выключенного источника не обрабатываются.'
  }
  return 'Ни одно включённое правило для этого источника не совпало.'
}

function peerTypeLabel(type: string): string {
  return {
    user: 'Личный чат',
    group: 'Группа',
    supergroup: 'Супергруппа',
    channel: 'Канал'
  }[type] ?? 'Чат'
}

function formatCount(count: number, forms: [string, string, string]): string {
  const lastTwo = count % 100
  const last = count % 10
  const form = lastTwo >= 11 && lastTwo <= 14
    ? forms[2]
    : last === 1
      ? forms[0]
      : last >= 2 && last <= 4
        ? forms[1]
        : forms[2]
  return `${count} ${form}`
}

function Stat({
  label,
  value,
  tone
}: {
  label: string
  value: number
  tone: string
}) {
  return (
    <article className={`stat ${tone}`}>
      <span>{label}</span>
      <strong>{value.toLocaleString('ru-RU')}</strong>
    </article>
  )
}

function Avatar({ name }: { name: string }) {
  const letters = name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase()
  return <span className="avatar">{letters || '?'}</span>
}

function Empty({ title, text }: { title: string; text: string }) {
  return (
    <div className="empty">
      <span>· · ·</span>
      <strong>{title}</strong>
      <p>{text}</p>
    </div>
  )
}
