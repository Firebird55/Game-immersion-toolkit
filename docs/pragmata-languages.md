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
Base archives are read before patch archives, and changed archives invalidate
the complete index. A failed replacement keeps the previous preparation.

Validation on the installed assets found 3,889–3,906 study lines per dub, with
3,742–3,757 original voice bindings. Dialogue and cutscene samples decoded to
non-silent audio in every dub. Counts describe indexed bindings, not exhaustive
playback verification. Production OCR regressions cover every study language
at 720p, 1080p and 4K using synthetic official text fixtures, including wrapped
bilingual layouts. They are not native gameplay or full-game footage coverage.
Chromium/Firefox reading checks exercise localized study text and original
audio controls across desktop/mobile widths and Windows DPI settings.
