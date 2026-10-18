# NTE language preparation

Study locales are English, Japanese, Korean, Simplified Chinese and Traditional
Chinese. Mandarin audio is shared by the two Chinese scripts. Preparation reads
only requested localization tables and the selected Wwise language's event banks
and media inventory. Numeric media IDs are accepted only through an authored
Play_Vo event whose bank ID and language hash agree with the selected dub.
The translation target comes from the selected learning language's Lexirise
settings. Users explicitly prepare each language; reading settings never
provisions dictionaries or prepares every locale.

Movie cues retain the reviewed catalog's owning subtitle namespace, key and
exact time interval. Zero variants keep the explicit authored Sex_Switch branch.
Ambiguous, layered or unresolved event trees cannot supply guessed performances.
Source packs and translations are checked independently. A missing official text
pack is an error; another script or language is never substituted.

Five locale binding regressions cover official ID alignment, language headers,
matching media paths, missing packs and cross-language batch rejection. Existing
cinematic timing and variant regressions remain enabled. An installed English /
Simplified Chinese build read 109,601 text rows with 14,777 original voice
references. Real ordinary dialogue and a timed movie cue decoded and were
non-silent. Ordinary dialogue and cinematic samples also decode successfully
for every supported locale, including shared Mandarin audio for both scripts.
Synthetic source-only, translation-only and wrapped bilingual OCR checks pass
for all five text locales at 720p, 1080p and 4K.

Fresh installed-asset extraction confirms nonempty official English, Japanese,
Korean, Simplified Chinese and Traditional Chinese tables with 110,260 rows each.
Traditional Chinese uses the authored `zh-Hant` resource, sharing Mandarin audio
with Simplified Chinese while retaining its own official text. Empty placeholder
resources do not count as installed language packs. No complete game chapter or
branch coverage is claimed from synthetic OCR or asset mapping checks.

The tested installation maps 14,777 English, 15,156 Simplified Chinese,
15,140 Traditional Chinese, 14,686 Japanese and 14,643 Korean original voice
references. These are verified subtitle/audio bindings, not a count of distinct
recorded files or a complete gameplay-coverage claim.

Authored double-dash prefixes have bounded OCR aliases for horizontal strokes.
Japanese aliases also tolerate the size of a repeated expressive vowel, while
preserving digraphs and the original official wording. All aliases keep the
original performance binding; collisions remain ambiguous. Other unsupported
dialogue rewrites remain excluded. Korean/Chinese synthetic layout checks use
appropriate fonts for each rendered text block.
