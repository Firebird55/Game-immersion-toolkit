# Updating after a game patch

Prepared game languages are checked automatically at startup and every two minutes,
even before those games launch. Game-language refresh and toolkit software upgrades
have separate status displays. See [update reliability](update-reliability.md).

Finish the patch and Mandarin voice downloads in the game's official launcher.
Open **Setup → Games → Refresh game data**. Users can do this on their own PC;
compatible content changes do not require a new toolkit release or a change to
the toolkit repository. The toolkit reads the installation without modifying it.

## What refresh updates

Most adapters rebuild bilingual text and original-voice mappings directly from
installed game files. ZZZ also refreshes its external language/scene metadata.

| Game | Data included in refresh |
| --- | --- |
| Zenless Zone Zero | With the folder empty, the selected Global or mainland China publisher's current text/resource/audio inventories and matching launcher base update dialogue scenes, messages, gameplay tips, clue recordings and translations. Each edition keeps its own metadata and missing translations. Complete raw patch files pass their declared hashes; unchanged base audio uses selective verified chunks. Old snapshots retain their own recordings after edition changes. With installed assets, game-file changes and explicit refresh update maps, scene metadata and voice bindings |
| PRAGMATA | Installed base and patch PAKs, bilingual messages, authored cutscene timelines and verified original Mandarin banks |
| Cyberpunk 2077 | Base game plus optional Phantom Liberty English/Chinese text and Mandarin voice archives |
| The Witcher III | Installed English/Chinese string tables and Mandarin speech IDs under both `content` and `dlc` |

ZZZ comic discovery includes the authored `Data/ScriptConfig/Comic` namespace,
separately from GalGame performances. Comic voice mappings read complete
serialized GUID-to-voice dictionary entries; neighboring subtitle order is not
used. Discovery follows the catalog's explicit bundle dependencies, including
voice dictionaries stored outside the root scene block. Patch catalogs take
precedence over base catalogs. Gender variants require distinct authored text
variants; unknown branches are not guessed. Conflicting associations and
incomplete dictionaries are rejected. An installed-client regression found
1,831 exact comic voice mappings where root-block-only discovery found 701,
and decoded the reported missing bubble from its original Mandarin package.
These are installation-specific
counts, not evidence that every comic presentation passes OCR or that all future
chapters are supported. Existing capture calibration is preserved.

Animated ZZZ scenes also use `CS_` subtitles and separate audio timelines. The
importer follows each typed Mandarin (`CH`) voice track to its authored subtitle
ID and Wwise event, then follows that event's declared bank references to the
original media. This includes media stored in a different bank from the event.
Other languages, ambiguous branches and unsupported timeline edits are skipped.
The reported comic bubble and animated-scene sentence both decoded from the
installed Mandarin packages. No speaker/headset recording fallback is used.
The first timeline scan runs in a background process; unchanged catalogs reuse
its complete local cache. Newly discovered mappings also repair recent saved
comic entries so their original audio becomes playable.

Cyberpunk users select the main game installation, with Phantom Liberty installed
under that same installation. Install its Simplified Chinese language/voice pack
through the game launcher as well, then refresh. Setup reports whether the DLC
is absent, missing text, missing Mandarin voices, or has all language archives.
Index status reports the number of mapped DLC performances. Installing,
patching or removing those archives invalidates the local index automatically.
Base-game use does not require Phantom Liberty. Incomplete DLC language files
cannot borrow a base-game translation or performance with a reused string ID.
V voice selection applies to DLC player variants too. Exact DLC archive/depot
references drive original playback. No DLC files are redistributed.

PRAGMATA refresh extracts base/patch overlays into a new temporary directory,
so files removed by a patch cannot survive from a previous extraction. An empty
index or a game change during extraction rejects the refresh before publication.

NTE publisher preparation reads the selected region's original localization,
dialogue/sequence/movie tables, subtitle cues and localized voice banks. Its
immutable snapshots include compatible public type metadata, so normal content
and type-data updates do not require a toolkit release. Missing regional text,
stale translations and unresolved bindings are reported separately. Saved voices
retain their exact publisher snapshot. NTE index schema 9 rebuilds older prepared
maps with the original movie-alias registry and each referenced StringTable's
exact namespace, including typed CG event references whose object names use
`Play_Vo_*` without repeating `CG`. Compatible game updates can add aliases and
reuse those authored voice-name forms without a toolkit update.
Fixed protagonist branches retain their authored source-text
and translation variants in ordinary dialogue. Unsupported source variants remain
unavailable/unknown, and unresolved target variants are omitted. A repeated
caption with unknown ownership remains unresolved; a successful voice download
alone does not prove automatic caption matching. The installed fallback retains
the separate [NTE_Assets](https://github.com/Waifus-Grace/NTE_Assets) catalog seed
and prefers the installed release's original movie tables and registry when
available. See the [current publisher evidence](game-audits/nte.md#publisher-setup-and-immutable-voice-snapshots).
Honkai's bilingual text hashes and authored event references come from
[HonkaiImpactData](https://github.com/nairieberry/HonkaiImpactData), then are checked
against installed Mandarin banks and sources.

Installed NTE movie bindings and the historical Honkai catalogs check those fixed sources' default
branches once a day while the companion runs. A detected game-file change or
explicit **Refresh game data** checks immediately. Every refresh resolves one
immutable commit first and reads all required files from that commit. Complete
schemas and usable bilingual/event links must validate before the catalog is
published. A changed catalog rebuilds the index even if game files have not
changed. NTE's extracted-event cache also accounts for the catalog change.

Downloaded catalogs are JSON data, never executable reader updates. Sources and
file paths are fixed in the adapter; remote responses cannot choose download
URLs, output paths, scripts or commands. Runtime snapshots retain their source
revision and cache checksums. These checks detect corrupt caches and interrupted
downloads; they do not independently certify an upstream translation's accuracy.
The source is still a trust dependency. Installed-language, event, media and
ambiguity validation remains required for playable mappings.

## Failed updates and coverage limits

An unavailable or incompatible catalog update keeps the last complete catalog
and displays a warning in setup. An existing reviewed cache can be upgraded to
the new snapshot layout offline. A fresh install needs a successful complete
download; the reviewed seed revision is a fallback when the latest source is
unavailable. Failed indexing preserves the previous complete dialogue index.
Changed game files continue to block stale voice extraction until rebuilt.
Private snapshots stay in ignored `data/<game>/catalog-snapshots`; they are not
included in source or installers. Capture calibration and credentials remain
separate and are preserved.

**Honkai's currently available bilingual source remains the older 4.7 catalog.**
This update mechanism does not unlock Part 2 or newer chapters. They become
eligible only when a complete compatible bilingual catalog supplies their exact
authored event references and the reader verifies the corresponding installed
Mandarin source. Do not combine an old language map with a newer dialogue table,
guess IDs, translate OCR text, or substitute recorded audio to claim support.

Changes to archive encryption, serialization, bank layouts, or presentation
formats can still require a reader/OCR change and a normal toolkit release.
Automatic data refresh is not a promise of compatibility with every future
patch. Setup reports catalog availability separately from playable index state.

## Contributor validation

Use synthetic catalogs and mocked downloads. Check same-commit language
consistency, complete schema validation, cache integrity, explicit refresh,
scheduled throttling, offline upgrade, partial-download failure and a changed
catalog with unchanged installed files. Verify that missing or ambiguous
installed voices cannot replace the last playable index. Never commit catalogs,
game text, audio, or credentials. Keep executable dependencies checksum pinned;
data refresh must not install code from a moving branch.

App updates prepare a separate replacement while the current companion keeps translating. Use the new release's `scripts/update-companion.ps1 -SourceRoot <new-release> -Root <current-companion>` for a running installation. OCR and the selected game index warm before capture transfers; open readers reconnect automatically. Game-data rebuilds run at lower priority in separate processes, and matching keeps the previous complete index until the replacement is ready. Failed preparations keep the working version and local data.


## Honkai: Star Rail, Genshin Impact and Arknights: Endfield

Genshin index schema 19 rebuilds ordinary dialogue and reminders with their
authored Traveler text and translation variants, including shared recordings.
Archive reader 4 retains the exact rendered historical identity. Unresolved
source branches cannot acquire audio through historical recovery.

An unresolved source-text branch remains an inventory diagnostic even when the
presentation is confirmed silent. Capture cannot identify it through a rendered
alias or an otherwise valid translation. Independently resolved text-only
entries still follow the unvoiced-capture setting.

Language preparation resolves one immutable revision of the fixed game-data
source. Subtitle tables, dialogue identifiers and voice source paths stay on that
revision for the complete candidate build. Genshin includes Medium and split
subtitle tables; Star Rail includes Main and split tables. Endfield uses its
explicit dialogue and audio tables with the selected VFS voice group. With
the game folder empty, it reads the selected publisher edition's release.
Endfield reader revision 18 also refreshes radio classifications from explicit
empty performer fields and complete same-release sentence/event evidence.
A later nonempty actor mapping restores the existing reaction path; missing
metadata or a missing voice pack is not relabeled silent.
For a new or changed FMV track it follows that dub's subtitle times, voice
event and recording. Saved clips retain the original release and times.
[Endfield release comparison](game-audits/endfield.md). A controlled 1.5.3-to-1.6.4
rehearsal with the same reader covers newly added dialogue, changed text and two
changed original recordings; fresh offline playback retains both saved versions.
The older discovery is replayed and current discovery is live. Scheduled device
activation remains separate acceptance work.
Prepared locales refresh through the normal language worker. Compatible data
changes need no toolkit release; new archive or schema formats require a reader
update. Hito’s World is disabled and no longer refreshes automatically.
