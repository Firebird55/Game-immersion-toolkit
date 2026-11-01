# Populated authored state copy and normal service readback

Status: implemented programmatic synthetic adapter with source tests. No new
frozen case, dispatcher, PowerShell harness, upload entry or production caller is
added. The historical C3–C6 cases and receipts retain their existing meaning.
The [completion plan](r19-completion-plan.md),
[R18 host contract](r18-storage-host-contract.md) and
[mutable-store limits](r19-mutable-store-lifetime.md) remain applicable. This
builds no installer and does not change PR #59, the source updater or schemas.

## Actual owners and selected roles

`PopulatedStateCopy` creates a complete **fixed authored fixture**, not a tool
which discovers or migrates an installation. Seeding requires four empty,
nonoverlapping `SyntheticRoot` directories with the same installation identity.
Existing content prevents seeding. Account, language, export and game contents
are authored TEST data; no live Runtime, installed game or user account is read.
All four raw roots are rechecked root-first before any seed directory listing,
including a static link/reparse replacement made after fixture construction.

`SyntheticStateBindings` retains the actual settings, language, installation,
manual/automatic export and account objects plus their selected RuntimeLayout.
It captures manual preference paths through the real owner property while the
fixture's layout is selected. Subsequent checks use those captured paths and
unchanged owner/root/scope identities. They do not recalculate preferences from
the ambient source environment. SQL setup objects and their existing operation
fences are also retained and checked against the four selected database paths.

| Selected source role | Copy namespace or preservation |
| --- | --- |
| Actual `layout.data_root` | `data/`, including Chinese history/favorites, the retained older named transcript file, both ledgers, language tables and opaque data-key TEST bytes |
| Actual `SettingsStore.path`, with its separate legacy file in data | `host-settings/settings.json`; selected-file precedence remains distinct |
| Actual language registry and requests; installation and game-path files | Fixed `host-settings/languages.json`, `languages.requests.json`, `setup.json` and `game-paths.json` |
| Actual unscoped/scoped manual preference paths | Fixed `host-settings/mobile-library.json` and `mobile-library/` subtree |
| Actual `layout.work_root` | Reviewed authored pending-work bytes in `work/voice-assets/` |
| Explicit external export root | Current/previous libraries, actual captured work identity, automatic rules/work/recovery and authored installation stay in place |
| Explicit host root and actual AccountStore locator | `Programs/Proxy Transcript/accounts.dpapi` and host-key TEST bytes stay in place; they are not relocated into the snapshot |

The settings root itself is never recursively copied. It can contain other
mutable roots, caches, leases or journals. The copied namespaces are target
snapshot names and do not make a writable, activatable RuntimeLayout. The
manifest still has `activation_allowed: false`.

The real export function prepares its normal work directory. The adapter captures
that actual path during fixture generation. Plan, inventory and readback never
call the mutating `work_folder` function or duplicate its path calculator. A
missing/moved captured work root refuses. Persisted export destinations are
checked against the already selected external owner; JSON cannot authorize a
new root. Changed automatic owner/persisted state or an unbound configured
destination also refuses. External roots are inventoried and checked in place.

## Normal operations and readback

The fixture uses actual service methods, with no SQL row seeding:

- TranscriptStore adds Chinese Hito/ZZZ history, marks a favorite and retains a
  separate older named transcript file. That file uses the current normal store
  constructor; this is preservation evidence, not a newly invented legacy
  schema migration.
- SettingsStore saves calibration, retired Hito fields, language-independent
  capture preferences and selected-file precedence. InstallationService records
  completed setup through its normal method.
- AccountStore registers/selects two explicit fake profiles using a bounded
  MockTransport and a visibly authored TEST envelope. LexiriseService receives
  a truthy explicit fake key, so credential, environment and DPAPI fallback paths
  are not used. Host/data fallback TEST blobs remain opaque.
- LexiriseService selects a mocked owned sentence deck, exports one unvoiced
  Chinese sentence and records two references without a duplicate remote write.
  ReadingService uses actual analysis/cache/grammar methods to persist both
  local proficiency 4 and local proficiency 0 overrides against opposite mocked
  remote states. Only fixed identity/settings/analysis/vocabulary/deck requests
  are accepted; unknown requests refuse.
- LanguagePreparation builds actual authored GoldSrc localization tables in
  two source/target directions, records per-profile choices and preserves a
  failed explicit pending request. Language workers are joined before setup
  settles. The normal registry/request constructor reconstructs the expected
  durable state.
- Ordinary `prepare_source` and `export_library` create two unvoiced libraries,
  preserve the previous library, interrupt the next revision and retain private
  work. Automatic export's normal configuration/status publication and guarded
  `publish` preserve a prior output and recovery copy on interruption.

The copy uses the existing coordinator-minted `SyntheticWriterBarrier` and the
same continuously held legacy/target leases. Readiness, SQL-operation tokens,
stored paths and manifest fields cannot mint that barrier. The setup reading
pool, language workers, manual admission and automatic picker/owner are settled;
the four existing SQL-operation fences close setup admission. This does not
replace the separate whole-cohort stop/signaled requirement.

Core integrity checks use separate disposable SQLite copies. Additional
exact table/column/version checks run on disposable copies before normal store
constructors can initialize or migrate anything. Fresh normal services then
reopen a **separate verification clone**. They compare full history/favorites,
grammar choices/cache, export status and new-reference idempotency, settings,
game paths, completed setup, registry/request state, manual destinations,
automatic waiting jobs and TEST account identity. A repeated ledger send adds
its new reference only in the clone and permits no remote write.

Source and staging are never SQLite-opened for semantic verification. Snapshot
bytes, source inventory, pointer and all preserved external bytes are checked
after readback. The clone is removed only after its actual services have settled.
The genuine public `library.mjs` importer reads both current and previous ZIPs in
the buildhost test, including Chinese/English context and absence of voice packs.
Node is not invoked or resolved by runtime code. This is importer-format
compatibility, not browser persistence, Migaku or physical-device acceptance.

## Failures and remaining boundaries

Mapped traversal checks raw ancestors before descendants and bounds inspection
to 4,096 entries, 32 path components and 64 MiB. The fixture's external census has
the existing corresponding bounds. Static links/reparse points, missing owned
roots, unsupported files, unknown SQLite stores/schema, source changes, copy
interruption, insufficient space, unowned partial targets, changed owner paths
and semantic/cleanup errors refuse. This does not claim protection against
arbitrary concurrent filesystem replacement.

Mapped verification rechecks raw ancestors at its actual read boundaries:
before every snapshot header open, before primary database `copy2`, and before
optional WAL/SHM presence metadata and their subsequent `copy2`. Optional
sidecars use no-follow checks rather than `exists()` followed by an unchecked
copy. The new semantic clone is guarded before/after tree copying and at its
database/sidecar copy boundaries too. Permanent spies cover completed static
file and parent substitutions, both sidecars before metadata and copy, and a
completed clone substitution. They require zero following metadata, header
opens or copy reads through those links. Malformed sidecar marker bytes in
these negatives are not fabricated WAL/SHM acceptance evidence. Checks do not
claim to eliminate a replacement between the final check and an OS operation.

All copy/core-integrity/schema/semantic/close/cleanup errors are conservative:
the original private exception remains retained; partial service objects are
retained before constructor entry. Mapped plans select a narrow core verifier
which records its actual connection and fixed query cursors before use. Body,
cursor-close, connection-close and filesystem-cleanup errors are separate
retained references. Every close is attempted once, and no root cleanup starts
before all cursor/connection closes return successfully. A pre-close failure
therefore retains the still-usable connection and its actual database directory;
there is no TemporaryDirectory destructor to remove that directory. A retained
record refuses another mapped verification operation. New semantic clone roots
and partial service objects remain retained on their failures as well.

Filesystem cleanup can itself partially fail; its root identity, remaining
content and owners are retained without a cleanup retry or reconstruction of
already removed files. Historical C3–C6 plans do not select the mapped verifier:
their original TemporaryDirectory branch remains unchanged, with no retroactive
claim that an old core temporary directory survives a failed close. The existing
source adapter is poisoned,
the coordinator remains recovery-required with its leases held, and no second
source cohort is admitted. Callers must keep that owner alive; there is no
automatic cleanup/finally which declares recovery successful. A future frozen
caller still needs its explicit living-owner failure hold. No raw traceback,
paths, keys or fixture text is added to public metadata. Migration manifests
remain private evidence and are not newly allowlisted for upload.

The mapped fixture pins its exact validated RuntimeLayout object to the actual
existing source adapter. Copy entry, copy completion and the adapter's real
activate/start admission check the same identity. A mismatch also poisons the
adapter and marks its retained coordinator recovery-required. This includes a
change after the copy method returns but before context-exit resumes source.
The added object pin in `_FrozenAuthoredDataRuntime._require_owned` is opt-in;
the historical C3–C6 routes do not set it. Their default behavior remains, but
the whole adapter class is consequently no longer AST-identical to its older
source.

Source tests drive the existing FrozenAuthoredDataRuntime/coordinator order with
explicit process/HTTP doubles. They prove this programmatic composition, not new
native process signals. Native integration must separately bind the exact fixed
fixture to genuine C2 and retained child objects before its barrier. Actual
Windows known-holder directory/set replacement, ordinary Windows 11, complete
global/dynamic writer admission, keeper-death exclusion, physical mutable-root
detach, warm OCR/routing, browser/credential migration and rights acceptance
remain open. No copied target is activated and no live data is accessed.
