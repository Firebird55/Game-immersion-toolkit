# Reverse: 1999 source and coverage audit

Status checked **2026-11-17**. Tracked in
[#144](https://github.com/Firebird55/Game-immersion-toolkit/issues/144).
This is provider research and tested public launcher discovery, **not a playable
toolkit adapter**. The game must remain unavailable for preparation until its
original text/voice pipeline and standalone Android path work.

## Official releases and languages

The [Global publisher website](https://re1999.bluepoch.com/) advertises 3.9.
Its current [bootstrap script](https://re1999.bluepoch.com/assets/js/api.js)
supplies the page version and game ID for the publisher's read-only website
version query. That query returns the original installer URL. Discovery reads
the current script each time; it does not freeze a game version or installer.

The [publisher Steam listing](https://store.steampowered.com/app/3092660/1999/)
lists English, Japanese, Korean and Simplified Chinese voice support. Traditional
Chinese has interface/subtitles and shares Mandarin recordings; it is not a
fifth independently recorded dub. The publisher's original client archive also
contains `CH`, `EN`, `GT`, `JP` and `KO` bootstrap locale files. This confirms
containers, not complete translation/recording extraction. German, French and
Thai named resource containers also exist in the current archive; file names
alone do not establish complete officially supported translations.

The [mainland publisher site](https://re.bluepoch.com/) advertises a different
release, 4.1. Its own
[bootstrap script](https://re.bluepoch.com/assets/js/api.js) and version query
return official Android links on `d.bluepoch.com`. Regional identity must stay
separate: Global 3.9 assets cannot stand in for mainland 4.1. An initial HEAD
request for that official APK returned HTTP 567; no current mainland APK or
regional text/voice playback has been verified.

## Publisher discovery implemented

`backend/reverse1999_release.py` uses Python's standard library. The initial
public app/channel profile was identified in the
[launcher profile implementation](https://github.com/Peebify-Launcher/peebify-launcher-lite/blob/0fdb84bf39d27a5128178475ef728ffb6dd22656/src-tauri/src/backend/game_profiles.rs)
and then verified against the live publisher service. That reference is protocol
research, not a runtime community dependency or source of game assets.

Public read-only queries to the publisher's
[`/diff-update/version`](https://hotupdate-hw.sl916.com/diff-update/version) and
[`/diff-update/resource`](https://hotupdate-hw.sl916.com/diff-update/resource)
returned **Global Windows 3.9.0, resource 111.0.1065**, with 20 original archive
URLs on `download.bluepoch.com`. Each URL carries its original size, expanded
size, MD5 identity, app/resource revision and archive part identity. Discovery
validates totals, ownership, region/version agreement, duplicate parts and
allowed HTTPS hosts. It rejects redirects and oversized/truncated metadata.

The ordinary module, rather than only a research script, performed all four
public discovery requests successfully. The resulting source fingerprint was
`52b2507337ac94ef69ce248cfa9090f45f76968d945c11f9535802a775cb0400`.
This is **one actual generation**, not an actual A-to-B update acceptance test.

| Exact manifest value | Bytes | Scope |
| --- | ---: | --- |
| Download | 29,139,635,761 | Complete original Windows client archives |
| Expanded | 33,181,309,025 | Complete original Windows client |
| Dialogue preparation download | Unknown | Selection and hotfix inventory unresolved |
| Prepared dialogue disk use | Unknown | No prepared catalog or decoded audio yet |

The complete-client numbers must never be shown as a dialogue-only download
estimate. Return values explicitly mark this distinction and
`dialogue_preparation_implemented = false`. No installer, original game code or
client executable is executed. The module does not download any archives.

Bounded research range reads of all 20 original 7z headers were validated with
their start/header CRCs. They expose original bundle, language, Lua container,
`allmanifest.dat`, video and audio paths. Those receipts are private metadata;
no original assets are committed. The headers use LZMA1; payload folders use
LZMA2 and, for executable files, an x86 filter. Large solid folders make efficient
selective extraction an open engineering issue. Header inspection is not proof
that a selected asset's full publisher MD5 has been verified.

The launcher archive inventory is **not the in-game hotfix catalog**. Static
protocol research identifies separate patch-version and optional voice queries.
An initial optional-voice request without the game-generated metadata header
returned an authorization error. A partial patch query returned `0.0.0`; it is
not accepted as the live version. Their complete public bootstrap, response
ownership, ordinary update behavior and selected original download format still
need verification. Account login, a running game or captured user credentials
must not become prerequisites.

## Finite dialogue coverage boundary

Inventory current accessible dialogue and official regional languages. Do not
spend indefinitely on orphaned references, removed event content or audio without
captions. None of the following is implemented or classified as silent yet:

| Presentation to verify | Required authored evidence |
| --- | --- |
| Story conversations, narration and choices | Story group/step text IDs, translation IDs, authored voice event IDs and explicit silent choices |
| Character voice/archive and battle/ambient captions | Character/event/locale binding; confirm which sounds actually have visible captions |
| Event and other side-story presentations | Current entry points and the same original step/audio schemas, including moving text |
| Cinematics and text over videos/images | Original caption timing, locale tracks, audio ownership and independent screen regions |
| Readable pages/messages and special layouts | Current accessible text tables and explicit voice state |

Static schema research identifies story step/group JSON inside original Unity
bundles, and audio configuration fields for bank and event names with overseas
variants. These are leads for original-file validation, not implemented bindings
or permission to substitute community audio. Missing recordings stay unknown or
missing-pack; they must not become unvoiced by inference. Short repeated text
must use authored scene/step context where available.

## Remaining implementation and acceptance

- Discover current Global/mainland bootstrap and in-game hotfix inventories from
  original publisher data, including optional dubs absent from a local device.
- Read the original selected metadata, translations, story layouts and audio
  event/bank/media relationships without evaluating game Lua or binaries.
- Implement portable archive/bundle/localization readers and original audio
  decoding, then exercise them inside the Android runtime. Standard-library
  discovery alone is not Android extraction or playback acceptance.
- Integrate the common Android/PC data manager: per-game download/delete,
  manifest-based transfer estimate, actual retained bytes, cancellation,
  interruption recovery and previous-complete-catalog retention.
- Prove two actual publisher generations without new external extraction or a
  toolkit update. Synthetic ordinary-version fixtures already cover discovery.
- Add support registry, detection/setup/capture/export regression coverage,
  public game metadata, README/install instructions and generated language
  guides when a functioning adapter is ready. Keep this issue open meanwhile.

Owned synthetic fixtures currently exercise public metadata decoding,
ordinary-version refresh, announcement-insensitive fingerprints, original
archive ownership and totals, malformed/oversized data, network fallback and
HTTP response integrity. No game text, recordings, keys or executable files are
test fixtures. No installed-game or physical-device playback is claimed.
