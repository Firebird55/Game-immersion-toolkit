# Live-service subtitle completion

Owner acceptance scope, agreed November 16, 2026, for issues #83–#88.
The endpoint is reliable subtitle support and autonomous normal content updates.
It does not require cataloguing every sound without subtitles or cutting every
film utterance at word boundaries. No release is requested.

Desktop Capture setup provides separate, default-off controls for confirmed
unvoiced dialogue and **Include subtitles without available audio**. The latter
requires adapter evidence that a record is authored, displayed dialogue; generic
localization entries do not qualify. Matching is exact and complete, respects
player and presentation restrictions, and rejects unresolved text branches or
ambiguous duplicates. It retains `unknown` or `unavailable` audio status rather
than declaring silence or attaching a generic reaction. History and favorites
survive disabling the control and restarting. Desktop exports and paired-PC
phone history retain that status; text-only Lexirise saves include an honest note
and never upload reaction audio. Standalone phone catalog preparation retains its
existing per-game coverage gates; this control applies to desktop capture.
The paired-PC transport's existing length cap is explicit: a shortened subtitle
cannot retain complete-caption evidence or be saved as a full sentence on the
phone; its full original remains readable and exportable on the PC.

## Fixed audit bases

Use these published generations as the starting inventories. Later publisher
changes require a delta audit; they do not invalidate unchanged evidence or
restart an entire game audit. Regional resources and dub revisions are separate
identities even when their displayed version numbers agree.

| Issue | Game | Starting generation | Detailed evidence |
| --- | --- | --- | --- |
| #83 | Genshin Impact | 7.2, resource 49411577 / design 49419538 / silence 49291486, independently discovered Global and mainland editions | [Genshin](game-audits/genshin.md) |
| #84 | Honkai: Star Rail | Global 4.7, including the original Lua revision 17175930; regional editions tracked separately | [Star Rail](game-audits/starrail.md) |
| #85 | Zenless Zone Zero | Global and mainland 3.3.0, resource/design 20245314, audio 19815450, silence 20080629 | [ZZZ](game-audits/zzz.md) |
| #86 | Arknights: Endfield | Global 1.6.4, resource 11775769-12; regional publisher inventories tracked independently | [Endfield](game-audits/endfield.md) |
| #87 | Wuthering Waves | Global launcher 3.8.0 / core 3.8.11, independently selected dub manifests and mainland edition | [Wuthering Waves](game-audits/wuwa.md) |
| #88 | Neverness to Everness | Global 1.5.4 and mainland 1.5.6; separate manifests and all official dubs | [NTE](game-audits/nte.md) |

These are audit anchors, not an assertion that the inventories are complete.
Each game report must count actual presentations, locales and relevant player
branches: conversations/choices, subtitled ambient/radio lines, films/in-engine
scenes, tutorials/comics and the messages/readables already within its ticket.
Totals of all text files are not story-coverage denominators. Classify active
content, proven unused authoring and historical test content separately.
Historical assets still called by the released game remain in scope.

## Audio outcomes

An individually recorded subtitle retains its original text, translations,
speaker, player branch and exact recording. A film subtitle may instead use a
verified **context clip** containing the entire corresponding utterance and
some surrounding audio. Its film, dub, player branch and playback clock must be
established. Display clocks alone do not establish that words fit inside a cut.

Adapters explicitly emit `audio_scope: "context"` only after that binding is
verified. Capture/history, PC sharing and Mobile Libraries retain this scope;
desktop/mobile playback labels it as context. Sentence exports may include the
audio with a context note. This metadata does not establish a binding, turn
unknown audio into voiced dialogue, or bypass a decoder's duration limits.
Different translations cannot be disambiguated merely because they share the
same context recording.

`line` retains individual-utterance behavior. `paragraph` retains its existing
whole-recording behavior and omission from automatic sentence-audio uploads.
Legacy `playback_scope: "full_track"` still forces `paragraph`; an adapter cannot
relabel that fallback as a verified context clip without a new binding.

Text accompanied only by a generic reaction remains supported as text. Do not
offer that reaction as a recording of the written sentence. Authored unspoken
text uses the existing opt-in unvoiced capture. Unknown/missing audio stays
explicit and does not imply silence. Missing official translations are reported,
never invented.

The Endfield 89 radio groups are a text-presentation inventory, not a promise of
one sentence recording per row. Resolve reaction categories through their shared
source mechanism and one targeted gameplay check. Resume only for new evidence
of an omitted subtitled utterance or an incorrect binding. Historical technical
test cuts alone are not current-game completion requirements; check whether the
current game actually uses their subtitles before counting them as blockers.

## Autonomous update acceptance

For each game, freeze toolkit code, helper versions and third-party data. Prepare
one official version without a game installation, then let the same software
discover another official version or substantive hotfix. Verify added/changed
subtitles, translations and audio, retained older recordings, a fresh process,
and recovery after an interrupted download. A version-number-only change is
insufficient. Recorded/replayed baseline discovery must be identified explicitly.

Existing third-party software, keys and format descriptions may remain pinned.
New content must not require a new third-party data publication. Attempt to derive
changed parameters and table descriptions from official client files before
classifying a failure as an unsupported format/protocol change. New IDs, moved
files, additional packages and missing data need representative regression tests.
Failed preparation must retain the last usable generation.

## Closure

Close an issue only after its current subtitle inventory is accounted for, all
available active subtitle audio has correct bindings, the required regional/
language/player variants are covered, the frozen update/recovery trial succeeds,
and representative real playback plus inventory-wide checks pass. Keep docs and
support summaries current and run the required publication/check gates.

Exact sentence cuts and exhaustive listening are not closure requirements.
Unsubtitled audio can be a later extension, but real subtitle gaps cannot be
moved there. A demonstrated official-data limitation needs precise evidence and
the smallest necessary decision, not an unsupported claim of complete coverage.
