# ChatRD

ChatRD is a local Windows and macOS desktop application that signs in with a
personal Telegram account, watches selected chats, matches literal rules or an
optional local Ollama semantic filter, and
copies or forwards matching messages to one summary chat.

Message matching and operational state stay on the user's computer when Ollama
uses its default local address. The
application has no custom backend, telemetry, cloud sync, or message-body
logging.

## Current implementation

The initial MVP implementation includes:

- Electron, React, and TypeScript desktop UI.
- Bundled Python 3 worker using Telethon and Telegram MTProto.
- Telegram login code and two-step-verification flows.
- OS-encrypted Telegram session persistence and logout.
- Telegram chat discovery and stable peer IDs.
- One writable destination and multiple monitored source chats.
- Start-now, latest-N, and recent-hours initial scans.
- Global and per-source keyword, phrase, and hashtag rules.
- Unicode-aware case-insensitive and whole-word matching.
- Side-effect-free testing area for previewing applicable and matched rules.
- Optional semantic matching through Ollama with `gpt-oss:20b`, structured
  boolean output, configurable instructions and endpoint, and deterministic
  internal generation defaults.
- Text and media-caption processing.
- Ordered catch-up, buffered live hand-off, and live monitoring.
- SQLite migrations, per-source cursors, and processing deduplication.
- Deterministic Telegram `random_id` values for crash-safe send retries.
- Formatted-copy and native-forward delivery modes.
- Pause/resume, source health, counters, and redacted worker errors.
- Windows worker and installer packaging.
- Windows, macOS Intel, and macOS Apple-silicon CI packaging definitions.
- Required desktop and Python unit/integration tests with a 90% core-worker
  coverage gate.

Real Telegram account flows cannot run in ordinary automated tests. They require
the evaluator's own API credentials and account.

## Architecture

```text
React renderer
    │ narrow contextBridge API
Electron main process
    │ versioned newline-delimited JSON over stdin/stdout
Python worker
    ├── Telethon ── MTProto ── Telegram
    ├── Ollama ── gpt-oss:20b (optional)
    └── SQLite
```

The renderer is sandboxed and has no Node.js access. Electron main owns worker
lifecycle and OS secret encryption. The Python worker is the only SQLite writer
and owns Telegram processing.

Detailed documents:

- [App description and MVP scope](docs/APP_DESCRIPTION.md)
- [System design](docs/SYSTEM_DESIGN.md)
- [MVP Kanban board](docs/MVP_KANBAN.md)

## Prerequisites

- Node.js 22 and npm.
- Python 3.11–3.13.
- Windows 10/11 or a currently supported macOS version.
- A Telegram API ID and API hash from
  [my.telegram.org/apps](https://my.telegram.org/apps).
- Optional: Ollama and enough memory to run `gpt-oss:20b` locally.

Use a dedicated non-production Telegram account during development whenever
possible.

## Install

```powershell
npm install
python -m pip install -e "services/telegram-worker[dev,build]"
```

To enable semantic matching, install Ollama and download the model:

```powershell
ollama pull gpt-oss:20b
```

Then open **Настройки → Ollama**, enter the selection instructions, send a test
message to verify the model, and enable the filter. The default server address is
`http://127.0.0.1:11434`.

No Telegram credentials belong in source files, environment templates, test
fixtures, commits, or CI secrets.

## Run in development

```powershell
npm run dev
```

Electron starts the Python module from
`services/telegram-worker/src`. Local application data is written to Electron's
platform user-data directory, not the repository.

During onboarding:

1. Enter the API ID, API hash, and international phone number.
2. Enter the code sent by Telegram.
3. Enter the Telegram two-step-verification password if requested.
4. Select a writable destination, such as Saved Messages.
5. Select source chats and their initial scan policies.
6. Add at least one rule.
7. Optionally test a composed message against the rules without sending it.
8. Start monitoring from the dashboard.

The login code and 2FA password are not stored. The API hash and serialized
Telegram authorization are encrypted at rest with Electron's `safeStorage`,
which uses Windows or macOS credential protection.

## Test

Run every required suite:

```powershell
npm test
```

This executes:

- Vitest desktop domain/IPC tests.
- Pytest matcher, formatter, SQLite, cursor, delivery, retry, catch-up, and live
  monitoring tests.
- A 90% coverage gate over the critical Python domain modules.

Automated tests use synthetic messages, temporary SQLite databases, and a fake
Telegram gateway. They do not connect to Telegram or require credentials.

Other checks:

```powershell
npm run typecheck
npm run build
npm audit --omit=dev
```

## Build a local package

Install the Python `build` extra, then run:

```powershell
npm run package
```

The command:

1. creates a one-file platform worker with PyInstaller;
2. builds Electron main, sandboxed preload, and renderer bundles; and
3. creates the current-platform desktop package with Electron Builder.

Windows output is written beneath `release/`. macOS artifacts must be created on
macOS; the GitHub Actions workflow builds Intel and Apple-silicon variants on
their corresponding runners.

Internal unsigned packages may trigger operating-system warnings. Public
distribution requires Windows code signing and Apple signing/notarization.

## Local data

Electron chooses the OS-specific user-data directory. It contains:

- `chatrd.db` — settings, peer metadata, rules, cursors, and processing outcomes;
- `secrets.bin` — OS-encrypted Telegram API/session authorization.

The database does not store source message bodies, captions, login codes, 2FA
passwords, or formatted destination text.

Logout asks Telegram to revoke the session when reachable and removes
`secrets.bin`. SQLite configuration remains so the user can reconnect without
recreating every rule.

## Rule semantics

- Rules are OR-combined.
- When the Ollama filter is enabled, messages that do not match a literal rule
  are classified against the configured instructions. A positive AI result is
  an additional OR match; literal matches do not invoke the model.
- Case-insensitive matching uses Unicode NFC normalization and case folding.
- Keywords are literal substrings unless whole-word mode is enabled.
- Phrases are literal contiguous strings, not regular expressions.
- Hashtags must be complete hashtag tokens.
- Text and media captions are evaluated.
- One source message produces at most one delivery even if several rules match.
- AI failures are retried without marking a message as processed. Setting a
  non-local Ollama URL sends message text to that server.
- Edited messages, quoted content, OCR, voice transcription, and regex are not
  part of the MVP.

## Known MVP limitations

- Real Telegram authentication and delivery need manual test-account validation.
- System tray, launch-at-login, auto-update, and daily digests are not included.
- Formatted-copy mode copies text/captions but does not re-upload media; use
  native forward to retain media.
- Telegram may prohibit forwarding protected messages.
- Message links are best effort and are unavailable for some peer types.
- The repository does not contain production signing certificates or a custom
  application icon.
- Desktop E2E automation remains a later phase; unit/integration tests and a
  packaged startup smoke test are currently the release checks.
