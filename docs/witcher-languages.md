# Witcher 3 language preparation

Supported study/audio locales: English, French, German, Japanese, Korean, Polish,
Portuguese (Brazil), Russian and Simplified Chinese. Each source uses its own
RTSW text and CPSW original speech IDs. Only explicitly requested official
translation tables are read. Missing tables or speech packs are reported without
substitution. Traditional Chinese text is a distinct translation locale.

The in-place Dual Subtitles writer keeps the base file's language first. The
reader removes only its explicit appended translation separator, preserving
wrapped and same-script language pairs. Backup files and unrelated mod archives
are excluded. Base and DLC identities remain scoped, explicit patch containers
can override earlier entries, and conflicting performances at the same priority
are rejected.
Reused base/DLC IDs receive explicit scopes on both performances, preventing an
older unscoped identity from recovering the wrong original voice. Historical
records and cached clips remain intact. Extraction batches cannot mix dubs;
official targets without aligned sentences are reported unavailable.

Public format references: [language markers](https://github.com/0x7A2C9E5D/Witcher3StringEditor/blob/master/Witcher3StringEditor.Contracts/Language.cs)
and [Dual Subtitles writer](https://github.com/maximumspoil/witcher3dualsubtitles/blob/main/dual_subtitles.py).

Validation includes mocked text/audio bindings for all nine supported locales,
missing-pack rejection, DLC identity separation, duplicate-performance rejection,
and same-script wrapped mod layouts. Native extraction reads official text in all
nine study locales. English maps 96,913 dialogue rows with 64,705 voice references;
Simplified Chinese maps 97,834 rows with 64,725 voice references. Two original
samples in each installed dub decode to non-silent audio. The other seven speech
packs and both paid expansions are absent on this PC; native playback for those
packs remains untested. Their format, binding and DLC-priority fixtures remain
enabled.

Synthetic production OCR checks use verified spoken IDs with official localized
text across all nine locales, source/translation/inline/wrapped layouts, and
720p/1080p/4K. Missing dubs use explicitly mocked audio bindings. Browser checks
use German study text with Chinese reading preferences in Chromium/Firefox at
desktop/mobile widths and zoom/DPR emulation. These checks establish no complete
gameplay chapter or branch coverage.
