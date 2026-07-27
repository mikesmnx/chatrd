# Initial MVP Kanban board

Status: MVP implementation is in verification; this file retains the original
card definitions and acceptance criteria  
Companion documents: [App description](APP_DESCRIPTION.md) and
[system design](SYSTEM_DESIGN.md)

## 1. Board policy

Columns:

- **Backlog** — prioritized but not yet fully ready to start.
- **Ready** — acceptance criteria and dependencies are sufficient.
- **In progress** — actively being implemented; WIP limit 2.
- **Review/verify** — code review, automated checks, and acceptance verification;
  WIP limit 2.
- **Done** — acceptance criteria, required tests, documentation, and review are
  complete.
- **Blocked** — cannot progress; every blocked card names the reason and owner.

Rules:

1. No implementation card is Done without its unit tests.
2. Tests are written with each behavior; testing is not a final hardening card.
3. A card cannot enter Review/verify with failing lint, types, unit, integration,
   or contract checks relevant to its changes.
4. Production code must not contact Telegram in automated unit tests.
5. Any schema or IPC change includes migration/compatibility tests.
6. A blocked card does not count against the In-progress WIP limit, but it is
   reviewed daily.
7. Estimates are relative story points (1, 2, 3, 5, 8). Split a card before work
   if it grows beyond 8.

## 2. Current implementation snapshot

Updated 26 July 2026:

| Backlog | Ready | In progress | Review/verify | Done | Blocked |
| --- | --- | --- | --- | --- | --- |
| OPS-03, REL-02–03, QA-02, E2E-01 | — | — | FND-02–03, IPC-02, DATA-02, AUTH-01–02, CHAT-01–02, RULE-01, PROC-02–04, SEND-02, OPS-01–02, UI-02–04, REL-01, QA-01 | PLAN-01, FND-01, IPC-01, DATA-01, RULE-02, PROC-01, SEND-01, UI-01 | — |

The full MVP code path and Windows package exist. Items remain in
Review/verify when they need real Telegram test-account acceptance,
cross-platform CI execution, signing/notarization, or the complete packaged
manual checklist. Unit/integration tests currently cover the pure domain,
SQLite, processor, catch-up/live hand-off, retry/deduplication, and desktop
state/validation paths.

## 3. Initial board snapshot (before implementation)

| Backlog | Ready | In progress | Review/verify | Done | Blocked |
| --- | --- | --- | --- | --- | --- |
| FND-01–03, IPC-01–02, DATA-01–02, AUTH-01–02, CHAT-01–02, RULE-01–02, PROC-01–04, SEND-01–02, OPS-01–03, UI-01–04, REL-01–03, QA-01–02 | SPIKE-01 | — | — | PLAN-01 | — |

`PLAN-01` is this planning baseline. `SPIKE-01` is first because it retires the
highest-risk architecture assumptions before broad scaffolding.

## 4. Release milestones

| Milestone | Outcome | Cards |
| --- | --- | --- |
| M0 — Architecture proven | Telethon auth/send/retry and packaged worker handshake work on both OS families | SPIKE-01 |
| M1 — Tested local core | Project/CI, IPC, database, matcher, formatter, and processor work against fakes | FND, IPC, DATA, RULE-02, PROC-01, SEND-01 |
| M2 — Telegram vertical slice | Authenticate, list chats, configure one source/destination and rules, catch up, and deliver | AUTH, CHAT, RULE-01, UI-01/02, PROC-02/03, SEND-02 |
| M3 — Operable MVP | Full management UI, recovery, pause/status, security/logout, diagnostics | PROC-04, OPS, UI-03/04 |
| M4 — Cross-platform candidate | Packaged Windows/macOS artifacts pass automated gates and manual acceptance | REL, QA |

## 5. Card backlog

### Planning and risk

#### PLAN-01 — Product, architecture, and board baseline — 3 points — **Done**

Acceptance:

- Product behavior, MVP boundaries, security posture, architecture, recovery
  semantics, required unit testing, and E2E deferral are documented.
- Initial implementation cards have dependencies and acceptance criteria.

#### SPIKE-01 — Prove Telegram and packaging risk path — 5 points — **Ready**

Dependencies: PLAN-01

Acceptance:

- A disposable prototype authenticates with a personal test account, including
  2FA, without committing credentials.
- Raw Telethon calls send a formatted message and native forward using a supplied
  stable `random_id`; retry demonstrates Telegram-side deduplication.
- Session serialization/encryption boundary is proven without logging the
  session.
- Electron starts a packaged Python worker and completes an IPC handshake on a
  Windows x64 and a macOS target.
- Findings record the pinned Telethon major version, sidecar packager, and any
  architecture changes; disposable prototype code is not treated as production.

Required tests:

- Automated local test of deterministic ID derivation and worker handshake.
- Sanitized manual evidence for the Telegram and cross-platform package checks.

### Foundation

#### FND-01 — Repository and toolchain scaffold — 3 points — **Backlog**

Dependencies: SPIKE-01

Acceptance:

- Electron/TypeScript and Python worker workspaces follow the agreed layout.
- Reproducible dependency locks, root development commands, formatting, linting,
  and type checking are configured.
- Sample environment/config files contain no real credentials.

Required tests:

- One example unit test runs in each runtime through the root test command.

#### FND-02 — CI and required quality gates — 3 points — **Backlog**

Dependencies: FND-01

Acceptance:

- Windows and macOS CI jobs run lint, type checks, unit tests, integration tests,
  coverage, migration checks, and secret scanning.
- Core Python domain branch-coverage threshold is 90%; other initial thresholds
  are documented and ratchetable.
- Test reports and build logs are redacted and retained as CI artifacts.

Required tests:

- A controlled branch proves each gate fails when its corresponding fixture is
  intentionally broken.

#### FND-03 — Shared errors, clocks, IDs, and redacted logging — 3 points — **Backlog**

Dependencies: FND-01

Acceptance:

- Both runtimes use stable error/event codes, injectable clocks, correlation IDs,
  and structured logging conventions.
- Sensitive-field redaction is centralized; full message content and credentials
  are prohibited from logs.
- Log rotation and diagnostic-event retention are bounded.

Required tests:

- Table-driven redaction tests include nested exceptions, IPC payloads, phone
  numbers, session strings, codes, passwords, message bodies, and captions.

### Process boundary

#### IPC-01 — Versioned desktop/worker contract — 5 points — **Backlog**

Dependencies: FND-01

Acceptance:

- NDJSON request, response, event, error, cancellation, and handshake schemas are
  defined and generated/validated in both languages.
- Maximum frame sizes, timeouts, backpressure, and sensitive fields are defined.
- Standard output cannot be polluted by ordinary worker logs.

Required tests:

- Golden fixtures pass in TypeScript and Python.
- Invalid, oversized, unknown-version, timeout, cancellation, and malformed
  frames are rejected predictably.

#### IPC-02 — Worker lifecycle manager — 5 points — **Backlog**

Dependencies: IPC-01, FND-03

Acceptance:

- Electron main starts/stops the correct sidecar, verifies compatibility, and
  reports worker health.
- Unexpected exits use bounded backoff; a crash loop becomes Action required.
- Graceful shutdown and forced termination preserve recoverable state.

Required tests:

- Unit tests cover start, ready, stop, crash, retry, crash-loop, incompatible
  version, timeout, and app-exit state transitions using a fake process.

### Local persistence

#### DATA-01 — SQLite schema, migrations, and repositories — 8 points — **Backlog**

Dependencies: FND-01, FND-03

Acceptance:

- The schema in the system design is implemented with foreign keys, WAL, busy
  timeout, constraints, and numbered transactions.
- Python worker is the only writer.
- Repository interfaces do not accept or store message bodies/captions.
- Migration failure stops safely without deleting or recreating user data.

Required tests:

- Temporary-real-SQLite tests cover fresh setup, every migration upgrade,
  rollback, constraints, uniqueness, transaction boundaries, and busy/corrupt
  failure mapping.

#### DATA-02 — Settings, retention, and local-data deletion — 3 points — **Backlog**

Dependencies: DATA-01

Acceptance:

- Validated non-secret settings can be read/updated transactionally.
- The retention decision for processing records is implemented and documented.
- Confirmed local-data deletion targets only resolved app-owned paths and reports
  partial failure.

Required tests:

- Validation, atomic update, retention boundary, exact deletion scope, and
  partial-failure unit/integration tests.

### Authentication and chat configuration

#### AUTH-01 — Secure Telegram login and session restore — 8 points — **Backlog**

Dependencies: SPIKE-01, IPC-01, DATA-01

Acceptance:

- Login supports phone, code, optional 2FA, cancellation, invalid/expired code,
  flood wait, and network loss.
- API hash and authorization material are encrypted at rest through the OS.
- Code and 2FA password are never persisted.
- A valid encrypted session restores without re-entering credentials.

Required tests:

- Gateway-fake state-machine tests cover every login branch.
- Main-process tests prove encrypted persistence and sensitive-value redaction.
- Platform encryption adapter contract tests run on Windows and macOS.

#### AUTH-02 — Logout and authorization cleanup — 3 points — **Backlog**

Dependencies: AUTH-01, DATA-02

Acceptance:

- Logout attempts Telegram revocation, disconnects, removes the encrypted local
  session, and returns to onboarding.
- Offline logout explains that local credentials were removed even if remote
  revocation could not be confirmed.
- Delete-all-local-data remains a separately confirmed action.

Required tests:

- Online, offline, partial cleanup, restart-after-logout, and idempotent-repeat
  tests.

#### CHAT-01 — Discover and cache Telegram peers — 5 points — **Backlog**

Dependencies: AUTH-01, DATA-01

Acceptance:

- Dialogs load with stable peer ID/type, display label, and known write
  capability.
- Search/filter is local after load; refresh handles renamed/inaccessible peers.
- Saved Messages is identifiable and selectable.
- No message history/body is fetched just to list chats.

Required tests:

- Mapping, pagination, cancellation, duplicate IDs, refresh, inaccessible peer,
  and redacted error tests using gateway fixtures.

#### CHAT-02 — Validate destination, sources, and scan policies — 5 points — **Backlog**

Dependencies: CHAT-01, DATA-01

Acceptance:

- Exactly one writable destination and at least one enabled source can be saved.
- Destination-as-source is rejected.
- Now/latest-N/recent-window values have explicit safe bounds.
- Confirmation persists immutable first-scan boundaries so restart is
  deterministic.

Required tests:

- Validation matrix and boundary tests for peer roles, unavailable peers, scan
  values, time zones, and interrupted confirmation.

### Rules and matching

#### RULE-01 — Rule configuration service and UI — 5 points — **Backlog**

Dependencies: IPC-01, DATA-01, UI-01

Acceptance:

- Create, edit, enable, disable, and delete global/per-source keyword, phrase,
  and hashtag rules.
- Invalid/blank patterns and unsupported option combinations are explained.
- Rules display their scope and matching behavior without exposing regex.

Required tests:

- Service and UI-view-model unit tests cover validation, scope, editing,
  enablement, deletion confirmation, and IPC error mapping.

#### RULE-02 — Pure Unicode-aware matcher — 8 points — **Backlog**

Dependencies: FND-01

Acceptance:

- Implements the exact semantics in the product/system documents for text and
  captions.
- Returns all matched IDs in stable order but requests one delivery.
- Does not use configuration text as regex.
- Remains deterministic and bounded for long/adversarial input.

Required tests:

- Table/property-based cases for case folding, NFC variants, non-Latin text,
  Unicode boundaries, hashtag prefixes, punctuation, emoji, multiline captions,
  empty content, multiple matches, and long inputs.
- At least 90% branch coverage for the matcher.

### Processing and recovery

#### PROC-01 — Per-message state machine and cursor transactions — 8 points — **Backlog**

Dependencies: DATA-01, RULE-02, FND-03

Acceptance:

- Canonical processor produces pending/no-match/sent/failed/skipped states.
- One serial queue per source preserves order; sources are isolated.
- Cursors advance only over contiguous terminal outcomes.
- Live/history overlap and repeated enqueue are harmless.

Required tests:

- Fake-gateway and real-SQLite tests inject a crash/failure before and after every
  durable transition, verify ordering, deduplication, cursor position, and
  cross-source isolation.

#### PROC-02 — Initial scan planner and history catch-up — 8 points — **Backlog**

Dependencies: CHAT-02, PROC-01

Acceptance:

- Now, latest-N, and recent-window boundaries are resolved and persisted.
- History pages process oldest-to-newest up to a fixed high-water ID.
- Progress is reported without message content.
- Cancellation/restart resumes from the durable cursor.

Required tests:

- Page boundaries, empty history, deleted-ID gaps, large scans, cutoff equality,
  cancellation, restart, flood wait, and no-history-for-Now scenarios.

#### PROC-03 — Buffered hand-off to live monitoring — 5 points — **Backlog**

Dependencies: PROC-02

Acceptance:

- Live handler buffers before catch-up high-water resolution.
- Buffered events drain after each source catches up, then stream normally.
- Buffer is bounded and backpressure behavior is visible/actionable.
- Reconnect performs a cursor-based reconciliation scan.

Required tests:

- Deterministic race tests cover before/during/after high-water events, duplicate
  history/live events, reconnect gaps, out-of-order arrival, and buffer pressure.

#### PROC-04 — Retry, permanent failure, retry/skip controls — 5 points — **Backlog**

Dependencies: PROC-01, UI-04

Acceptance:

- Transient retries and exact flood waits persist across restart.
- Permanent failures block only the affected source.
- User can retry or explicitly skip with a warning and durable audit outcome.
- Destination-wide failure pauses destination sends without losing work.

Required tests:

- Retry scheduling with fake clock, flood waits, restart, inaccessible source,
  unwritable destination, retry success, skip, and independent healthy source.

### Delivery

#### SEND-01 — Safe formatted-copy formatter — 5 points — **Backlog**

Dependencies: RULE-02

Acceptance:

- Produces deterministic metadata, matched-rule list, text/caption, local display
  time, and best-effort source link.
- Escapes all user content and handles missing author/link.
- Enforces Telegram text limits with explicit truncation.
- Does not persist the formatted body.

Required tests:

- Golden tests for escaping, injection-like text, Unicode, links by peer type,
  timestamps/DST, missing fields, exact length boundaries, and multiple matches.

#### SEND-02 — Idempotent copy and native forwarding gateway — 8 points — **Backlog**

Dependencies: SPIKE-01, PROC-01, SEND-01

Acceptance:

- Stable non-zero signed 64-bit ID is persisted before every send.
- Raw Telegram send/forward receives exactly that ID on initial attempt and
  retry.
- Telegram response/update maps to destination message ID.
- Forward restrictions remain explicit permanent failures; no semantic fallback.

Required tests:

- Deterministic ID/collision-domain vectors, same-ID retry, crash after accepted
  send, in-flight duplicate response, native restriction, oversized content, and
  destination loss using the fake gateway.
- Sanitized test-account verification is part of release smoke, not normal CI.

### Desktop UI and operation

#### UI-01 — Secure application shell and navigation — 5 points — **Backlog**

Dependencies: FND-01, IPC-01

Acceptance:

- Renderer sandbox/context isolation/no-Node settings are enforced.
- Narrow preload API, main navigation, keyboard focus, and loading/error
  boundaries exist.
- Closing exits; minimizing keeps the worker active.

Required tests:

- Preload allow-list, navigation state, focus behavior, loading/error boundaries,
  and dangerous Electron preference assertions.

#### UI-02 — Guided onboarding — 8 points — **Backlog**

Dependencies: AUTH-01, CHAT-02, RULE-01, UI-01

Acceptance:

- Implements privacy, credentials/sign-in, destination, sources, rules, scan
  policy, review, and start steps.
- Back/cancel/restart never claims monitoring before valid confirmation.
- History scan warnings and secret-field handling are clear and accessible.

Required tests:

- View-model/component tests for every step/branch, validation, 2FA, restore,
  navigation, interruption, and sensitive-value clearing.

#### UI-03 — Sources, rules, and settings views — 8 points — **Backlog**

Dependencies: RULE-01, CHAT-02, AUTH-02, UI-01

Acceptance:

- User can manage source enablement, rules, destination/mode, logout, and local
  deletion.
- Risky actions have scoped confirmations and success/failure feedback.
- Rule edits clearly state that past messages are not reprocessed.

Required tests:

- Component/view-model tests for CRUD, confirmation, error, optimistic/stale
  response, and keyboard/accessibility behavior.

#### UI-04 — Dashboard, pause, progress, and action-required states — 5 points — **Backlog**

Dependencies: IPC-02, PROC-01, UI-01

Acceptance:

- Dashboard shows app/source state, catch-up progress, redacted counters/events,
  and last-success time.
- Pause/resume state is durable and accurately distinguishes queued from active
  work.
- Errors provide retry/skip/re-authenticate/change-destination actions where
  applicable.

Required tests:

- Reducer/view-model tests cover state transitions, stale/out-of-order events,
  coalesced progress, pause/resume, and each recovery action.

### Operations and privacy

#### OPS-01 — Failure classification and persisted retry scheduler — 5 points — **Backlog**

Dependencies: FND-03, DATA-01

Acceptance:

- Telegram/network/database errors map to documented transient, flood-wait,
  authentication, and permanent categories.
- Retry schedule uses bounded exponential backoff with jitter or exact Telegram
  wait.
- Restart honors persisted next-attempt time.

Required tests:

- Table-driven classification plus fake-clock schedule/restart/jitter-bound
  tests.

#### OPS-02 — Diagnostics and privacy controls — 3 points — **Backlog**

Dependencies: FND-03, UI-03

Acceptance:

- Rotating logs obey the documented allow/deny fields.
- Diagnostics preview and export are local and user initiated.
- Privacy copy accurately describes storage/network behavior.

Required tests:

- Rotation, export scope, preview, redaction regression, and filesystem-error
  tests.

#### OPS-03 — Database/disk/crash-loop recovery UX — 3 points — **Backlog**

Dependencies: IPC-02, DATA-01, UI-04

Acceptance:

- Migration failure, disk full, persistent lock/corruption, and worker crash loop
  stop unsafe processing and show non-destructive next steps.
- App never silently replaces or deletes a failed database.

Required tests:

- Failure-injection tests for each state and its UI error mapping.

### Release and verification

#### REL-01 — Reproducible Windows package — 5 points — **Backlog**

Dependencies: M3 cards, FND-02

Acceptance:

- Windows x64 artifact installs/runs, launches the correct worker, uses an
  app-owned data path, and uninstalls without unexpectedly deleting user data.
- Signing or the explicitly accepted internal-evaluation warning path is
  documented.
- Artifact includes dependency locks, licenses, checksum, and SBOM.

Required tests:

- CI packaged startup/IPC smoke plus versioned manual Windows acceptance.

#### REL-02 — Reproducible macOS packages — 8 points — **Backlog**

Dependencies: M3 cards, FND-02

Acceptance:

- Apple-silicon and Intel artifacts (or an approved narrowed target) launch the
  correct worker and use the proper user-data path.
- Signing/notarization or explicitly accepted internal-evaluation warning path
  is documented.
- Artifact includes dependency locks, licenses, checksum, and SBOM.

Required tests:

- CI packaged startup/IPC smoke on required architecture(s) plus versioned manual
  macOS acceptance.

#### REL-03 — Setup, privacy, recovery, and troubleshooting documentation — 3 points — **Backlog**

Dependencies: AUTH-02, OPS-02, REL-01, REL-02

Acceptance:

- README/user guide covers API credentials, sign-in/2FA, configuration, scan
  policies, rule semantics, privacy/storage, backups, logout/deletion, common
  failures, and update limitations.
- Screens and commands match the shipped build.

Required tests:

- A clean-machine evaluator follows the guide without developer assistance;
  links and commands are checked in CI where automatable.

#### QA-01 — Automated MVP acceptance suite with fakes — 8 points — **Backlog**

Dependencies: all M3 behavior cards

Acceptance:

- Cross-component tests cover multi-rule single delivery, now-mode, bounded
  catch-up, live overlap, crash recovery, flood wait, source isolation, revoked
  session, and logout.
- Uses fake Telegram gateway and temporary database; no account/credentials.
- Runs reliably on Windows and macOS CI.

Required tests:

- This card is itself the integration acceptance suite; flake retries cannot hide
  a consistently failing scenario.

#### QA-02 — Packaged MVP release checklist — 5 points — **Backlog**

Dependencies: REL-01, REL-02, REL-03, QA-01

Acceptance:

- The nine MVP outcomes in the app description are checked on clean Windows and
  macOS environments.
- Telegram test-account data is sanitized from evidence and local artifacts are
  removed after the check.
- Known limitations and accepted unsigned-build warnings are recorded.
- All required unit/integration gates pass with no unexplained skips.

Required tests:

- Versioned manual checklist until desktop E2E replaces applicable steps.

## 6. Later-phase quality card (not an MVP release gate)

#### E2E-01 — Playwright Electron E2E with fake worker — 8 points — **Later**

Dependencies: stable IPC contract and M3 UI

Acceptance:

- Automates first-run onboarding, source/rule configuration, catch-up progress,
  live monitoring, pause/resume, failure recovery, logout, and restart restore.
- Runs against a deterministic fake worker; ordinary CI never uses Telegram
  credentials.
- Captures screenshots/traces only with synthetic content and has a documented
  flake budget.

This is intentionally outside the initial MVP gate, but the narrow preload/IPC
design and stable selectors should make it straightforward to add without
reworking production behavior.

## 7. Suggested first pull sequence

1. SPIKE-01 — retire Telegram idempotency, session, and packaging risks.
2. FND-01 and FND-02 — establish the project and non-negotiable test gates.
3. FND-03, RULE-02, and SEND-01 — build/test pure domain behavior.
4. IPC-01 and DATA-01 — establish stable boundaries and durable state.
5. PROC-01 — prove the crash-safe state machine against fakes/SQLite.
6. AUTH-01 and CHAT-01 — connect the tested core to Telegram.
7. UI-01 and UI-02 — expose the first usable vertical slice.

Only one or two cards should be active at once. This ordering front-loads the
hardest external and recovery assumptions while keeping unit tests attached to
every increment.
