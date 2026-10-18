# ZZZ language preparation

Prepare English, Japanese, Korean, Simplified Chinese or Traditional Chinese
explicitly in Setup → Languages. Both Chinese scripts use original Mandarin
audio. Only the selected source and requested official translation tables are
read. Account reading preferences and translation targets remain specific to
each learning language; dictionary operations remain demand driven.

TextMaps and scene configuration come from one pinned revision of the existing
[extracted game-data mirror](https://git.mero.moe/dimbreath/ZenlessData). Installed
GalGame/comic scripts and cinematic timelines supply authored subtitle/source
or event bindings. The selected installed voice pack supplies the exact Wwise
namespace, bank language, external source hash and original media. Namespace
names are read from the pack rather than assumed from another game's language
codes. Persistent patches take precedence over base packages. Ambiguous sources,
unsupported schemas and changed files cannot supply a guessed performance.

Free-roam and tip dialogue follow the authored configuration's text ID and
default/alternative voice fields. Both supported field schemas retain the
explicit Belle/Wise roles. Unknown schemas fail preparation instead of silently
removing those conversations. In Capture setup, choose **Proxy voice** when a
caption cannot distinguish the variants. An exact distinguishing subtitle can
identify its own authored performance. Variant IDs keep originals independent;
historical Chinese comic identities remain visible and cached clips are retained.

Game sentence translations use aligned official text only. Missing targets are
reported unavailable without English substitution or generated translations.
Historical audio retry reads the stored locale's existing index, without
preparing another language or changing the current selection. Independent
Migaku mode and userscript storage keys are unchanged.

The tested installation maps 66,704 English, 67,055 Simplified Chinese, 67,055
Traditional Chinese and 66,926 Japanese voice references. These are bindings,
not counts of distinct recordings. Original dialogue, comic, gameplay, tip and
cutscene samples decode successfully, as do explicit Wise/Belle samples in each
installed dub and both Chinese text scripts. Korean's pack is absent locally;
its native playback remains untested, with authored binding fixtures and an
explicitly mocked audio binding for OCR evidence.

Synthetic production OCR checks cover all five text locales, source/translation/
inline/wrapped layouts, and 720p/1080p/4K. Chromium/Firefox checks cover Japanese
study with Chinese reading preferences, original audio, local Proxy selection,
legacy Chinese comics, mobile widths and zoom/DPR emulation. These are asset,
format and synthetic regression checks, not native gameplay or complete chapter
and branch coverage.
