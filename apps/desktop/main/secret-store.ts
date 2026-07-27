import { promises as fs } from 'node:fs'
import { dirname } from 'node:path'
import { safeStorage } from 'electron'

export type TelegramSecret = {
  api_id: number
  api_hash: string
  session: string
}

export class SecretStore {
  constructor(private readonly path: string) {}

  async save(value: TelegramSecret): Promise<void> {
    if (!safeStorage.isEncryptionAvailable()) {
      throw new Error('Operating-system credential encryption is unavailable.')
    }
    const encrypted = safeStorage.encryptString(JSON.stringify(value))
    await fs.mkdir(dirname(this.path), { recursive: true })
    await fs.writeFile(this.path, encrypted, { mode: 0o600 })
  }

  async load(): Promise<TelegramSecret | null> {
    try {
      if (!safeStorage.isEncryptionAvailable()) return null
      const encrypted = await fs.readFile(this.path)
      const parsed = JSON.parse(safeStorage.decryptString(encrypted)) as TelegramSecret
      if (!parsed.api_id || !parsed.api_hash || !parsed.session) return null
      return parsed
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') return null
      throw error
    }
  }

  async clear(): Promise<void> {
    try {
      await fs.unlink(this.path)
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error
    }
  }
}

