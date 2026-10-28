# R18 storage and runtime host contract

Status: **research and proposed R12c contract; no runtime implementation**.
Originally reviewed on 2026-10-28 against `upstream/main`
`4a4abfcee8d4fa87a8bfacdae12b6cef5284cad9` (toolkit 0.21.3). Refreshed on
2026-10-28 after rebasing onto freshly fetched `upstream/main`
`ba0b7c34c358f1664220674e5ff8bb7f30502e5f` (0.22.0, PR #58): the active
registry now contains 25 games, including twelve additional readers. This
refresh inventories support already implemented upstream; it adds no game.
Code links and current-behavior statements below refer to that refreshed baseline.
This document inventories actual source and defines the small boundary R14, R19
and R21 can adopt. R14's candidate/physical-pack/preference contracts are still
planned. Defining this boundary does not complete R14, R19, an installer or a
migration. The companion remains a Windows desktop application with an ordinary
browser; the independent mobile/browser-extension modes remain available.

The companion [component inventory](r18-runtime-components.md),
[architecture study](rework-architecture.md), [roadmap](rework-roadmap.md),
[runtime context](runtime-context.md) and [release runbook](../RELEASE.md) supply
component, lifecycle, integration and publication requirements. No account, game,
credential, recording, database or existing installation was read or modified
for this research. Source inspection and upstream documentation are evidence;
native execution and migration are unverified.

## Decisions and scope

- R19 should prove a PyInstaller **directory bundle for Windows x64** of the
  existing Python runtime, with immutable application/resources and explicitly
  selected writable roots. It must work without preinstalled Python, Node/npm or a
  .NET SDK. The inventory owns tool-by-tool prerequisite/redistribution decisions;
  this document owns their locations, launch and lifetime. Build tools may remain
  on trusted build hosts.
- Investigate a local static frontend in R19, behind the existing public browser
  origin. This is an equivalence experiment. Keep the current Vinext/Wrangler
  frontend/router as the source/development adapter and fallback until the
  experiment proves the required routes, extension integration, assets, workers,
  API/WebSocket access and browser storage behavior. No origin switch is allowed
  merely because a static build loads.
- R19 may implement an **opt-in, copy-and-verify data-root migration prototype**
  with a durable manifest, leaving the old ZIP/data intact. Moving files, deleting
  old data, automatically upgrading a real installation, installer integration,
  uninstall and comprehensive upgrade/rollback acceptance belong to R20/R21.
- Preserve existing per-PC settings/calibration, language/account selections,
  Chinese and older transcript stores, independent Migaku mode, userscript
  storage keys and current protected credentials. No storage consolidation or
  database replacement is needed to bundle the runtime.

## What the current application actually owns

Here `legacyRoot` means the original checkout/extracted ZIP passed as `-Root` to
its launcher/updater; `codeRoot` means the active code version. These often differ
after an update. Tokens below are logical paths, never a published host profile.

| Current path or root | Owner and actual content | Persistence / migration treatment |
| --- | --- | --- |
| Active checkout/release `backend`, `scripts`, `public`, `dist`, `vendor`, package/version/lock files | Application version; frontend build and Python modules | Replace as one verified application version. Never source runtime data from a different version's static capability catalog. |
| `legacyRoot/data` | Backend `PROJECT_ROOT/data`; multiple services accept a project root and append `data` themselves | Installation-owned mutable root today; preserve its complete contents before any split. It is not a wholly disposable cache. |
| `data/transcript-v2.db` | Transcript/history/favorites and audio references | Durable user data. Preserve alongside untouched older stores; do not merge old transcript semantics silently. |
| `data/lexirise/exports-v2.db` | Account/language-scoped destinations, export completion and idempotency/reference state | Durable operational/user data. Rebuilding it can repeat remote writes; do not treat it as a cache. |
| `data/lexirise/reading-cache-v2.db` | Account/language/settings-scoped reading results **and persistent local `grammar_choices` overrides** | Mixed durable/derived sensitive state despite its filename. Preserve the whole database; any later cache eviction must delete only recreatable cache rows and retain grammar choices, exports and keys. |
| `data/lexirise/key.dpapi` | Fallback legacy encrypted API key | Persistent protected credential. Preserve even if a newer local key takes precedence. |
| `data/languages/<game>/<locale>`, legacy `data/textmaps`, `data/<game>` | Prepared text/voice bindings, metadata, installation fingerprints, tools, legacy indexes | Mixed derived and durable selection/readiness state. Preserve exact locale/catalog bindings and last complete snapshots. A folder or old index alone is not physical pack presence. |
| `data/persona5royal/persona5-charsets` | Pinned Persona character-mapping TSVs, upstream license and generated attribution notice, shared across requested locales | Private derived metadata with GPL review obligations; preserve verified bytes for offline preparation and never move it into shipped resources without separate closure. Not account preferences or credentials. |
| `data/agent-voices` (optional existing tooling) | Agent library, `entries.db`, observed names, fingerprints/PCM/audio and optional `model/**/model.int8.onnx` plus adjacent `tokens.txt` | Mixed local user/recognition state and derived indexes; preserve existing contents. Model absence is explicitly unavailable; do not seed from a developer installation. |
| `data/audio`, `data/voice-assets` | Original decoded audio, recordings, voice manifests and learned mappings; decoder executable | Mixed user media, derived audio and tool cache. Never delete `audio` or learned manifests as a blanket cache clean. Referenced recordings may be irreplaceable. |
| `legacyRoot/work/voice-assets` | Separately acquired ZZZ reader/license, public metadata, generated JavaScript/scene links/diagnostics, optional old `ZenlessData` checkout and duplicated decoder | Private mutable tool/work directory outside `data`; inventory it explicitly. Preserve source in place; migrate only reviewed tool/metadata/work groups, not unrelated `work` footage or private backups. |
| `data/runtime-code/<version>-<id>`, `data/runtime-assets` | Updater application slots and old hashed frontend chunks | Application staging/compatibility assets today, not user history. Retain active and rollback versions and chunks used by old open pages. |
| `data/companion-runtime.json[.previous]`, `data/processes.json`, `data/companion-operation.lock` | Local route pointer, verified process records and OS-held launcher/update lock | Host coordination; contains private local paths/identities. Never import as live ownership from another installation. A stale PID is not authority to terminate a process. |
| `data/runtime-logs`, `data/toolkit-updates` | Private stdout/stderr, updater stage/status/preferences, download scratch and locks | Logs/scratch can be bounded later; update preference is persistent. Preserve failure evidence and active locks during recovery. Exclude all from public artifacts. |
| `%LOCALAPPDATA%/Proxy Transcript/settings.json` | Per-PC capture calibration/settings and language/account selections | Durable; existing file wins. `SettingsStore` copies legacy `data/settings.json` only when the local file is absent. Preserve retired Hito calibration/keys too. |
| `%LOCALAPPDATA%/Proxy Transcript/game-paths.json`, `setup.json` | Validated game paths and onboarding completion | Durable, host-specific state. Preserve valid manual paths and skip/resume; validate actual installations on use. Do not copy game contents. |
| `%LOCALAPPDATA%/Proxy Transcript/languages.json`, `languages.requests.json` | Prepared-language registry, per-account selected locales/targets and persisted explicit requests/retries | Durable selection/preparation state independent of capture settings; preserve both and validate referenced snapshots. |
| `%LOCALAPPDATA%/Proxy Transcript/nte-archive/<identity>.dpapi` | Installed-version NTE archive metadata, protected for offline use | Private protected **derived metadata**, separate from account credentials. Preserve same-user bytes/location initially. Missing/corrupt data follows bounded public-metadata retry/unavailable behavior; never publish values or suggest account-key recovery for this cache. |
| `%LOCALAPPDATA%/Proxy Transcript/mobile-library.json`, `mobile-library/<scope>.json`, `automatic-mobile-libraries/rules.json` | Export destinations, account/locale-scoped preferences, automatic rules/jobs | Durable configuration; preserve selected external destinations. Account and locale scope must remain intact. |
| Export destination, default `legacyRoot/output/mobile-libraries`; automatic work below `%LOCALAPPDATA%/Proxy Transcript/automatic-mobile-libraries` | Completed private game libraries, `latest.json`, instructions and managed work/history | User output, not release assets. Preserve completed output and pointers; interrupted work is not a completed library. External destinations need their own availability/space checks. |
| Export-derived `.toolkit-mobile-work/<destination-hash>` and legacy `<output>/.toolkit-work` | Same-volume resumable clips/cache plus `previous-libraries` containing complete previous exports | Mixed work and retained user output, not a disposable cache. Inventory the effective export destination and derived workspace together, including implicit old defaults. Preserve completed previous libraries and resume state; do not redirect this workspace to generic `cache_root`. |
| `%LOCALAPPDATA%/Programs/Proxy Transcript/accounts.dpapi`, `key.dpapi` | Named account store and legacy host-local key | Persistent protected credentials, separate from program versions and caches. Keep current paths for contract v1. |
| `%LOCALAPPDATA%/Programs/Proxy Transcript/ProxyTranscriptLauncher.exe`, `project-path.txt`; `%APPDATA%/Microsoft/Windows/Start Menu/Programs/Proxy Transcript.lnk` | Owned managed wrapper, private pointer to the original checkout/ZIP and Start menu entry with source working directory/icon | Launcher/control state, separate from credentials beside it. Preserve the previous working target for recovery; a copied data directory or new app slot does not retarget these entries. Do not manipulate Windows-owned taskbar pin internals. |
| `%LOCALAPPDATA%/Programs/Proxy Transcript/venv` | Existing setup's Python environment | Existing adapter prerequisite, not user data. New bundle must not depend on it; do not delete it while old ZIP rollback uses it. |
| `assets/fireredvad` and optional `%LOCALAPPDATA%/Programs/gamesentenceminer/resources/GameSentenceMiner/assets/fireredvad` fallback | FireRedVAD ONNX/CMVN; current source prefers app assets, otherwise uses a legacy third-party installation | Bundled adapter must require verified shipped resource hashes and actionable missing-resource errors. A third-party installation must not mask incomplete candidate collection. Preserve unrelated fallback files; never copy them blindly. |
| `%USERPROFILE%/.config/oneocr/{oneocr.dll,oneocr.onemodel,onnxruntime.dll}` | Current oneocr package's expected native OCR files, copied by local setup from Snipping Tool | Host-owned native prerequisite. No redistribution permission is inferred; preserve this location until a proved adapter/license permits another. |
| User-installed game directories, including Death Stranding's `oo2core_7_win64.dll` | Publisher-owned game archives, language packs, manifests and game-owned native decompressor | Read-only inputs. Outside app/data/cache migration; toolkit never installs or edits game packs. |
| Browser profile at each origin | localStorage, IndexedDB, Origin Private File System (OPFS) library bytes, Cache Storage, service-worker registrations, file permissions/handles | Browser-owned, separate migration domain. Copying `data` cannot preserve or transfer it. |

Evidence: [Runtime composition](../backend/api.py#L54),
[settings migration](../backend/config.py#L10), [account store](../backend/accounts.py#L16),
[key precedence and export database](../backend/lexirise.py#L74),
[reading cache](../backend/reading.py#L88), [game paths](../backend/game_paths.py#L16),
[setup state and native checks](../backend/installation.py#L75),
[scoped export destinations](../backend/mobile_export_controls.py#L51),
[automatic export state](../backend/automatic_mobile_export.py#L96),
[language/request state](../backend/language_preparation.py#L30),
[Persona metadata acquisition](../backend/persona5_assets.py#L70),
[game-owned native loader](../backend/decima_archive.py#L205),
[protected NTE metadata](../backend/nte_assets.py#L128),
[FireRed resource fallback](../backend/firered_vad.py#L44),
[export work layout](../backend/mobile_export_layout.py#L24),
[retained previous exports](../backend/mobile_export_layout.py#L138),
[wrapper/pointer/shortcut creation](../scripts/install-shortcuts.ps1),
[pointer consumer](../launcher/ProxyTranscriptLauncher.cs#L17),
[updater staging](../scripts/update-companion.ps1#L19) and
[OCR setup](../scripts/setup.ps1#L59). These links describe the reviewed baseline;
future code changes must update the adapters and regression evidence.

### Additional 0.22.0 reader effects

The refreshed [active registry](../backend/game_paths.py#L10) extends the original
thirteen games with the twelve titles in [STEAM_GAMES](../backend/steam_games.py).
The readers use the existing `data/<game>` preparation workspace,
`data/languages/<game>/<locale>/textmap.json` publication and
`data/audio/official-<game>-...mp3` output. The shared source/bundle adapters must
include their dynamically selected modules and format helpers; copying Python
source alone does not prove PyInstaller collects modules selected through
`import_module`. Source entrypoints still use the existing language/index/export
worker kinds, rather than twelve new desktop services. See
[adapter registry](../backend/game_assets.py),
[language-worker inputs](../backend/api.py#L284) and
[worker validation/publication metadata](../backend/language_worker.py#L40).

| Additional game(s) | Source/runtime and storage requirement |
| --- | --- |
| Spyro Reignited Trilogy | [Unreal reader](../backend/spyro_assets.py) and [PAK/localization helpers](../backend/spyro_unreal.py); inspect installed text/voice packs and preserve their exact bindings. This adapter does not call FModelCLI or dynamically load a game DLL. It still uses the existing vgmstream/FFmpeg voice route. |
| Detroit: Become Human | [BigFile reader](../backend/detroit_assets.py) and [format helper](../backend/detroit_format.py); keep archive extents, dependencies, locale aliases and timed original performances in the selected snapshot. It uses the existing decoder/audio outputs, without a new SDK/extractor process. |
| Persona 5 Royal | [CPK/message/flow reader](../backend/persona5_assets.py), [CRI](../backend/persona_cri.py), [message](../backend/persona_message.py) and [flow](../backend/persona_flow.py) helpers; additional private character metadata is acquired during preparation as described below. Original ADX decoding uses the shared decoder, with no upstream Atlus executable launched. |
| MGSV: The Phantom Pain and MGSV: Ground Zeroes | [TPP reader](../backend/mgsv_tpp_assets.py), [GZ reader](../backend/mgsv_gz_assets.py), [Fox helper](../backend/fox_dialogue.py) and [GZS archive helper](../backend/mgsv_gz_archive.py); retain each edition's installed original-voice/text binding and namespace. The inspected paths use Python archive/decompression code and existing audio tools, not a new game-DLL loader. |
| Death Stranding (original PC release) | [Decima reader](../backend/death_stranding_assets.py), [archive](../backend/decima_archive.py), [dialogue](../backend/decima_dialogue.py) and [cinematic](../backend/decima_cinematics.py) helpers; the sole new game-owned dynamic DLL path is described below. The Director's Cut is not implied by this reader. |
| Portal, Portal 2 and Half-Life 2 | [Portal](../backend/portal_assets.py), [Portal 2](../backend/portal2_assets.py) and [HL2](../backend/halflife2_assets.py) readers with shared [Source files](../backend/source_formats.py), [dialogue](../backend/source_dialogue.py) and [scene](../backend/source_scene.py) helpers; preserve game/campaign/DLC namespaces, mount precedence and completed Steam language evidence. Do not infer a pack from `UserConfig` alone or persist unrelated appmanifest/account fields. |
| Half-Life | [GoldSrc reader](../backend/halflife_assets.py) and [format helper](../backend/goldsrc_formats.py); current capability is authored unvoiced messages, with spoken capture explicitly unsupported. Do not acquire a decoder or fail host readiness merely because this text-only route has no voiced records. |
| A Plague Tale: Innocence | [Asobo reader](../backend/plague_tale_assets.py) and [format helper](../backend/plague_tale_formats.py); preserve text/structure/media package precedence and recording overrides. It uses Python parsing and existing audio tools rather than a new SDK or game-DLL path. |
| Deus Ex: Human Revolution - Director's Cut | [BIGFILE reader](../backend/deusex_hr_assets.py), [formats](../backend/deusex_hr_formats.py) and [cinematic](../backend/deusex_hr_cinematics.py) helpers; keep selected locale, recording/stream metadata and decode bounds. Existing decoder subprocesses write only the declared audio/scratch roots. |

This is a host/dependency inventory, not a new claim of every game's or locale's
native playback. The [component inventory](r18-runtime-components.md) owns
codec/artifact decisions and the [per-game reports](game-audits/README.md) own
presentation, official language, installed-file evidence and unresolved bindings.
Existing upstream native statements are not fresh native validation by this R18
refresh. Do not turn an absent pack, unresolved format or unknown voice into
confirmed silence or remove its implemented language choice.

**Persona metadata and preference ownership.**
`Runtime.build_language` passes `--directory = DATA_DIR/persona5royal` to the
existing language worker; only `--output` is in temporary locale staging.
`load_charset` therefore keeps mapping TSVs and `AtlusScriptTools-LICENSE.txt`
under `data/persona5royal/persona5-charsets`, and writes `NOTICE.txt` there.
The source pins Atlus Script Tools commit
`05483fe12f9c482ee17f38ded2e115f4c55015b3` and hashes each table/license; cached
bytes are checked before reuse, downloads are bounded and temporary files replace
only verified content. An absent/corrupt cache can require network preparation;
missing network/metadata is an actionable failure while a prior complete
snapshot stays available. R19 must test both cached and empty/corrupt paths;
packaging must not silently seed a private developer cache. The source's
[acquisition and GPL notice](../backend/persona5_assets.py#L70) and
[third-party notices](../THIRD_PARTY_NOTICES.md) identify GPLv3 metadata; the
[license at the pinned upstream revision](https://github.com/tge-was-taken/Atlus-Script-Tools/blob/05483fe12f9c482ee17f38ded2e115f4c55015b3/LICENSE.txt)
was checked through the connected GitHub source on 2026-10-28. Treat it as a
separate license/source-closure gate; a user download or data-only label
alone does not settle a shipped integration's obligations or publisher rights.
No mapping values or extracted game tables belong in public diagnostics or
provenance. No new upstream executable or account service is required for these
mapping tables.

Mappings are not the selected study/translation target. Preserve the existing
per-account selection, explicit request and local-target fields in
`languages.json` / `languages.requests.json`, plus the snapshot's
`targets_requested`, `source_locale`, `audio_locale`, reader revision and game
fingerprint. Persona's English/Japanese original voice choices and additional
text targets are independent. A missing target translation must remain distinct
from a missing selected text/voice pack. Account switches and retries must not
adopt another account's target or start preparing unrequested translations.
See [Persona selection/build](../backend/persona5_assets.py#L209),
[language ownership](../backend/language_preparation.py#L83) and
[worker snapshot validation](../backend/language_worker.py#L40).

**Game-owned native resource.**
`PackSet` resolves the selected Death Stranding install before loading exactly
`install/oo2core_7_win64.dll` with `ctypes.WinDLL`; it rejects a missing file,
a resolved escape from the installation, or absence of the Windows API. It does
not search PATH or the bundled resource tree for this primary DLL. Both indexing
and later original-voice extraction can read compressed packs, so prove the
loader in the frozen language worker **and** the retained audio extraction path,
including shutdown/update while it is loaded. A successful directory/pack probe
alone does not initialize the DLL. Treat the DLL and dependent game components
as user-installed read-only prerequisites: never copy, collect, seed, hash-upload
or redistribute them through a PyInstaller hook, app/cache/tool root, CI fixture
or release. Missing/incompatible resources need game-file verification guidance,
not a toolkit download or another game's decoder DLL.

The absolute primary path does not by itself prove dependency isolation.
Microsoft documents that dependent DLLs can still be resolved by module name,
and PyInstaller changes Windows DLL search behavior. R19 must test actual loaded
module origins/architecture and dependency failure under the frozen environment,
with spaces/Unicode/unrelated CWD and a read-only game/application tree; keep
private native-path evidence local. The new code is not evidence that a bundle
already loads the correct modules safely. See
[Decima loading](../backend/decima_archive.py#L189),
[voice-path pack reads](../backend/death_stranding_assets.py#L276),
[Microsoft DLL search order](https://learn.microsoft.com/en-us/windows/win32/dlls/dynamic-link-library-search-order)
and [PyInstaller Windows search-path guidance](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#windows)
(official references reviewed 2026-10-28). This game-owned path is distinct from
the separately acquired Unreal helper libraries already inventoried for NTE and
Wuthering Waves; do not generalize it to Spyro or either MGSV reader.

**Readiness and migration semantics.** The existing versioned stores remain in
use; adding twelve game IDs does not justify merging stores or resetting saved
calibration, account/locale targets, favorites, archived games or library
preferences. Preserve all four voice states (`voiced`, `unvoiced`, `unavailable`,
`unknown`) and per-game/campaign presentation metadata. Half-Life's
`capture_capabilities` explicitly permits text-only readiness (`unvoiced_only`);
`capture_unvoiced` stays opt-in and persisted. A host check must distinguish that
supported route from missing audio in a reader that requires it, and must not
advertise spoken Half-Life capture. Other confirmed unvoiced pages use the same
toggle; failed decoding or absent recordings never qualify. Independent mobile
OCR libraries still have their current voiced-catalog behavior, so desktop
text-only readiness does not imply mobile catalog parity. This is a reader
capability distinction; the current `InstallationService` still reports a global
audio-conversion/FFmpeg prerequisite. A text-only reader pass does not satisfy
the full candidate's global dependency/readiness gate. See
[readiness states](../backend/multilingual_index.py#L110),
[Half-Life capability](../backend/halflife_assets.py#L191),
[capture toggle policy](../backend/capture.py#L350),
[global setup requirements](../backend/installation.py#L116) and
[upstream coverage limits](game-audits/README.md#capture-unvoiced-dialogue).

`LocalVoiceAssetService` now reuses a verified full-performance encoding using
per-history filenames, preferably hardlinks with a same-directory copy fallback.
A migration must preserve **every filename/reference** even when source names
share one file identity; deduplication must not collapse independent history
entries or make deleting one line delete another line's audio. Budget destination
space for copies when links cannot be retained; unique-inode byte counts alone
can understate copy space. Retain `playback_scope`, complete-performance binding,
locale and authored channel/stream fields rather than inventing cuts from caption
order. A moved game or incomplete Steam download still requires revalidation of
the original install/pack binding; copying prepared tables does not prove the new
physical pack is ready. See [audio reuse](../backend/local_voice.py#L107),
[inventory byte counting](../backend/language_inventory.py#L12) and
[completed Steam language evidence](../backend/source_dialogue.py#L20).

### Credential boundary

Desktop credentials use Windows `CryptProtectData` / `CryptUnprotectData` with
flag `1` (`CRYPTPROTECT_UI_FORBIDDEN`), no optional entropy, and no
`CRYPTPROTECT_LOCAL_MACHINE`. Named profiles are JSON inside one protected blob;
the browser receives labels/opaque IDs, never keys. Legacy key lookup is:
explicit/pinned key, active saved profile, `LEXIRISE_API_KEY`, host-local
`Programs/Proxy Transcript/key.dpapi`, then `data/lexirise/key.dpapi`.
A malformed/unreadable existing protected store must remain an explicit recovery
error, never be replaced with an empty store during migration.

Microsoft says decryption normally requires matching logon credentials and the
same computer, with a roaming-profile exception. The toolkit therefore supports
same Windows user/host migration only unless separately proved. Copying a blob
across Windows users, running setup as a different/elevated account, or syncing it
to another PC is not credential migration. Never switch to machine-wide DPAPI to
make it portable. Leave unreadable original blobs intact and offer the existing
hidden-input flow only for a new/readable store. That flow does **not** repair an
unreadable named-account store: `AccountStore.add()` reads the existing blob
before writing, so it encounters the same error. R19/R21 need an explicit repair
design that preserves the original encrypted blob and requires a deliberate
reconnection before creating replacement state; it is not implemented here.
Do not automatically rename, delete or replace a failed store. Verify a supplied
key's identity through read-only `/v1/me` without claiming the old profiles were
recovered. A migration needing that unreadable store remains incomplete.
Credentials are persistent state even when their filename is under a program
parent. They must survive repair/uninstall by default and never enter caches,
command-line arguments, logs, workflow secrets, diagnostics or browser transfers.
See [protection implementation](../backend/lexirise.py#L29),
[hidden-input setup](../scripts/set_lexirise_key.py), and Microsoft's
[DPAPI contract](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata)
(reviewed 2026-10-28).
The [named-store read/add behavior](../backend/accounts.py#L29) is the source of
the recovery limitation above.

Mobile/browser credentials are a separate domain: `vault.mjs` stores an encrypted
PBKDF2/AES-GCM record in IndexedDB by default; explicit trusted-device mode stores
a plaintext remembered key. A browser-origin transfer must never export the
remembered key. Existing encrypted vaults stay at their old origin; reconnecting
at a new origin is the default. A future explicit encrypted-vault transfer needs
its own consent, format and tests. Desktop DPAPI and mobile vaults are not
interchangeable. See [vault implementation](../public/mobile-capture/vault.mjs).

## R12c v1: the shared boundary to adopt

This is a proposed, versioned **in-process host description**, not a new public
endpoint or configuration file already consumed by the application. R14 can
accept this description alongside its candidate/physical-pack/preference models;
R13a/R19 can provide source and bundled implementations. Keep service-specific
logic in the existing services. No general container/framework is required.

| Field / operation | Required meaning |
| --- | --- |
| `schema = "proxy-runtime-host-v1"` | Reject unknown major schemas before writes or process starts. It versions path/host semantics, not every database. |
| `mode` (`source` or `bundle`); `version`; `source_commit`; `build_id` | Active application identity from verified resources; never inferred from the legacy launch folder. |
| `application_root` | Exact active application slot and executable siblings. Treat as read-only at runtime. |
| `resource_root` | Root for packaged static catalogs, scripts/adapters and native resources. Source resolves from module location; frozen adapter resolves its bundled resource tree. Never use CWD or data root as a resource fallback. |
| `data_root` | Writable private data root whose contents keep current names, e.g. `transcript-v2.db`, `lexirise`, `languages`, `audio`. Root resolution performs no extraction, game scanning or account network call. |
| `settings_root` | Existing per-user `Proxy Transcript` settings directory. Services retain their specific files and precedence. |
| `cache_root` | Private disposable, versioned derived/scratch storage. Only explicitly registered recreatable content belongs here. Empty is valid. It must not alias a parent of durable data/credentials. |
| `tool_root`, `work_root` | Verified separately acquired tools with revision/notices, and private mutable extraction/transpile workspace. Source adapter maps current per-game `data/*/tools` and ZZZ `work/voice-assets` explicitly; bundled helpers are read-only resources. Never infer these roots from `data_root.parent` or CWD. |
| `export_workspace(destination)` | Preserve the existing export-derived same-volume workspace, its destination identity and retained `previous-libraries`. This is a separate owner from disposable extraction/transpile `work_root`; resolve and validate it with the selected output, not a fixed cache-root alias. |
| `state_root` | Host coordination, route/process state, locks, update journal and private logs. Distinct from immutable application code. Never treat imported process JSON as live ownership. |
| `credential_locations` | Explicit ordered locator list for named profiles, host legacy key and old data-key fallback; protection mode `dpapi-current-user`. Return paths internally, never key material. v1 retains existing host paths. |
| `default_export_root`, `legacy_root?` | Private default for new exports; prior ZIP root for read/copy/recovery only. Explicit saved destinations win. No automatic file movement from an external transfer folder. |
| `frontend_origin`, `api_base`, `websocket_url`, `asset_base`, `frontend_kind` | Canonical public browser contract: initially `http://127.0.0.1:3000`, `http://127.0.0.1:8766`, `ws://127.0.0.1:8766/api/ws`, same-origin asset base, and `current-host` or experimental `static-local`. Record actual legacy aliases separately. Never expose private standby ports as a new public origin. |
| `resource(relative_name)` | Resolve an allowlisted relative resource under `resource_root`; reject traversal/absolute names; fail with an actionable missing-resource error. No writable fallback inside resources. |
| `launch_child(kind, arguments, cwd)` | Map a fixed child kind to a source command or bundled dispatcher/executable; explicit absolute resources, writable output and working directory. No arbitrary module/process execution from browser input. Preserve ownership, cancellation, stdout rules and native bootstrap behavior. |
| `prepare`, `ready`, `quiesce`, `activate`, `close`, `recover` | Existing lifecycle semantics below; preparation/readiness cannot claim exclusive data ownership, migrate data, or write remote accounts. Failures are typed/actionable, with old runtime retained when safe. |

In source v1 the adapter may map `application_root = resource_root = codeRoot`,
`data_root = legacyRoot/data`, and host state/compatibility assets to their current
`legacyRoot/data` subdirectories. This physical co-location is a legacy mapping,
not permission to clear them as caches. Current consumers that append `data`
(e.g. update/export/tool managers) need explicit adapters or narrow constructor
changes when a direct data root is introduced; replacing only `api.DATA_DIR`
would leave split state. Retain existing HTTP endpoints/status codes and
`LocalAccessMiddleware`, account request pinning and lock order.

R14 must take explicit roots for candidate validation/tool readiness and return
physical presence, implemented reader capability and prepared-index readiness
separately. The same installed game and manual path should produce the same
candidate and actionable errors in WebUI and the later installer. Status reads
may inspect/cache inventory; they must not prepare files, select an account,
change preferences, create decks or silently activate a locale. The current
`InstallationService` is the adapter to preserve, not evidence R14 is complete.

### Proposed per-user target layout

Resolve Windows Known Folders for the actual user; do not construct a username
or assume a system drive. Microsoft identifies LocalAppData as per-user and
warns default paths can vary with configuration/redirection:
[Known Folder IDs](https://learn.microsoft.com/en-us/windows/win32/shell/knownfolderid)
(reviewed 2026-10-28). The installer and ordinary launcher must agree on that
user. No system service/admin account should own ordinary user runtime data.

```text
%LOCALAPPDATA%/
  Programs/Proxy Transcript/
    app/<version>-<build-id>/       # immutable onedir application/resources
    launcher/                     # prebuilt stable host/resources, later adapter
    ProxyTranscriptLauncher.exe   # existing wrapper; explicit compatibility plan
    project-path.txt              # existing private legacy pointer, not app data
    accounts.dpapi                # existing same-user location, preserved
    key.dpapi                     # existing same-user location, preserved
    venv/                         # old ZIP adapter only, retained for rollback
  Proxy Transcript/
    settings.json                 # existing calibration/settings, same path
    game-paths.json                # existing validated manual paths
    setup.json                     # existing skip/resume state
    languages.json                 # prepared/selected language registry
    languages.requests.json        # persisted explicit requests/retries
    nte-archive/                   # existing protected metadata cache
    mobile-library*/               # existing scoped destination preferences
    automatic-mobile-libraries/   # existing rules/completed work, not cache
    data-v1/                       # same internal data names as legacy data
    cache-v1/<component>/<format>/  # proven recreatable outputs only
    tools-v1/<component>/<revision>/ # acquired verified tools and notices
    cache-v1/work/                 # disposable scratch only, not export workspace
    host-v1/
      layout.json                  # schema + selected roots + install identity
      runtime/                     # route/process records and lock files
      compatibility-assets/<build-id>/ # retained hashed chunks for open readers
      updates/                     # stage/journal/status; persistent preferences
      logs/                        # private bounded diagnostics
      migrations/<migration-id>/   # manifest/checkpoint/recovery instructions
    exports/                       # default for new exports only
```

Export work remains a separate derived root on the destination volume.
`work_folder(output)` chooses the parent of the transfer folder (with a drive-root
special case) and hashes the normalized absolute output path. It can also move
legacy `.toolkit-work` into that workspace. Preserve the mapping and recorded
previous libraries; changing the output path changes its identity. A future
move needs its own verified copy/reattachment plan and space checks. Do not
assume a rename is atomic across volumes or evict `previous-libraries` with
scratch. R20/R21 also own the existing Start menu entry outside LocalAppData.

This is the target layout, not created by R18. v1 intentionally retains existing
settings and credential locations; path schema versioning does not require moving
working keys. Legacy fallback keys and every unknown legacy file are preserved.
Do not place writable data in PyInstaller `_internal`/`_MEIPASS`, the executable
folder, the game installation, a build checkout, a synced public folder or a
temporary extraction directory. An application slot can be replaced only after
its processes stop; data/credential lifetime is independent of program versions.
The existing source adapter may keep its historical checkout `data` and `output`
locations. For a **new target**, disallow reparse-point/symlink escapes, roots
nested in a game/repository/publication output, and overlapping
immutable/durable/disposable roots before migration.
Keep paths private in local manifests; public reports use logical labels only.

`host-v1/compatibility-assets/<build-id>` replaces the legacy router
`data/runtime-assets` role. Index retained hashed chunks by the producing app
slot/build, and have the stable frontend route serve old/current immutable URLs.
Retain the active build, retained rollback builds and any build needed by open
readers; a generic cache-clean operation must not evict them. Without a proved
open-client retirement policy, keep compatibility chunks conservatively.
Prune only after no active/rollback slot or supported open page needs that build;
application cleanup and user-data cleanup remain separate.

## Source resources, frozen launch and working directories

The current launcher sets `PROXY_TRANSCRIPT_PROJECT_ROOT = legacyRoot` while
starting `python -m backend.main` with CWD `codeRoot`. Thus `PROJECT_ROOT` is
already a partial mutable-root bridge, but it is not a full host abstraction.
`LanguageInventory`, toolkit version reporting and static game catalogs correctly
read the active module/code root; tool/index/export workers often combine
code-relative entrypoints with legacy-root outputs. R19 must inventory each
consumer, not repoint `PROJECT_ROOT` and assume completion.

PyInstaller documents that bundled `__file__` is under the resource tree;
`sys._MEIPASS` points at `_internal` for a directory bundle, while `sys.executable`
is the bootloader executable, not a Python interpreter. Use a single source/
frozen resource resolver with the packaged relative tree, and verify all required
resources exist. App-root and resource-root are separate fields because they can
be different in onedir output. See [PyInstaller runtime information](https://pyinstaller.org/en/stable/runtime-information.html)
(reviewed 2026-10-28). Do not store user data under either resource mechanism.

| Actual source dependency | Bundle requirement / failure to prevent |
| --- | --- |
| `api.py` language builder: `sys.executable -m backend.language_worker`; `local_game_updates.py`: `-m backend.game_index_worker` | Explicit dispatcher/subexecutables with identical CLI/exit/progress behavior. A frozen executable does not accept Python `-m` automatically. |
| `automatic_mobile_export.py` and `mobile_export_controls.py`: `-m backend.mobile_export_worker`; update managers execute `scripts.*` or `.py` paths | Include and probe every child kind, both module and script routes. No end-user interpreter or source-file assumption. Preserve cancellation/output scope and Python import dependencies. |
| Optional `AgentRecognizer`: `sys.executable -m backend.agent_transcribe`; agent/story fingerprint scripts use code-relative default data paths | Explicit ASR child dispatch plus declared data/model/token/scratch roots; preserve separate process and native DLL isolation. Sherpa and FireRedVAD carry incompatible ONNX Runtime DLLs: never import sherpa into capture by collecting both into one process. Missing optional model/tokens remains unavailable. Probe fingerprint workers separately if retained. |
| `toolkit_update.py`: detached `sys.executable -m backend.toolkit_update` twice, CWD `CODE_ROOT` | Independent bundled updater dispatch must survive retirement of the backend. Do not respawn the main API accidentally or terminate the updater with the old process tree. |
| `InstallationService.launch_native`: hidden-input account console, folder PowerShell and capture-readiness `.py` | Use fixed bundled actions; retain hidden input, no credential arguments and user-visible recovery. Pure status remains read-only. |
| Current PowerShell launcher `Add-Type` C# process-image interop | Source launcher compiles an owned P/Invoke shim through OS PowerShell/.NET Framework facilities. Preferred R19 path is a precompiled owned launcher helper; alternatively declare and probe exact OS PowerShell/Framework behavior. The target excludes a separately installed developer compiler, not a claim that unchanged source never compiles C#. This does not excuse end-user game-reader SDK/compiler builds. |
| `install-shortcuts.ps1` requires Framework `csc.exe`; managed wrapper reads `project-path.txt` and starts the old script/CWD | Prebuild any retained owned wrapper on the Windows build host. Adapt its entrypoint for the bundle; do not ship a wrapper that silently starts old Python/source setup. Publish the stable launch target only with a verified candidate and preserve its prior target for rollback. Probe actual Framework/PowerShell/WinForms requirements, missing/moved pointer targets and shortcut/icon behavior. |
| `WindowsPreparationProcess.command`: current executable image + `__file__` script + job name/child command | Frozen bootstrap dispatch is required **before** child launch, still joins kill-on-close Job Object before extractor spawn. Retain owned handles, verified membership and deadline/descendant waits. Merely freezing a `.py` entry path breaks this contract. |
| ZZZ `_links` derives project with `directory.parent.parent`, then `work/voice-assets`; helper scripts transpile downloaded `.ts` into writable `.mjs` beside metadata | Replace ancestor-depth inference with declared tool/work roots. Collect/prebuild licensed helpers and keep mutable metadata/generated links outside read-only resources; account for Node, TypeScript, WASM module resolution and `node_modules` assumptions. |
| Static `package.json`, `public/mobile-capture/games-data.json`, game tool source/JS/WASM and external extractor data | Resolve active version resources explicitly; collect their relative layouts and notices. Missing data must be a named readiness failure, not fallback to the original ZIP/code version. |
| New 0.22.0 registry-selected adapters/format helpers and Death Stranding game-owned DLL | Enumerate dynamic hidden imports for all 25 active games. Resolve the game DLL only under the validated install; never collect it into resources or use CWD/PATH fallback. Preserve Persona's private shared charset cache and existing worker dispatch. Probe source/frozen indexing and audio paths separately. |
| External tool launches and native DLL search | Declare each executable path and CWD; preserve tool-relative adjacent files. Frozen Windows DLL search-path changes can affect external tools; isolate/sanitize only where proved necessary and test the exact packaged extractor. |

Evidence: [launcher C# shim](../scripts/companion-runtime.ps1#L8),
[separate managed-wrapper compilation](../scripts/install-shortcuts.ps1#L17),
[managed-wrapper dispatch](../launcher/ProxyTranscriptLauncher.cs#L17),
[launcher roots](../scripts/companion-runtime.ps1#L268),
[language builder](../backend/api.py#L281),
[game worker](../backend/local_game_updates.py#L136),
[ZZZ tool/work inference](../backend/zzz_assets.py#L259),
[automatic export worker](../backend/automatic_mobile_export.py#L308),
[native setup actions](../backend/installation.py#L184),
[detached updater](../backend/toolkit_update.py#L208),
[isolated agent ASR](../backend/agent_recognition.py#L268),
[fingerprint child launch](../backend/agent_library.py#L164),
[fingerprint defaults](../scripts/build_agent_fingerprints.py#L37),
[Windows preparation bootstrap](../backend/windows_preparation_process.py#L84),
[active catalog root](../backend/language_inventory.py#L36) and
[PyInstaller external-process guidance](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#launching-external-programs-from-the-frozen-application)
(reviewed 2026-10-28).

Source adapter CWD may remain `codeRoot` for import compatibility. The bundled
adapter must launch successfully from an unrelated directory, a shortcut, paths
with spaces/Unicode and a read-only application slot. No relative path may choose
an unintended data/config file. Temporary/index output stays in a declared writable
root, with same-volume atomic publication when replacing complete files. Static
resources/tool libraries are read-only; tool-generated work must be redirected or
staged under a separate writable workspace. Frozen command dispatch is R19 work;
this research neither implements nor validates it.

## Lifecycle, update preparation and recovery

The current lifecycle is valuable behavior to retain, rather than a reason to
invent a second updater. The wrapper operation lock is an open exclusive file
handle, not existence of a lock filename. Process records include root/start-time/
executable identity checks; unknown/reused PIDs cannot authorize termination or
another capture owner. Route JSON uses same-volume replacement with `.previous`.

| Phase | Existing behavior and v1 requirement |
| --- | --- |
| Prepare application | `update-companion.ps1` stages only owned code/frontend assets into a new `runtime-code` slot, validates/reuses Python or creates a candidate venv, installs locked npm dependencies and reuses/verifies a prebuilt frontend. Existing capture keeps running. R19 replaces development dependency setup with verified bundled resources; data migration is a separate explicit transaction. |
| Start standby | Backend receives `--standby`; warmup starts without capture or normal update jobs. Standby avoids transcript purge/prune. It can still initialize stores/schema and read shared data, so it is **not** an isolated read-only migration verifier. R19 migration probes must use a copied candidate data root. |
| Ready | `/api/runtime/ready` requires successful OCR warmup and, when requested, the active account's selected prepared language/index. Frontend must answer too. `/api/health` alone is insufficient. No readiness call creates remote account state or prepares an unrequested language. Readiness for one game is not proof every extractor works. |
| Quiesce | `/api/runtime/quiesce` stops updates/preparation first, then drains capture before exporting bounded `CaptureHandoff`. Failed/unconfirmed descendant cleanup prevents successful takeover. Preserve lock order and stop/close semantics from `runtime-context.md`; a cancelled future is not proof native work ended. |
| Activate | Warm candidate imports session/duplicate-suppression/cinematic state, resumes capture only if it was running, then starts updates. Use new runtime identity/generations; preserve data/account/locale selection and invalidate old async publications. Do not add a second capture owner. |
| Publish routes | Updater atomically publishes active slot state, retains stable public ports, probes routed API/frontend and retires old owned processes later. Router lets old HTTP requests finish, closes upgraded connections on API target change and retains old static chunks. UI reconnects/reconciles runtime state. |
| Failure/recovery | Preparation failure keeps old runtime usable. Takeover failure restores old route/process state, stops candidate capture with verified ownership before reactivating old capture, then resumes old updates. If shutdown/identity cannot be proved, fail closed with recovery guidance; do not start competing capture. Startup repair distinguishes direct-port legacy installations, missing targets, stale router and unverified live endpoints. |
| Rollback | Application rollback selects a retained verified slot. Data rollback requires its own manifest/snapshot when schema changes; older code must not open an incompatible upgraded writable database. Restore only after all current writers stop. Preserve keys/settings/exports regardless of application rollback. |

Evidence: [update phases and catch recovery](../scripts/update-companion.ps1#L79),
[atomic state and operation lock](../scripts/companion-runtime.ps1#L212),
[verified capture owner](../scripts/companion-runtime.ps1#L170),
[startup repair](../scripts/companion-runtime.ps1#L351),
[router routing/assets](../scripts/companion-router.mjs#L13),
[standby initialization](../backend/api.py#L129),
[runtime endpoints](../backend/api.py#L797),
[handoff payload](../backend/runtime_handoff.py), and
[capture drain/import](../backend/capture.py#L203).

The existing handoff schema carries only running/session and duplicate/cinematic
state; it is not a disk migration manifest. New R12b occurrence/context fields
need an explicit preserve/reset/derive policy and consumer tests before takeover.
R19 must not widen this payload to copy arbitrary account data. Full migration
must also quiesce native setup/tool jobs, manual/automatic mobile exports, pending
audio/reading writes and browser-driven mutations, not just capture. Existing
runtime readiness/quiesce is a starting adapter; it does not prove a global
migration lock, SQLite backup consistency or cross-version rollback.

## Data-root migration manifest and recovery

R19's prototype is opt-in and uses synthetic state plus protected test credentials.
It records a **local private** `proxy-storage-migration-v1` manifest under
`host-v1/migrations/<id>/`; the old ZIP remains untouched. R21 owns actual
installation migration and interruption/rollback acceptance. There is no blanket
"move everything from the old ZIP" operation.

Required manifest fields:

| Field group | Minimum record |
| --- | --- |
| Identity/version | Schema, migration ID, source/target app version+commit/build, layout versions, user/installation binding represented only locally, creation/update timestamps. |
| Roots | Resolved old ZIP/data/settings/credential origins and target roots, source origin aliases/browser profile scope, filesystem/volume identity sufficient to detect a different source. Never publish this manifest. |
| Inventory | Each relative file/group, owner/classification, size/content digest, database format/version and consistency strategy, preserve/copy/rebuild/external-reference action, target and verification result. Unknown files default to preserve; credential bytes never appear. |
| State machine | `planned → copying → verified → ready-to-activate → activated → committed`, plus `failed`/`rolled-back`; last completed atomic checkpoint and failure stage. Record active runtime IDs/ownership proof separately from copied PIDs. |
| Recovery | Old runnable app slot/root, unchanged source data, prior target snapshot when needed, required reader/writer version bounds, forward/rollback steps and credentials/browser verification outcomes. |
| Browser transfer | Per-origin inventory/export schema, destination import result or `unchanged`/`unavailable`; no credentials or file permissions silently claimed as transferred. |

Prototype sequence and acceptance:

1. Explicitly select the old root; validate toolkit provenance/version and refuse
   game/repository/publication destinations, reparse-point escapes and nested or
   overlapping roots. Check permissions/free space on **each** target volume,
   including enough room for copy, retained source, SQLite snapshot, temporary
   work and rollback. Refusal/cancellation leaves source runnable and untouched.
2. Inventory data and the explicitly reviewed legacy `work/voice-assets` groups
   without following links; record unknown/legacy files. Unknown old-root files
   remain preserved **in place**, not automatically copied into tools or published.
   Preserve older `.db` files, calibration and learned/voice mappings. Preserve
   legacy language tables rather than claiming they have been semantically
   migrated. Keep selected export folders external and revalidate availability.
3. Establish cross-root exclusion in this fixed order: acquire the old
   `legacyRoot/data/companion-operation.lock` with its existing exclusive-open
   semantics, then the target `host-v1` migration/runtime lease. If there are
   multiple explicitly selected old roots, acquire their canonical sorted paths
   first; refuse ambiguous roots rather than scan disks. Hold the old lock while
   the candidate can capture/write so the unmodified old launcher cannot restart
   beside it. A copied process record or new target mutex cannot enforce that.
   The launcher/guard design must retain those handles through supervision and
   updates, and prove orderly close, guard crash and process-tree cleanup before
   releasing legacy exclusion. If uninterrupted lifetime exclusion cannot be
   proved without editing the old ZIP, migration activation acceptance is
   **blocked**; R19 may still prove the offline copy and keep the source active.
   The existing updater cannot simply run inside that guard: it calls
   `Enter-CompanionOperation` again on the same old root, and the exclusive lock
   is not reentrant (default wait: 1,200 seconds). R19 needs an owner-aware,
   serialized update operation through the supervising guard, with verified
   installation/process ownership, rather than nested lock acquisition.
   Keep the legacy handle continuously owned across preparation, takeover,
   failure and rollback; releasing it temporarily to let the updater enter
   reopens the old-launcher race. A browser-supplied bypass flag or mere lockfile
   existence is not ownership. Until delegation/continuity is implemented and
   proved, guarded candidate updates and migration activation remain incomplete.
   Lock acquisition alone does not stop an already-running backend or browser
   mutations. Either stop all source writers
   within a deadline or use a supported consistent SQLite backup per database
   while separately snapshotting referenced files. Never copy a live `.db` alone
   and ignore WAL/SHM. Without a consistent strategy, report unavailable and do
   not activate. For a multi-store cutover, quiesce all writers for the final
   snapshot so transcript/audio/export references describe one recoverable set.
   SQLite documents the [online backup API](https://www.sqlite.org/backup.html)
   for one-database snapshots and [WAL behavior](https://www.sqlite.org/wal.html),
   including committed data outside the main database and non-atomicity across
   multiple databases (reviewed 2026-10-28). A series of independent online
   backups is not a coherent multi-store cutover without the final writer barrier.
4. Copy into a new target staging directory; verify digests and database
   integrity/schema, all per-history audio filenames (including hardlinked full
   performances), locale/voice bindings, favorites,
   account-language export completion/destinations and settings precedence.
   Preserve pending/cancelled job states honestly; rerunning an export must not
   repeat a completed remote write because its ledger was omitted.
5. Credentials remain at their existing host locators for v1. For a legacy
   data-key fallback, retain its encrypted bytes in the copied data location;
   validate only under the same user/host with protected **test** blobs. Never
   decrypt into a manifest, shell argument or temporary plaintext file. If keys
   cannot be read, retain source and report reconnect/recovery, not success.
6. Start candidate against the copied root in standby; verify resources,
   readiness and selected paths without remote account writes or real capture.
   Publish an atomic layout/route selection only after verification and proven
   quiescence. Do not let two independent launchers point at the same writable
   root or resume the old ZIP against old data while candidate capture is active.
   Keep both the legacy-operation exclusion and target lease until capture and
   all writers have stopped; do not release them when only the copy finishes.
7. On interruption, inspect manifest/checkpoints and verify actual process/lock
   ownership. Resume an idempotent copy or discard only the owned incomplete
   target; never delete the source. If activation was published, stop/reap the
   candidate before restoring old app/data pointers. Preserve any writes made
   after activation; rollback needs an explicit reconciliation/recovery choice,
   not silent loss by selecting the old snapshot.
   Launcher pointers/shortcuts form a separate checkpoint: record their previous
   values, stage the verified stable target and publish it only with the accepted
   layout/route selection. Prove startup and rollback through the actual Start
   entry and any retained wrapper; after a crash, reconcile these checkpoints
   rather than assume several file replacements are one atomic transaction.
   Preserve or restore the old target on failure. Do not leave the shortcut
   dispatching the old ZIP while the new candidate owns capture, or point it at
   a slot that cleanup can remove. Taskbar pins remain managed by Windows.
8. Mark committed only after restart and round-trip checks succeed. Retain old
   ZIP/data and recovery information by default. Cleanup/retention must be a
   separate explicit policy after R21 evidence; repair/uninstall preserve data.

Known risks to test later include full disk/denied access during checkpoint,
locked files, corrupt manifest/source change mid-copy, Unicode/long paths,
unavailable external drives, different users, duplicate launches, interrupted
activation, incompatible database versions, legacy direct-port rollback and
candidate writes before commit. A file hash proves bytes copied, not equivalent
account/locale/voice behavior.

The lock/update limitation follows from the
[updater's acquisition](../scripts/update-companion.ps1#L17),
[exclusive operation lock](../scripts/companion-runtime.ps1#L252) and
[automatic update entrypoint](../backend/toolkit_update.py#L164).
R19 must include an update while the migration guard is held, plus interruption
and rollback, among its host probes; the current source updater alone does not
establish that future behavior.

## Browser host, origins, API and static experiment

The ordinary desktop page hard-codes API `http://127.0.0.1:8766` and WebSocket
`ws://127.0.0.1:8766/api/ws`. The public frontend is port 3000; private updated
frontends use 3001–3039 and APIs 8767–8799 behind the router. Current backend
access permits browser origins `http://localhost:3000/3001` and
`http://127.0.0.1:3000/3001` only, with exact Host/Origin checks for HTTP,
preflight and WebSocket before dispatch. Missing Origin supports trusted local
scripts; it is not authentication against hostile programs on the same PC.
A public HTTPS Pages origin is not allowed to control the desktop API.

The current [browser opener](../scripts/start-companion.ps1#L18) searches only
Google Chrome's fixed locations, uses a normal window in the existing profile,
and fails to open a browser when Chrome is absent. The backend/frontend are
already started at that point; `-NoBrowser` plus manually opening the canonical
URL is a separate source route. R19 must preserve the user's browser/profile
selection and extension access. Do not introduce a fresh/private profile or
`--user-data-dir` as a packaging shortcut: the same origin in another profile
does not retain the old profile's stores, vault or extensions. Record profile
continuity in the migration manifest and verify ordinary-browser reopening;
real extension compatibility remains separate evidence.

The frontend reads/writes localStorage keys including
`proxy-transcript-reading-mode`, `proxy-transcript-playback-rate`,
`proxy-transcript-reading-options` and account/language-suffixed options,
legacy `proxy-transcript-pinyin-mode`, `toolkit-interface-language`,
`proxy-transcript-source` and shared-reader popup-tab preference. Mobile modules
use IndexedDB `proxy-mobile-library` version 2 with a `state` object store,
including history, calibration/preferences, retained-library registry, OCR model
packs and vault records. Retained library bytes additionally live in OPFS under
`retained-libraries-v1`, separate from the IndexedDB registry. Preserve key names; userscript-managed storage is owned by the extension
and must not be renamed or assumed to exist in page localStorage.

Evidence: [desktop URLs/preferences](../app/companion.tsx#L45),
[local access matrix](../backend/local_access.py),
[mobile storage](../public/mobile-capture/storage.mjs),
[retained OPFS libraries](../public/mobile-capture/retained-library.mjs),
[source identity](../public/mobile-capture/pc-provider.mjs#L1),
[interface preference](../public/mobile-capture/interface-language.mjs#L96) and
[shared reader key](../vendor/lexirise-components/src/reader.tsx#L97).

Origins are scheme/host/port tuples. `localhost` and `127.0.0.1`, port 3000 and
3001, HTTP and HTTPS are different origins with separate browser state. Storage
keys also determine IndexedDB/Cache Storage/service-worker isolation. Thus
copying an app/data directory or preserving a URL path cannot transfer browser
history/preferences. See the [HTML origin rules](https://html.spec.whatwg.org/multipage/browsers.html#origin)
and [Storage Standard](https://storage.spec.whatwg.org/#storage-keys) (reviewed
2026-10-28). The [File System Standard](https://fs.spec.whatwg.org/#dom-storagemanager-getdirectory)
defines access to the origin's bucket file system through
`navigator.storage.getDirectory()` (reviewed 2026-10-28); this is the production
retained-library store's entry point.

The preferred R19 spike serves static desktop assets at the **same existing
loopback origin** and keeps API/WS public URLs and access policy. Its host must
reproduce MIME types, relative/base paths, query/navigation behavior and the
hashed asset lifetime required by old pages during takeover. It must prove that
no server-rendered route/action or Vinext/Cloudflare runtime dependency was
silently removed. A bare filesystem `file:` page is not equivalent; it changes
origin, fetch/worker behavior and extension integration. Preserve the ordinary
browser and Browser Extension route.

Mobile library processing uses a module `library-worker.mjs` resolved from
`import.meta.url`; OCR uses same-host verified worker/core/language assets, WASM,
explicit MIME/CSP and `workerBlobURL: false`. The standalone preview registers
`./sw.js`; the generated service worker uses content-versioned caches, a bounded
public asset allowlist, navigation fallback and explicit update activation.
It ignores non-GET/Authorization requests; it must never cache account API or
private audio responses. Keep old chunks/cache generations while open clients
can still need them, and prove update/reload/offline recovery across the actual
path/base URL. Existing desktop hosting does not gain a new service worker merely
because the mobile preview already has one.

Service-worker registration requires same-origin script/scope and a trustworthy
origin/secure context; worker scripts, module dependencies, WASM and CSP must be
tested from the candidate's actual URL. Browser implementations may differ, so
spec compliance alone is insufficient evidence. See [W3C service-worker registration](https://w3c.github.io/ServiceWorker/#service-worker-container-register)
(2026-09-17 draft, reviewed 2026-10-28), [Chromium security FAQ](https://chromium.googlesource.com/chromium/src/+/main/docs/security/service-worker-security-faq.md)
(reviewed 2026-10-28), [worker creation](../public/mobile-capture/mobile-ui.mjs#L11),
[OCR worker configuration](../public/mobile-capture/mobile-ui.mjs#L118), and
[preview cache generation](../scripts/build-mobile-preview.mjs#L51).

### If a future origin change becomes necessary

No R18/R19 default origin switch is authorized. First inventory the actual old
origins/browser profiles, including `localhost` aliases and PWA storage. Keep
old origins usable as an explicit recovery/transfer adapter. Prove a versioned,
allowlisted transfer in **the browser that owns that state**, not by copying raw
browser-profile databases. Prefer explicit user-mediated export/import for
noncredential preferences/history/library metadata; a constrained local bridge
would require exact origin/source validation, one-use transfer identity, bounded
payloads, no wildcard messaging and tests before adoption. Preserve conflict and
account/language rules; never overwrite populated destination state silently.

Confirm imported counts/identities/favorites/options after reload and restart,
retain originals, and record success separately per origin/profile. An IndexedDB registry alone does not transfer OPFS library bytes: explicitly
copy and verify an allowed library payload through the browser, or re-import
from its original private file and report it as pending until usable. Library File
handles and permissions are not portable; require re-selection and digest
validation where needed. Re-pair/reconnect at the destination instead of silently
transferring bearer keys, remembered credentials, pairing secrets or source
identity. Re-fetch public model/app caches; do not export Cache Storage as user
history. Browser credentials and extension userscript stores need separate owner
flows. If the old origin/profile is unavailable or transfer is unproved, keep
the current host/origin and report the limitation; do not label an empty new
profile successful migration.

## Hosted publication and optional services

Pages may publish only the exact allowlisted generated mobile-preview package:
`index.html`, `games.html`, `build.json`, `.nojekyll`, generated `sw.js`, reviewed
content-hashed UI modules/styles/icons/manifest/catalog, and pinned QR/OCR
JavaScript/WASM/model assets. The independent publisher checks exact top-level
and nested names and bytes; adding a builder asset does not automatically add
publication permission. Static `games-data.json` is public capability metadata,
not an extracted game library. The 0.22.0 refresh adds `retained-library.mjs`
to the independent static allowlist and includes `core.mjs` in preview precaching;
it does not move retained library bytes or vault/history into the publication.
IndexedDB/OPFS remain browser-owned. Reuse the same-origin offline/update checks
for the actual generated asset set. See [builder](../scripts/build-mobile-preview.mjs),
[publication validator](../scripts/mobile-publication.mjs),
[negative publication tests](../tests/mobile-publication.test.mjs) and
[Pages workflow](../.github/workflows/mobile-preview.yml).

Desktop Python/FastAPI, capture, OCR native files, extractors, local file APIs,
DPAPI, databases, recordings, game libraries, private logs/manifests and update
state stay on the PC. A local static host is not permission to publish the
desktop application or expose its API on LAN/public interfaces. Preview assets
must continue excluding localhost API/WS connection permission as the builder
currently does. Runtime-bundle delivery uses the release pipeline, separate from
Pages.

The optional Lexirise gateway is separately deployed fixed-origin transport.
Although it stores no account content in application code and requests
`no-store`, it **processes bearer credentials, requested text/settings/deck or
vocabulary operations and optional audio bytes in transit** and forwards them
to `api.lexirise.app`; provider transport/rate limiting is still involved.
Stateless does not mean no processing. Keep exact origins/operations, bounded
sizes, no payload logging, no generic URL proxy and explicit account-write UI.
This research makes no account calls. See [gateway](../services/lexirise-gateway/worker.mjs#L55).

The pairing relay is another distinct optional service: it holds expiring room
hashes in Durable Object storage and forwards validated packets over WebSockets.
It is not a desktop backend or file store. Keep its TTL/authentication and
end-to-end packet boundary; do not infer a general "everything stays local"
claim from the desktop data layout. See [relay worker](../services/pairing/worker.mjs#L31)
and [protocol](../services/pairing/protocol.mjs).

## Evidence to reuse and work still required

These are inspected existing checks, **not newly executed native proof**:

| Existing source checks | Relevant guarantee and limit |
| --- | --- |
| New-reader tests (`test_persona5_assets.py`, `test_death_stranding_assets.py`, `test_halflife_assets.py`, other twelve-reader format suites) and updated `test_language_inventory.py` | Missing Persona metadata/network or selected-pack failures, bounded archive/media parsing, synthetic reader substitutes and locale/voice/capability states in format fixtures. They do not prove real game DLL loading, absent-pack native playback or frozen hidden-import collection. |
| `backend/tests/test_local_capture_settings.py`, `test_game_paths.py` | Legacy/local calibration precedence, valid manual paths and retired locations. No bundled root migration. |
| `backend/tests/test_accounts.py`, `test_account_request_pinning.py` | Mocked identity/protection, no credential status leak and pinned operations. Mocks do not prove native DPAPI portability. |
| `backend/tests/test_runtime_handoff.py`, `test_language_preparation.py`, Windows process fixtures | Standby/readiness, session/dedup drain, selected account locale, cancellation/atomic index ownership. Native job/process assertions require Windows. |
| `backend/tests/test_toolkit_update.py`, `scripts/update-companion-e2e.mjs`, `scripts/setup-e2e.ps1` | Verified release extraction, failure recovery and current launcher/update behavior; no new bundle/installer acceptance. |
| `tests/companion-router.test.mjs` | Stable routing, WebSocket handoff and old chunk serving with synthetic services. No browser-origin transfer. |
| `tests/mobile-vault.test.mjs`, `tests/mobile-transcript.test.mjs`, `scripts/mobile-update-e2e.mjs`, `scripts/mobile-library-e2e.mjs` | Browser storage/vault/history and cache update behavior in their declared harness. No desktop installed candidate or cross-origin migration. |
| `scripts/setup-build-e2e.mjs`, extracted-distribution checks | Checkout/current packaged frontend with synthetic services; setup-build blocks service workers and uses Wrangler. No proof end-user Node/Python can be removed. |
| `tests/mobile-publication.test.mjs`, publication audit | Static allowlist/private-data exclusions. No license grant for native resources or game content. |

R19 must remove reliance on an externally installed Node/TypeScript for ZZZ
[`extract_voice_links.mjs`](../scripts/extract_voice_links.mjs) /
[`extract_cinematic_links.mjs`](../scripts/extract_cinematic_links.mjs) and
`galgame-perform.ts` execution dependencies as well as the frontend/router
host requirements, or report that game/toolchain blocked. A prepared ZZZ helper
may carry an app-local Node runtime after the component/license closure gates;
it must not run npm or compile TypeScript on the user's PC. The component
inventory owns its exact runtime/modules/WASM resources. A retained unbundled
Wrangler frontend is diagnostic only; shipping an embedded frontend host needs
the decision/proof recorded in the main inventory. A static desktop page alone
cannot satisfy the no-user-installed-Node target.

R19 must supply narrowly scoped source/bundle host contract checks (root
resolution, read-only resources, unrelated CWD, child dispatch, missing resource,
private worker lifetime), an extracted bundle on clean Windows without development
tools, every distinct required toolchain probe, and current-host/static-host
behavior comparison. Use a small representative game/locale sample chosen for
distinct toolchains; each unprobed reader/locale stays explicit. Static failure
keeps the current host adapter. R02b provides measured baseline/startup comparison;
R18 makes no speed/size guarantee.

R20 owns per-user install/repair/uninstall/onboarding; R21 owns interruption,
post-activation writes, old ZIP migration, same-user protected test credentials,
browser-origin recovery and incompatible-schema rollback on the actual candidate.
R22 owns hosted candidate verification, downloaded checksums/provenance and the
separate signing/attestation decision. Native Windows capture/DPI/multiple-monitor
and physical mobile/extension evidence remain necessary where behavior changes.
No Linux product-support or Argo/cluster dependency is introduced.

Only documentation and publication checks apply to this research change. The
integration owner records their actual command results; lack of local native
execution is not a passing bundle/migration result.
