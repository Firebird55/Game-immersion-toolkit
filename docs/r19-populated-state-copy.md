# Populated authored state copy and normal service readback

Status: implemented programmatic synthetic adapter with source tests; the
separate fixed frozen integration described below is a **native-pending source
candidate**. It adds `authored-populated-state-copy-v1` and its own harness and
receipt, without a production caller. The historical C3–C6 cases, dispatch
defaults, harness predicates and receipts retain their existing meaning.
The [completion plan](r19-completion-plan.md),
[R18 host contract](r18-storage-host-contract.md) and
[mutable-store limits](r19-mutable-store-lifetime.md) remain applicable. This
builds no installer and does not change PR #59, the source updater or production
store schemas.

## Separate frozen integration candidate

[The fixed harness](../scripts/probe-frozen-populated-state.ps1) accepts only the
exact extracted `runtime-experiment` candidate and its provenance. Its fixed
case is `authored-populated-state-copy-v1`, with the fixed `api-populated` API
entry. The experiment still uses the existing genuine suspended creation
objects, Jobs, retained listeners, strict C2 drain, coordinator and typed barrier.
It does not create a second host/keeper or derive authority from a stored path,
SQL fence, JSON event or manifest. No native run or passing receipt exists yet
for this new case.

The outer bootstrap envelope has settings below `empty-host/p2` and work below
its `cache-v1/work`. Four independent marked roots are derived below fixed
`p2-native`: legacy, private-target, external-state and host-profile. All are
initially marker-only; the seed uses normal services and settles its actual
setup owners before creating the inner child marker or entering leases. The
inner RuntimeLayout selects settings=legacy and **data=legacy/data**, so the
coordinator's source lease and the unchanged source Enter operation both select
the same `data/companion-operation.lock`. Other mutable roots remain below the
legacy settings root; explicit host accounts and automatic/manual export state
remain in their independently marked siblings. These are fixed authored roots,
not discovered or operator-selected installations.

The pre-owner source contender may open and close only after seeding. It is
labelled `seeded-before-owner`; no exclusion during seed is claimed, and no
target lease baseline runs before its parent exists. Once the sole coordinator
enters, both native lease contenders and the actual unchanged source
`Enter-CompanionOperation` must refuse at every observing checkpoint. Their
original entered lease objects remain held throughout both genuine source
cohorts, barrier creation, mapped copy, clone verification and source readback.
An uncertain setup before owner entry retains its actual objects and reports
`owner_interval=not-entered` in the private closed recovery event; it never
claims continuous exclusion.

### Normal readback, explicit TEST boundaries

The fixed API entry creates the actual normal classes at the selected paths:
AccountStore uses the exact host-profile locator and shared strict TEST codec;
LexiriseService receives the fixed truthy fake key and finite authored
MockTransport with remote writes disabled; AutomaticMobileExports receives
the actual selected external home. Wrong constructor arguments, an unknown
remote route, malformed TEST bytes or fallback to an ambient/default locator
refuse. TEST is not DPAPI, real credential evidence or permission to contact an
account. The normal SQL ledger class, request middleware, registry, SQL Phase B,
strict C2 behavior and real readiness remain active.

Normal loopback HTTP on retained listener objects covers Hito history/favorites,
settings/calibration, profile listing and stale-account refusal, Half-Life
language/target, selected manual destination, automatic waiting, grammar 0/4
and export status. The one additional normal ZZZ transcript row has the already
exported authored grammar sentence. Its ordinary saved-line send route must
return already-sent, add only local `line:3` and perform no remote write; GET
status and later source/clone readback check that retained reference. The native
case alone extends this fixture; historical P2 and C3–C6 expectations stay intact.

The normal history endpoint still filters ZZZ rows against a loaded game index.
This fixture supplies no such index, so Hito list/favorite and direct saved-line
reading/send coverage do not imply all-ZZZ history-list coverage. All three
authored rows are checked through TranscriptStore on the disposable clone.
Durable pending language requests have no current HTTP list field: their check
is actual constructor/service `entries()` readback, not an invented endpoint.
No capture start, browse, language rebuild, background export or remote setting
write is requested. The JS importer remains a build-host test, without runtime
Node, browser persistence or Migaku evidence.

### Ordered control and independent exclusions

The separate control schema is
`proxy-r19-frozen-populated-state-copy-probe-v1`, with exactly 44 flat keys. The
raw reader retains the existing one-pending-read policy, strict UTF-8 and 8 KiB
line cap with a 120-second deadline. Stderr is discarded through the existing
fixed-buffer task; no stderr string, byte count or private hash is kept. Raw
JSON object enumeration rejects duplicate keys before closed key/type/enum and
source/build validation. Missing, unknown, nested, wrongly typed, out-of-order,
trailing or inconsistent events refuse before ACK. No event grants ownership.

| Checkpoint | Generation / created / resumed / signaled / strict drains | Harness observation before ACK |
| --- | --- | --- |
| seeded-before-owner | 0 / 0 / 0 / 0 / 0 | Actual source Enter opens/closes; no target observation |
| owner-entered | 0 / 0 / 0 / 0 / 0 | Both native leases and actual source Enter blocked |
| api-populated-checked | 1 / 2 / 2 / 0 / 0 | Same exclusions; normal first-cohort readback passed |
| strict-drain-complete | 1 / 2 / 2 / 0 / 1 | Same exclusions; real C2 completed |
| writers-signaled | 1 / 2 / 2 / 2 / 1 | Same exclusions; genuine retained creations signaled |
| copy-progress | 1 / 2 / 2 / 2 / 1 | Same exclusions; exact live plan/barrier remains held |
| copy-verified | 1 / 2 / 2 / 2 / 1 | Same exclusions; disposable-clone services and preserved bytes passed |
| source-resumed | 2 / 4 / 4 / 2 / 1 | Same exclusions; genuinely fresh source cohort/readback passed |
| final-strict-drain-complete | 2 / 4 / 4 / 2 / 2 | Same exclusions; final real C2 completed |
| final-writers-signaled | 2 / 4 / 4 / 4 / 2 | Same exclusions; four retained writer signals observed |
| released | 2 / 4 / 4 / 4 / 2 | No ACK; independent open checks follow confirmed owner exit |

Before emitting and after receiving **both** first-cohort drain ACKs, Python
rechecks the same captured coordinator/owner, current adapter, one-element owned
tuple, concrete layout object, generation, absent pre-mint barrier and exact two
held lease objects. Active=True during strict drain and False after signal are
distinct expected states. SQL setup tokens do not substitute for these process
checks. Copy ACKs also preserve the same actual plan/typed barrier, source
inventory, pointer and external snapshot. Generation two has its own original
frame; the old barrier is retired before fresh admission, and exited handles
cannot be reused for that new cohort.

Only after actual C2, ordinary-status 503/health availability and both first
writer signals may the coordinator mint the barrier. Selected source and
snapshot bytes are preserved before fresh admission; semantic verification opens
only disposable SQLite clones. After fresh normal constructors/cache activity,
source logical state rather than unchanged database bytes is required. Host and
external bytes, snapshot, route pointer and source/profile bindings retain their
respective explicit checkpoints. This is not a nonempty-WAL experiment.

### Receipt, failure and cleanup

The separate receipt schema is
`proxy-r19-frozen-populated-state-copy-receipt-v1`, with exactly 55 keys. A passing
receipt requires the pre-owner source-open baseline, nine independently completed
blocked checks, two genuine cohorts/four retained writer signals/two strict
drains, successful copy/service/API readbacks and the unchanged pointer. The
legacy function source is pinned before/after to its exact reviewed LF or CRLF
bytes. Neither the source body nor old harness projectors are edited.

The fixed `expected_*` counts describe the requested fixture, not observations:
three current rows, one retained older named row, two local grammar overrides,
one exported sentence and three references. The four literal expected schema
pins are user_version 0 for current transcript, retained transcript, export
ledger and reading cache, in that order; they are the reviewed P2 plan's exact
pins, not placeholders. The actual core/schema checks precede normal clone
constructors. A failed receipt never approves those expected values.

Failure counts retain only the last fully validated **regular** control frame's
generation/signals/drains and this harness's fully completed 0–9 source-block
checks. Default zero means no such observation. A closed recovery frame supplies
only its finite category, never fresh counts, authority or success semantics;
unknown/malformed input updates nothing. Its earlier real observations need not
be falsely relabelled as never run. The public failed receipt instead uses
not-approved for every approval outcome and retains explicit failed status.
It publishes no rows, account IDs, key/profile/path values, PIDs, raw errors,
scope contents, private file hashes or logs.

The terminal released event has no ACK. The harness closes input and requires
exit zero on the retained owner, control EOF, stderr discard completion, real
open source/target lease contenders, free ports, exact immutable runtime
inventory and confirmed private tree/process disposal before publishing passed.
No finally branch kills the unknown owner, releases entered leases, deletes its
fixture or adopts another process. Unknown containment retains the actual owner,
input, readers and original Python resources; a workflow deadline is a failed
attempt with unconfirmed cleanup, not proof every process/lease closed.

The report sink independently checks ancestors root-first and refuses links,
existing leaves and unknown metadata. It creates only missing parent components
after candidate admission and writes a private sibling with exclusive CreateNew
and no sharing. Only confirmed write, durable flush and close permit an exclusive
rename to the exact public report name. Existing report bytes are preserved; no
stale-output deletion, overwrite or failure-path blind removal occurs. A
complete-looking partial write cannot become the uploaded report. A failed
write/close retains its actual stream record, original errors and owned private
partial file and refuses publication; it cannot retry
the close or replace it with a different result. The default report basename is
`r19-frozen-populated-state-copy.json`. The owner Process object is retained
before Start is attempted; uncertain startup therefore cannot disappear from
the recovery hold.

[The focused PS7 checker](../scripts/test-populated-state-harness.ps1) loads only
named AST function definitions and never executes the harness body, starts a
runtime/native owner, contacts HTTP or acquires a lease. It tests actual closed
projector admission and actual private report files: valid phases, invalid
types/keys/order/identity/duplicate/trailing frames, recovery no-adoption,
fresh-parent creation, preexisting/link refusal, once-only publication and
failed/premature-pass receipts. Its synthetic read function supplies only bounded
authored JSON and is not proof of the real async byte reader. Run
`pwsh -NoProfile -File scripts/test-populated-state-harness.ps1` before the native
probe. PowerShell is unavailable on the current development host, so that
checker and actual frozen mechanism remain required Windows validation.

This is still source-only/native-pending integration. Physical/global/dynamic
writers, keeper loss, warm OCR/routing, browser/Migaku, real credentials,
ordinary-user Windows 11, exact-output rights, target/production activation,
installer and R19 completion remain unavailable, pending or false. Source tests
and a future hosted Windows Server receipt cannot close those separate gates.

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
