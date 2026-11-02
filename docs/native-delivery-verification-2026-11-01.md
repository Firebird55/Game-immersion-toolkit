# Native desktop verification — 2026-11-01

This record supersedes pending construction observations in the earlier delivery
plans. It separates accepted target packages from final release and installation.
The historical R19 plan retains its broader, unfinished acceptance rows.

The first tag attempt was stopped by the Windows source-integrity gate. The
[metadata investigation](native-release-metadata-2026-11-01.md) records the exact
cause and the required patch-release verification; 0.23.0 remains unpublished.

## Exact target evidence

| Source | Target | Hosted result |
| --- | --- | --- |
| `eb15802` | Windows x64 | Input review, frozen lifecycle, mounted browser, tray and owned shutdown accepted in [run 41313203096](https://github.com/Firebird55/Game-immersion-toolkit/actions/runs/41313203096). |
| `11141a7` | Linux x64 and macOS arm64 | Both targets accepted in [run 41318552161](https://github.com/Firebird55/Game-immersion-toolkit/actions/runs/41318552161), with all six input checks true and no blockers. Windows stopped on source-download transport before freezing. |
| `efdcf85` | Linux x64 | Accepted again in [run 41321715135](https://github.com/Firebird55/Game-immersion-toolkit/actions/runs/41321715135): exact input review, eight frozen checks and actual status/log windows, tray, both mounted-browser acknowledgements and owned shutdown. The target receipt has `candidate: false`, `release_eligible: true` and `native_acceptance: approved`. |
| `0ec5f5f` (`v0.23.1`) | Windows x64, Linux x64 and macOS arm64 | All final browser, native and publication gates passed in [run 41340575864](https://github.com/Firebird55/Game-immersion-toolkit/actions/runs/41340575864). The [release](https://github.com/Firebird55/Game-immersion-toolkit/releases/tag/v0.23.1) is published. |

These are separate source identities. Earlier candidates do not substitute for
the final tag's checks. All 24 release assets were downloaded; the 23 checksummed
payloads and all three platform provenance records were independently verified.

## Completed construction corrections

Production resources include the pinned compiler-free ZZZ scene reader and
source-built decoder. Its [acceptance record](zzz-runtime-acceptance-2026-11-01.md)
distinguishes synthetic native checks from private installed-file verification.
All games use the common capability and missing-pack states; historical private
experiments do not authorize or restrict the production resource profile.

The Ubuntu closure is independently checked against authenticated package/source
metadata: 83 binary packages, 63 source packages, 160 complete notices and 288
retained archives. Exact source versions and native-library identities are
verified before target acceptance. macOS freezing preserves immutable toolchain
resources byte for byte, while native Python/Qt dependencies retain their
platform-specific verification.

Actual native browser evidence requires the production transcript to mount and
report positive layout for separate startup and tray-open challenges. Completing
a browser-opener command alone does not pass. macOS final reports are written
before owned Qt shutdown. Windows gateway socket-reset cleanup closes and
detaches the connection without suppressing unrelated errors.

## Installed delivery and preparation follow-up

The verified 0.23.1 Windows installer completed the authorized source-to-native
[handoff](native-installation-handoff.md). Installed executable identity and both
shortcut choices were checked. The native application started with retained
settings, calibration and protected profiles; browser opening and local/LAN
serving were observed. Physical-device acceptance remains separate.

Installed use exposed a preparation child inheriting the API's actively read
shutdown input pipe, blocking frozen Python startup. A real Windows reproduction
failed before the fix and passed with independent empty input. The shared fix and
a mandatory frozen preparation/control-pipe probe are committed for
[0.23.2](releases/0.23.2.md); that release's frozen acceptance is still pending.
A separately prepared, fingerprint-validated Beyond Dutch catalogue restored
capture after confirmed host shutdown, with the learning/translation selection
preserved. This temporary local recovery does not replace the permanent update.

Packages are unsigned. Intel macOS, physical iOS/Android devices, Wayland capture,
every gameplay presentation and absent voice packs are not established by these
hosted results. The [screenshot plan](capture-regression-completion-plan.md)
retains missing fixtures for other games explicitly. Broader R19 device,
installer-interruption and recovery scenarios remain separate from target
package eligibility.
