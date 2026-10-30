# PRAGMATA languages

Prepare a language explicitly in **Setup → PRAGMATA → Languages**. Preparation
reads that language's installed dialogue banks and official message tables.
Opening settings or adding an account does not prepare other languages.

Study text and original voices support English, French, Italian, German,
Spanish–Spain, Spanish–Latin America, Portuguese–Brazil, Russian, Simplified
Chinese (Mandarin), Japanese and Korean. Official sentence translation targets
also include Traditional Chinese, Polish and Arabic. Internal reserved MSG
language slots are not advertised as official translations.

The translation target comes from the selected learning language's effective
Lexirise target. An unavailable or unprepared target is reported explicitly;
there is no generated translation or English substitution. Word lookup remains
demand driven and uses that learning language's account preferences.

MSG columns are selected by authored language identifiers. Dialogue audio uses
authored SoundID events; cutscenes use authored timeline GUIDs and intervals.
Only the selected localized bank can establish an installed voice binding.
Ambiguous events, conflicting timeline bindings and unresolved text references
cannot borrow another performance or become partial official translations.
Localized bank preparation includes authored banks whose names do not end in
`dialogue`. Narrative archive bodies and archive conversation/hologram pages are
indexed separately as readable text; menu labels, item labels and archive
headings are not dialogue. Missing audio does not prove an entry is unvoiced.
Base archives are read before patch archives, and changed archives invalidate
the complete index. A failed replacement keeps the previous preparation.

The [dialogue coverage audit](game-audits/pragmata.md) records the current
Simplified Chinese inventory and its remaining unavailable/unknown voices.
Earlier per-dub validation predates the expanded bank selection and readable
categories, so its counts are not the current completeness measure. Dialogue
and cutscene samples were previously decoded in every dub; the latest audit
also decoded two recovered Mandarin bindings. Counts describe indexed bindings,
not exhaustive playback verification. Production OCR regressions cover every study language
at 720p, 1080p and 4K using synthetic official text fixtures, including wrapped
bilingual layouts. They are not native gameplay or full-game footage coverage.
Chromium/Firefox reading checks exercise localized study text and original
audio controls across desktop/mobile widths and browser zoom/DPR emulation.
