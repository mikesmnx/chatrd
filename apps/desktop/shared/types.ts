export type WorkerEvent = {
  event: string
  payload: Record<string, unknown>
}

export type ChatRDDesktopApi = {
  call: <T = unknown>(method: string, payload?: Record<string, unknown>) => Promise<T>
  onWorkerEvent: (callback: (event: WorkerEvent) => void) => () => void
  platform: NodeJS.Platform
}

export type Peer = {
  peer_id: number
  peer_type: 'user' | 'group' | 'supergroup' | 'channel' | 'unknown'
  display_name: string
  username: string | null
  can_write: boolean
}

export type Source = {
  peer_id: number
  display_name: string
  enabled: boolean
  initial_scan_mode: 'now' | 'latest_count' | 'recent_window'
  initial_scan_value: number | null
  last_terminal_message_id: number | null
  error_code: string | null
}

export type Rule = {
  id: string
  source_peer_id: number | null
  type: 'keyword' | 'phrase' | 'hashtag'
  pattern: string
  case_sensitive: boolean
  whole_word: boolean
  enabled: boolean
}

export type Settings = {
  destination_peer_id: number | null
  delivery_mode: 'copy' | 'forward'
  paused: boolean
  ai_enabled: boolean
  ollama_base_url: string
  ollama_model: string
  ollama_prompt: string
  ollama_timeout_seconds: number
  ollama_temperature: number
}

export type MonitorSnapshot = {
  state: 'paused' | 'catching_up' | 'monitoring' | 'offline' | 'action_required'
  counts: Record<string, number>
  sources?: Source[]
}

export type AppSnapshot = {
  authenticated: boolean
  settings: Settings
  sources: Source[]
  rules: Rule[]
  monitor: MonitorSnapshot
}

declare global {
  interface Window {
    chatrd: ChatRDDesktopApi
  }
}
