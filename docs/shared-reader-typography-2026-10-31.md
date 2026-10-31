# Shared reader typography verification — 2026-10-31

Shared reader **1.0.14** fixes the uneven Dutch word baselines and artificial
spacing shown in the supplied screenshots. Optional readings and meanings no
longer move the source text vertically. Meanings fit within their token's width
in at most two lines; the full meaning remains available in the title and
dictionary lookup. Source-word grouping keeps provider-split `churro's` and
closing punctuation together without changing source text or lookup offsets.
Chinese closing punctuation stays attached to its preceding token. Annotated
lookup examples use the same layout rules.

The implementation is in the [canonical shared source](https://github.com/Firebird55/Lexirise-shared-components/commit/6790c34),
with no toolkit-specific typography override or manual vendor edit.
The [hosted release](https://github.com/Firebird55/Lexirise-shared-components/actions/runs/41236684349)
passed at `6a6f004310d42b14532cd9520c3f4b742d0626d9`. All **12** downloaded release
asset hashes matched `SHA256SUMS`; provenance matched the annotated tag commit.
The package SHA-256 is
`100f110b2f87848d148e2ae59be2ec9beed2a15dd6406c8515ed98d44bd9bebd`.

`shared:update -- --version 1.0.14 --all` ran in isolated linked worktrees and
checked both consumers before committing their imports: toolkit `23f9cbe` and
Emulingo `4058769`. The toolkit check reported **278 Node tests passed, 5 skipped**
and **2376 Python tests passed, 19 skipped**, plus five passing subtests, followed
by its production build. Platform-specific skips are not native platform proof.
The Emulingo source regression is committed as `e260c52` and runs in hosted CI.
Its main checkout was fast-forwarded to the checked import without publishing
a new userscript release.

Validation against the imported release passed:

- **29** shared contract tests, including UTF-16 positions, combining marks,
  Latin apostrophes/hyphens, phrase tokens and CJK punctuation.
- **20** Chromium/Firefox × document/Shadow DOM typography cases across
  320, 390, 768, 853 and 1280-pixel viewports, including CSS zoom 1.5. Assertions
  cover source glyph baselines, exact source text, punctuation, bounded glosses,
  long-word wrapping and original dictionary lookup positions.
- **8** Shift-hover gesture cases, **4** existing popup cases, **40** full
  play/panel browser layout cases and Firefox isolated-world settings checks.

The typography screenshots were reviewed locally. Fixtures use authored text
and mocked account transport; no account writes or live game session changes
were made. CSS zoom and viewport emulation are separate from native browser
zoom, Windows DPI and physical phone/tablet acceptance. The remaining native
and physical-device checks remain in the [reader plan](reader-lan-completion-plan.md).

The [upstream compatibility review](lexirise-compatibility-review-2026-10-31.md)
records the preceding 1.0.13 Shift-hover adaptation. This typography release
preserves that behavior and does not change the reviewed upstream baseline.
