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

Public format references: [language markers](https://github.com/0x7A2C9E5D/Witcher3StringEditor/blob/master/Witcher3StringEditor.Contracts/Language.cs)
and [Dual Subtitles writer](https://github.com/maximumspoil/witcher3dualsubtitles/blob/main/dual_subtitles.py).

Validation includes mocked text/audio bindings for all nine supported locales,
missing-pack rejection, DLC identity separation, duplicate-performance rejection,
and same-script wrapped mod layouts. An installed English/French build mapped
96,913 official dialogue rows and 64,705 original voice references. An original
English voice decoded successfully and was non-silent. Only English and Mandarin
speech packs are installed on this test host; other locales have format/binding
regressions rather than decoded real-audio evidence. Synthetic OCR resolution
checks are distinct from gameplay footage and establish no chapter coverage.
