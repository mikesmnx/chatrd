# App description and MVP scope

Status: planning baseline  
Working name: **ChatRD** (replaceable before implementation)  
Target platforms: Windows and macOS

## 1. Product summary

ChatRD is a private, local desktop companion for Telegram. It lets a user select
Telegram chats, define keywords, hashtags, and exact phrases, and route matching
messages to one summary chat. It catches up after downtime and then continues
monitoring in real time.

The application authenticates as the user's normal Telegram account through
MTProto. It is not a bot and it has no custom backend. Except for direct
communication with Telegram, configuration, matching, state, and logs remain on
the user's computer.

The app solves a narrow problem: important decisions and actions are scattered
across busy Telegram chats, and manually collecting them is slow and unreliable.
It is not intended to replace Telegram or become a full Telegram client.

## 2. Product principles

1. **Local and private by default.** No content analytics, cloud sync, custom
   server, or telemetry. Full message bodies are not written to logs or the
   database.
2. **Safe recovery.** Closing the app for hours or days must not cause messages
   to be silently missed. Work resumes from durable per-chat cursors.
3. **No duplicate delivery.** Catch-up and live events use one processing path,
   a local uniqueness constraint, and Telegram idempotency identifiers.
4. **Understandable automation.** The UI shows what is monitored, why a message
   matched, processing health, and actionable errors.
5. **Conservative first run.** A newly monitored source starts "from now" unless
   the user explicitly requests a bounded history scan.
6. **Tests are part of the feature.** Unit tests are required for every domain
   behavior and must pass before a card or release is complete.

## 3. Intended user

A single person using one Telegram account on one desktop installation who:

- belongs to multiple active private chats, groups, or channels;
- wants a focused summary stream for decisions, actions, incidents, or topics;
- is comfortable obtaining Telegram API credentials during onboarding; and
- expects configuration and processing to stay local.

Multi-user installations, organization-wide administration, and cross-device
configuration sync are outside the MVP.

## 4. Primary experience

### 4.1 First-run onboarding

The app presents a guided setup:

1. **Privacy and prerequisites**
   - Explain that processing is local and the app talks directly to Telegram.
   - Link to instructions for obtaining a Telegram API ID and API hash.
2. **Telegram sign-in**
   - Enter API ID, API hash, phone number, and Telegram login code.
   - Prompt for the Telegram two-step-verification password when required.
   - Never persist the login code or 2FA password.
3. **Destination**
   - Load the account's chats and choose one writable summary chat.
   - Default recommendation: Telegram "Saved Messages" or a private chat owned
     by the user.
4. **Sources**
   - Select one or more chats to monitor.
   - The destination cannot also be a monitored source.
5. **Rules**
   - Add global rules and optional per-source rules.
   - Preview each rule's type and matching options.
6. **Starting point**
   - For each source choose: from now (default), latest N messages, or messages
     from the last N hours/days.
   - Show an explicit warning before scanning existing history.
7. **Review and start**
   - Show destination, sources, rules, and initial scan choices.
   - Start catch-up, then enter live monitoring.

If setup is interrupted, non-secret progress may be saved locally; the app does
not claim monitoring is active until authentication and configuration are valid.

### 4.2 Main window

The MVP has four views:

- **Dashboard** — state (`Starting`, `Catching up`, `Monitoring`, `Paused`,
  `Action required`, or `Offline`), source health, last successful activity,
  counts of matched/ignored/failed messages, and recent redacted events.
- **Sources** — source selection, enabled state, initial scan policy, cursor
  status, and per-source error state.
- **Rules** — create, edit, enable, disable, and delete global or per-source
  rules.
- **Settings** — destination, formatted-copy/native-forward mode, Telegram
  account details, diagnostics export, logout, and local-data deletion.

Closing the window exits the app in the MVP. Minimizing leaves monitoring
running. Background system-tray behavior and "launch at login" are later work so
the app never runs invisibly without an explicit product decision.

### 4.3 Normal processing

For each new or recovered source message, the app:

1. reads message text or media caption;
2. evaluates enabled global and source-specific rules locally;
3. records a no-match outcome without storing the body, or sends one destination
   message even if several rules matched;
4. records the matched rule IDs, source identity, destination identity, outcome,
   and timestamps; and
5. advances the source cursor only after the message has a durable terminal
   outcome.

Rules are OR-combined in the MVP: matching any enabled applicable rule is enough
to deliver the message. Rule exclusions and AND groups are deferred.

## 5. Rule behavior

| Rule type | MVP behavior |
| --- | --- |
| Keyword | Literal substring; case-insensitive by default; optional Unicode-aware whole-word boundary |
| Exact phrase | Literal contiguous phrase, including spaces and punctuation; case-insensitive by default |
| Hashtag | A complete hashtag token including or omitting the leading `#` in configuration; case-insensitive by default |

Additional semantics:

- Match text messages and media captions only.
- Normalize text to Unicode NFC and use Unicode case-folding for
  case-insensitive comparison.
- Do not interpret configured text as a regular expression.
- An empty/whitespace-only rule is invalid.
- A message matching multiple rules produces one destination message listing all
  matched rules.
- Rule changes affect messages processed after the change; the MVP does not
  automatically re-run old messages.
- Edited messages, quoted/replied-to content, OCR, audio transcription, and
  topic-specific matching are not evaluated in the MVP.

## 6. Destination output

### 6.1 Formatted copy (default)

The destination message contains:

- the primary matched tag or label;
- source chat display name;
- original author when Telegram exposes it;
- original Telegram timestamp, shown in the user's local time zone;
- all matched rule labels;
- original text or caption; and
- a link to the source message when Telegram can construct one.

The formatter safely escapes Telegram markup. If a message is too long for
Telegram, metadata is retained and the content is truncated with a clear marker;
multi-part copying is not part of the MVP.

Media itself is not re-uploaded in formatted-copy mode in the MVP. The copy
includes its caption and source link where available. Native-forward mode is the
option for retaining the original media.

### 6.2 Native forward

The app asks Telegram to forward the original message. Telegram content
protection, permissions, deleted messages, or chat restrictions may make that
impossible. A failure is shown as actionable rather than silently falling back
to a formatted copy, because the two modes have different privacy and content
semantics.

## 7. MVP functional scope

### Included

- Electron desktop application on Windows and macOS.
- Personal-account Telegram authentication, including 2FA.
- Secure local session persistence, logout, and local-session deletion.
- Chat discovery and selection using stable Telegram peer IDs.
- One writable destination and one or more enabled/disabled sources.
- Global and per-source keyword, phrase, and hashtag rules.
- In-app configuration persisted in SQLite; a YAML-only setup flow is not needed
  for the desktop MVP.
- Text and media-caption matching.
- Per-source first-run policy: now, latest N, or recent time window.
- Ordered startup catch-up plus buffered hand-off to live monitoring.
- Local SQLite state, migrations, cursors, processing outcomes, and
  deduplication.
- Formatted-copy and native-forward modes.
- Flood-wait, offline, revoked-session, inaccessible-chat, send restriction, and
  database error handling.
- Pause/resume control and redacted diagnostic logs.
- Optional semantic matching through a user-configured Ollama server and model.
- Windows and macOS packaged builds suitable for MVP evaluation.
- Required automated unit tests and local/CI test commands.

### Explicitly excluded

- Any custom backend, cloud deployment, cloud sync, or remote administration.
- OCR, voice transcription, or managed cloud content processing.
- Mobile, web, or Linux clients.
- Full Telegram browsing or chat UI.
- Regex, include/exclude logic, Boolean rule groups, sender rules, or topics.
- YAML/JSON configuration import and export.
- Edited-message processing and reply/quote content inspection.
- Daily digests and scheduled delivery.
- System tray, auto-start, or auto-update.
- Encrypted storage of all non-secret SQLite metadata.
- Multiple Telegram accounts per app profile.
- E2E desktop automation as an MVP release gate.

## 8. Non-functional requirements

### Privacy and security

- Network access is limited to Telegram endpoints during normal operation.
- No analytics or crash-report upload in the MVP.
- The Telegram authorization material and API hash are encrypted at rest with
  the OS credential protection mechanism.
- Login codes and 2FA passwords exist only in memory for the authentication
  request.
- Logs contain IDs, categories, timestamps, counts, and error codes—not message
  bodies, captions, phone numbers, credentials, or session material.
- Renderer isolation, a narrow preload API, and no Node.js access from web UI
  content are required.

### Reliability

- Process recovered messages oldest-to-newest independently for each source.
- Preserve ordering per source; different sources may progress independently.
- A failure in one source must not stop healthy sources.
- Retry transient failures with bounded exponential backoff and Telegram
  flood-wait timing.
- Never advance past an unresolved message without an explicit, persisted user
  decision to skip it.
- A crash at any processing stage must recover without losing the cursor and
  must retry destination sends with the same Telegram idempotency ID.

### Performance targets

These are MVP engineering targets, not user-facing guarantees:

- Dashboard becomes interactive within 5 seconds on a typical supported laptop,
  while the worker may continue connecting.
- A new text message normally begins evaluation within 2 seconds of receipt when
  connected and not flood-limited.
- UI remains responsive during a 10,000-message bounded catch-up.
- Local state supports at least 100 monitored chats, 1,000 rules, and 1,000,000
  processing records without requiring a schema change.

### Accessibility and operability

- All onboarding, source, and rule actions are keyboard reachable.
- Status never relies on color alone.
- Errors explain the affected source/action and a recovery step.
- Destructive logout/data deletion requires confirmation and explains scope.

## 9. MVP acceptance outcome

The MVP is ready for evaluation when a fresh Windows or macOS installation can:

1. authenticate a personal Telegram account with or without 2FA;
2. choose a destination, two sources, and a mix of global/per-source rules;
3. start from now without forwarding older content;
4. copy exactly one formatted summary for a message matching several rules;
5. close for a bounded period, reopen, and process missed messages in order;
6. retry a crash-interrupted send without producing a second destination
   message;
7. survive a simulated flood-wait and continue at the required time;
8. log out and remove local Telegram authorization material; and
9. pass all required unit tests on both implementation runtimes.

Desktop E2E automation is desirable after the core is stable. Until then, the
packaged-build scenarios above are verified with a documented manual smoke
check.

## 10. Assumptions to validate during implementation

- For an internal MVP, the user supplies a Telegram API ID and API hash. A public
  distribution decision must separately review Telegram's API terms and
  credential model.
- One installation controls one account and one destination.
- "Private summary chat" means any destination the account can write to; the UI
  recommends Saved Messages or a user-controlled private chat.
- Source-message links are best effort because Telegram cannot provide a usable
  public/private link for every peer type.
- macOS packaging will target both Apple silicon and Intel unless project
  stakeholders deliberately narrow the supported hardware before the packaging
  milestone.
