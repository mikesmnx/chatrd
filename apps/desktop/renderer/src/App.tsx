import { useCallback, useEffect, useMemo, useState } from 'react'
import type {
  AppSnapshot,
  Peer,
  Rule,
  Source
} from '../../shared/types'
import { parseDesktopError, reduceMonitorEvent, validateCredentials } from './domain'

type Page = 'dashboard' | 'sources' | 'rules' | 'settings'

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
          <p className="eyebrow">Local worker unavailable</p>
          <h1>ChatRD could not start</h1>
          <p>{fatalError}</p>
          <button onClick={() => void reload()}>Try again</button>
        </div>
      </Centered>
    )
  }

  if (!snapshot) {
    return (
      <Centered>
        <div className="brand-loader">
          <Logo />
          <p>Starting your private workspace…</p>
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
          <p className="eyebrow light">Private by design</p>
          <h1>The messages that matter, gathered quietly.</h1>
          <p>
            ChatRD watches your chosen Telegram chats, matches your rules locally,
            and creates one calm summary stream.
          </p>
        </div>
        <div className="privacy-note">
          <LockIcon />
          <span>No cloud backend. No message-body logs. Your account stays on this device.</span>
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
            <p className="eyebrow">Connect Telegram</p>
            <h2>Sign in with your personal account</h2>
            <p className="muted">
              Create an API application at{' '}
              <a href="https://my.telegram.org/apps" target="_blank" rel="noreferrer">
                my.telegram.org
              </a>{' '}
              and enter its credentials below.
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
            <Field label="API hash">
              <input
                value={apiHash}
                onChange={(event) => setApiHash(event.target.value)}
                autoComplete="off"
                spellCheck={false}
                placeholder="32-character hash"
                type="password"
              />
            </Field>
            <Field label="Phone number">
              <input
                value={phone}
                onChange={(event) => setPhone(event.target.value)}
                autoComplete="tel"
                placeholder="+357 99 123456"
              />
            </Field>
            <FormError message={error} />
            <button className="primary wide" disabled={busy}>
              {busy ? 'Connecting…' : 'Send Telegram code'}
            </button>
          </form>
        )}

        {step === 'code' && (
          <form onSubmit={submitCode} className="form-card compact">
            <p className="eyebrow">Verification</p>
            <h2>Enter the code from Telegram</h2>
            <p className="muted">Telegram usually sends this code inside the Telegram app.</p>
            <Field label="Login code">
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
              {busy ? 'Checking…' : 'Continue'}
            </button>
          </form>
        )}

        {step === 'password' && (
          <form onSubmit={submitPassword} className="form-card compact">
            <p className="eyebrow">Two-step verification</p>
            <h2>Enter your Telegram password</h2>
            <p className="muted">It is used for this request and is never saved.</p>
            <Field label="Password">
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
              {busy ? 'Signing in…' : 'Finish sign-in'}
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
        <nav aria-label="Main navigation">
          <NavButton icon="◫" active={page === 'dashboard'} onClick={() => setPage('dashboard')}>
            Dashboard
          </NavButton>
          <NavButton icon="⌁" active={page === 'sources'} onClick={() => setPage('sources')}>
            Sources
          </NavButton>
          <NavButton icon="✦" active={page === 'rules'} onClick={() => setPage('rules')}>
            Rules
          </NavButton>
          <NavButton icon="⚙" active={page === 'settings'} onClick={() => setPage('settings')}>
            Settings
          </NavButton>
        </nav>
        <div className="sidebar-foot">
          <StatusDot state={snapshot.monitor.state} />
          <div>
            <strong>{statusLabel(snapshot.monitor.state)}</strong>
            <span>Local processing</span>
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
        {page === 'settings' && (
          <SettingsPage snapshot={snapshot} action={action} />
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
    snapshot.settings.destination_peer_id && snapshot.sources.length && snapshot.rules.length
  )
  return (
    <>
      <PageHeader
        eyebrow="Overview"
        title="Your quiet Telegram radar"
        description="Messages are evaluated on this device and delivered only to your selected summary chat."
      >
        {snapshot.monitor.state === 'monitoring' || snapshot.monitor.state === 'catching_up' ? (
          <button
            className="secondary"
            disabled={busy}
            onClick={() => action(() => window.chatrd.call('monitor.pause'))}
          >
            Pause monitoring
          </button>
        ) : (
          <button
            className="primary"
            disabled={busy || !configured}
            onClick={() => action(() => window.chatrd.call('monitor.start'))}
          >
            {busy ? 'Starting…' : 'Start monitoring'}
          </button>
        )}
      </PageHeader>

      {!configured && (
        <div className="banner info">
          Choose a destination, at least one source, and one rule before starting.
        </div>
      )}

      <section className="hero-status">
        <div>
          <span className={`pulse ${snapshot.monitor.state}`} />
          <p className="eyebrow">{statusLabel(snapshot.monitor.state)}</p>
          <h2>
            {snapshot.monitor.state === 'monitoring'
              ? 'Listening for what matters'
              : snapshot.monitor.state === 'catching_up'
                ? 'Catching up safely'
                : 'Monitoring is paused'}
          </h2>
          <p className="muted">
            {snapshot.sources.length} source{snapshot.sources.length === 1 ? '' : 's'} ·{' '}
            {snapshot.rules.length} rule{snapshot.rules.length === 1 ? '' : 's'}
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
        <Stat label="Sent to summary" value={snapshot.monitor.counts.sent ?? 0} tone="green" />
        <Stat label="Checked locally" value={total} tone="ink" />
        <Stat label="No match" value={snapshot.monitor.counts.no_match ?? 0} tone="sand" />
        <Stat
          label="Needs attention"
          value={snapshot.monitor.counts.permanently_failed ?? 0}
          tone="red"
        />
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Source health</p>
            <h3>Monitored chats</h3>
          </div>
        </div>
        {snapshot.sources.length === 0 ? (
          <Empty title="No sources yet" text="Add source chats from the Sources page." />
        ) : (
          <div className="source-list">
            {snapshot.sources.map((source) => (
              <div className="source-row" key={source.peer_id}>
                <Avatar name={source.display_name} />
                <div className="grow">
                  <strong>{source.display_name}</strong>
                  <span>
                    {source.last_terminal_message_id
                      ? `Cursor ${source.last_terminal_message_id}`
                      : 'Waiting for first run'}
                  </span>
                </div>
                <span className={`pill ${source.error_code ? 'danger' : source.enabled ? 'ok' : ''}`}>
                  {source.error_code ? 'Action required' : source.enabled ? 'Enabled' : 'Disabled'}
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
        eyebrow="Routing"
        title="Choose where to listen"
        description="The destination receives summaries. Source chats are watched using stable Telegram IDs."
      />
      <section className="panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Step 1</p>
            <h3>Summary destination</h3>
          </div>
          {destination && <span className="pill ok">Writable</span>}
        </div>
        {loadError && (
          <div className="inline-load-error" role="alert">
            <span>
              <strong>Telegram chats could not be loaded.</strong>
              {loadError}
            </span>
            <button className="secondary" onClick={loadPeers}>Try again</button>
          </div>
        )}
        <label className="select-label">
          Destination chat
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
              Select a writable chat
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
            <p className="eyebrow">Step 2</p>
            <h3>Monitored sources</h3>
          </div>
          <span className="muted small">{sourceIds.size} selected</span>
        </div>
        {loading ? (
          <Empty title="Loading Telegram chats…" text="This can take a moment for larger accounts." />
        ) : loadError ? (
          <Empty title="Sources unavailable" text="Retry after resolving the Telegram connection error above." />
        ) : peers.length === 0 ? (
          <div className="empty">
            <span>· · ·</span>
            <strong>No Telegram chats returned</strong>
            <p>Refresh the list or confirm this account has at least one Telegram conversation.</p>
            <button className="secondary empty-action" onClick={loadPeers}>Refresh chats</button>
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
          <small>{peer.peer_type}</small>
        </span>
      </label>
      {source && source.last_terminal_message_id === null && (
        <div className="scan-policy">
          <select
            aria-label={`Initial scan for ${peer.display_name}`}
            value={source.initial_scan_mode}
            onChange={(event) => {
              const mode = event.target.value as Source['initial_scan_mode']
              onPolicy(mode, mode === 'now' ? null : 24)
            }}
          >
            <option value="now">Start from now</option>
            <option value="latest_count">Latest messages</option>
            <option value="recent_window">Recent hours</option>
          </select>
          {source.initial_scan_mode !== 'now' && (
            <input
              aria-label="Scan amount"
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
        eyebrow="Filters"
        title="Define what matters"
        description="Rules are literal, local, and OR-combined. One message is delivered even when several rules match."
      />
      <section className="rule-layout">
        <form className="panel rule-builder" onSubmit={create}>
          <div className="panel-heading">
            <div>
              <p className="eyebrow">New rule</p>
              <h3>Add a local filter</h3>
            </div>
          </div>
          <Field label="Rule type">
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
                  {value}
                </button>
              ))}
            </div>
          </Field>
          <Field label={type === 'hashtag' ? 'Hashtag' : 'Text'}>
            <input
              value={pattern}
              onChange={(event) => setPattern(event.target.value)}
              placeholder={type === 'hashtag' ? '#decision' : 'production release'}
              maxLength={256}
            />
          </Field>
          <Field label="Scope">
            <select value={scope} onChange={(event) => setScope(event.target.value)}>
              <option value="global">All monitored sources</option>
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
                <strong>Whole words only</strong>
                <small>“cat” will not match “concatenate”</small>
              </span>
            </label>
          )}
          <button className="primary wide" disabled={!pattern.trim()}>
            Add rule
          </button>
        </form>

        <section className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Active set</p>
              <h3>{snapshot.rules.length} configured rules</h3>
            </div>
          </div>
          {snapshot.rules.length === 0 ? (
            <Empty title="No rules yet" text="Add a keyword, phrase, or hashtag to begin." />
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
                        {source?.display_name ?? 'All sources'} · {rule.type}
                        {rule.whole_word ? ' · whole word' : ''}
                      </span>
                    </div>
                    <label className="switch" title={rule.enabled ? 'Disable rule' : 'Enable rule'}>
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
                      aria-label={`Delete ${rule.pattern}`}
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

function SettingsPage({
  snapshot,
  action
}: {
  snapshot: AppSnapshot
  action: (work: () => Promise<unknown>) => Promise<void>
}) {
  return (
    <>
      <PageHeader
        eyebrow="Preferences"
        title="Local app settings"
        description="Choose how matched messages arrive and manage this device's Telegram authorization."
      />
      <section className="panel settings-panel">
        <div>
          <h3>Delivery format</h3>
          <p className="muted">
            Formatted copy adds source, author, time, matched rules, and an original link.
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
              <strong>{mode === 'copy' ? 'Formatted copy' : 'Native forward'}</strong>
              <span>
                {mode === 'copy'
                  ? 'Clean summary with matching context'
                  : 'Original Telegram message and media'}
              </span>
            </label>
          ))}
        </div>
      </section>
      <section className="panel danger-zone">
        <div>
          <h3>Telegram session</h3>
          <p className="muted">
            Logging out revokes Telegram authorization when online and removes the
            encrypted session from this computer.
          </p>
        </div>
        <button
          className="danger-button"
          onClick={() => {
            if (window.confirm('Log out of Telegram on this device?')) {
              void action(() => window.chatrd.call('auth.logout'))
            }
          }}
        >
          Log out
        </button>
      </section>
      <div className="privacy-footer">
        <LockIcon />
        <p>
          ChatRD connects only to Telegram. Message bodies are not stored in the local
          database or diagnostic logs.
        </p>
      </div>
    </>
  )
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
      <span>{icon}</span>
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
    monitoring: 'Monitoring',
    catching_up: 'Catching up',
    paused: 'Paused',
    offline: 'Offline',
    action_required: 'Action required'
  }[state] ?? 'Starting'
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
      <strong>{value.toLocaleString()}</strong>
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
