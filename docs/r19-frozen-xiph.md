# R19 Xiph FLAC integration in the extracted runtime

Status: implemented and verified on hosted Server 2025 in the quarantined
runtime-experiment profile, within the bounded scope below. Production runtime and
general game-codec acceptance remain disabled. PR #59 is unchanged and no
installer is built.

The subsequent [rights/source/maintenance review](r19-xiph-distribution-review.md)
retains the exact source kit in Git, defines the delivery/maintenance policy and
records an unresolved custom build-recipe license condition. It changes no
runtime pin or acceptance flag.

This continues the [selected source-built Xiph FLAC 1.5.0 candidate](r19-codec-replacement.md).
The old [Gyan FFmpeg artifact](r19-codec-artifact-review.md) remains rejected and
is no longer collected in the integrated experiment. Source-mode FFmpeg behavior
and unrelated game/language/account behavior remain unchanged.

## Exact resources and bounded operation

The build host builds the same selected source/configuration and checks the
previously verified executable/DLL hashes before collection. The runtime resolves
only codecs/xiph-flac/flac.exe and its exact FLAC.dll through the frozen
resource manifest. Notices and the complete codec-sources.zip are bound by fixed
hashes and carried alongside them. The source kit remains SHA-256
7dc11c7fc0c87c6304b0d09af81d76a4d6229c15ce8590681a74e14ca85d2f6b.

Preparation compares the clean current source commit, build configuration,
original upstream tarball, all source-kit/recipe bytes, notice inventory and
selected binary hashes before writing a new output. Collection checks current
preparation/resolver/recipe source hashes and exact nested/outer inventories.
The old wheel interface, old manifest kind/schema and old binary are refused.
The integrated output probe also rejects any collected FFmpeg executable.

The explicit experimental_flac_decoder still permits only native FLAC,
16 kHz mono 16-bit samples, at most one second and at most 1 MiB of input.
The CLI uses fixed decode/raw-PCM/little-endian/signed arguments and a validated
sample endpoint, with no caller-supplied switches. Canonical input/output files
must share one private work directory; filenames follow an end-of-options marker.
General ffmpeg_executable remains unavailable in bundle mode.

PreparationJob owns the process tree, deadline and cancellation checkpoints.
Output is private until successful exit, exact expected byte count and confirmed
process cleanup; publication is atomic and failed attempts preserve prior bytes.
No compiler, runtime download, PATH lookup or rejected-codec fallback is added.

## Actual DLL-origin observation

The existing Windows bootstrap now clears the inherited PyInstaller DLL
directory with SetDllDirectoryW(NULL) before spawning a native helper. This is
process-local to the bootstrap; the main frozen process retains its own loader
configuration. [PyInstaller documents inherited DLL-search changes](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#launching-external-programs-from-the-frozen-application),
which can otherwise make an external executable use the bundle's libraries.
The bootstrap also forwards its redirected stdin/stdout/stderr explicitly when
creating the console-free native process. Leaving all three as None bypasses
Python's explicit standard-handle setup; [Windows pipe redirection uses those
startup handles](https://learn.microsoft.com/en-us/windows/win32/procthread/creating-a-child-process-with-redirected-input-and-output).

The codec probe holds an owned stdin decode open long enough to observe the
actual flac.exe process. Process IDs come only from its existing Job Object;
retained handles are checked for membership before remote module queries.
The probe observes the real Job Object constructor to obtain that handle; no
module list, Win32 behavior or process outcome is mocked.

The observed application images must be exactly the pinned sibling flac.exe and
FLAC.dll. VCRUNTIME140.dll and ucrtbase.dll must resolve under Windows, rather
than from the Python bundle or a developer directory. All loaded images in the
snapshot are recorded as relative application names or Windows basenames with
SHA-256, never host profile paths. An extra application image, wrong hash,
unknown origin, duplicate or missing required image fails the probe.

Authored invalid FLAC.dll and VCRUNTIME140.dll bytes in the process CWD test
search-order isolation. After observation the same process receives the authored
FLAC stream, must emit all expected PCM bytes and finish with owned cleanup.
This is an actual snapshot followed by successful decoding, not proof that every
possible future input can never trigger another dynamic load.

## Failure cases and application integrity

Missing/corrupt DLL cases use independently owned copies outside all runtime
roots. They must fail manifest resolution before native execution. The original
read-only application tree is never modified to inject faults.

The normal frozen adapter separately decodes the non-silent 512-sample authored
frame to all 1,024 expected PCM bytes, SHA-256
e153774c8d06b094341ec9eb1e1f53571d3398a01cfd6526df97bc073f7ef379.
Pre-cancellation, an owned deadline and a truncated frame must retain prior
output, remove attempt work and confirm owned shutdown. The complete outer
application file/directory inventory, including Hidden/System entries, must stay
unchanged. No game files, accounts, user recordings or existing stores are used.

Cheap contracts additionally cover missing notices/source kit, changed/absent
DLLs, forged promotion/source states, the legacy codec kind, wrong PE/policy,
out-of-scope stream metadata, canonical work paths and invalid module-origin
records. Bootstrap contracts protect join-before-spawn and reset-before-spawn;
actual Windows process-tree checks remain separate from source mocks.

## Explicit acceptance boundaries

The selected covered source/build kit accompanies this experimental candidate.
Durable production source hosting, exact-output licensing/notice acceptance,
ordinary-user VC/UCRT prerequisites and servicing review remain open.
Clean Windows 11 25H2, capture/OCR/DPI, Framework/WOW64, installed-game formats,
other codecs and full export still need their own evidence. Server 2025 does
not close those gates. Every receipt keeps production execution false, Windows
11 unavailable and R19 incomplete. No installer/release/tag/Pages publication
or live migration is part of this integration.

## Local checks

The affected source contracts passed: **164 tests, four Windows-only skips and
five unittest subtests**. The first combined run exposed an older mocked kernel
fixture without the newly required SetDllDirectoryW method; the fixture was
updated and its join/failure assertions retained. No native case is credited
from these mocks.

Stable changed-check record f5ee2fb9-8166-4e33-8725-78f447e52b78 resolved actual
upstream/main at ba0b7c34c358f1664220674e5ff8bb7f30502e5f with an unchanged source
fingerprint. Typecheck and 271 Node tests passed (one skipped), then macOS Python
collection lacked pyaudiowpatch; later aggregate checks did not run.
The earlier record a4b2e172-82fe-406f-b243-10a7c12e1844 was source-invalid after
a test fixture changed during execution. Neither aggregate is a full pass.

After the native standard-handle/prefix corrections, stable record
4565f697-e8e8-49a9-9f74-2ab1f60cdfb8 resolved that same actual target and source
fb1b014ec42aac125c159dcb10ef5f88d4d109f2. Typecheck and 271 Node tests passed
(one skipped), then collection again lacked macOS pyaudiowpatch. Later checks
did not run. Its preceding sandbox record d6724d94-6c75-4573-8ecd-538a4fdd16d1
failed nine listener tests with EPERM; the unchanged host repeat above passed
those tests. These failed/incomplete aggregates are retained, not full passes.
The final documentation-only selector record
3ded46a4-657a-4b7e-94b8-a56a02c458f8 conservatively selected full checks for
packaging/runtime-bundle/README.md and again failed the sandbox listener cases;
source remained stable. Explicit generated-guide/link and public-audit checks
passed separately; no full aggregate pass is inferred from them.

## Native attempts and source control

[First integrated run 41106438193](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/41106438193)
at 0ff46bbd4bf8ec7a74bc50f8c071ac0994297ac2 built the selected bytes and reached
the expected codec DLL inventory, then failed the held-stdin decode completion.
It is a failure, not decode evidence. A source-mode control at cfd538a then
exposed an observation-path assumption: an executable directly at the candidate
root was compared as ./flac.exe rather than flac.exe. The probe now handles both
root and nested placement; bootstrap standard-handle forwarding is explicit.
No expected PCM, DLL-origin or process-cleanup assertion was removed.

[Windows source-control/rebuild run 41108865731](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/41108865731)
passed at clean fb1b014ec42aac125c159dcb10ef5f88d4d109f2. Both the selected
build and a new build from the delivered source kit passed real DLL observation,
same-process stdin decode, normal file decode, cancellation/deadline/truncation,
previous-output retention and owned cleanup. All seven actual loaded images
were identical across those two probes: pinned flac.exe/FLAC.dll plus Windows
KernelBase.dll, kernel32.dll, ntdll.dll, ucrtbase.dll and vcruntime140.dll.
Source Python owns these standalone probes; frozen acceptance is separate.

Downloaded artifact 13002391818 matched outer ZIP SHA-256
8056ac6e2879b3443ec4a6ba36d70d92a964aec79415b6bdb2a35266b7c1a60f.
Its exact five outer entries, complete source kit, original tarball, raw source
receipt hashes and canonical Git recipe bytes were independently checked.
Both binary/notices inventories, PCM/failure/cleanup/module records and disabled
production/Windows 11/R19 fields matched. The source kit retains its original
7dc11c7f digest above. No executable/DLL or raw process logs were uploaded.

## Verified frozen runtime and downloaded metadata

[Integrated Windows run 41109324682](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/41109324682)
passed at clean fb1b014ec42aac125c159dcb10ef5f88d4d109f2 on hosted Server 2025,
image windows-2025-vs2026/20261030.294.1. **177 affected Windows contracts**
passed, followed by the source build, exact preparation/collection and actual
relocated frozen probes. Build identity: runtime-experiment-41109324682-1.

Both held-stdin and normal file decoding produced the expected PCM. Missing and
corrupt DLL copies were rejected before execution; pre-cancelled, deadline and
truncated attempts retained prior output and completed owned cleanup. Invalid
CWD DLL bait was ignored. The actual codec snapshot contained exactly the two
pinned application images plus six Windows images: KernelBase.dll, apphelp.dll,
kernel32.dll, ntdll.dll, ucrtbase.dll and vcruntime140.dll. The extra Windows
apphelp.dll compared with the standalone control is recorded, not discarded.

| Actual codec image | Origin | SHA-256 |
| --- | --- | --- |
| _internal/codecs/xiph-flac/flac.exe | Application sibling | 959b7871c00598360734b3792e24b369de6a08f91c02d18abaa7678488b9a355 |
| _internal/codecs/xiph-flac/FLAC.dll | Application sibling | 29c4c88bc8cb17e30aaef2d9af50455abeeccc59bda18d1189dfb7568d9e27d8 |
| vcruntime140.dll | Windows system | d1f4225df2cd877dbf130d5668a021dce3f94118455ff5ec952061c30afc9ce7 |
| ucrtbase.dll | Windows system | 9601850e2ede2cd86b441223557cae0fa7f5e33b1dd9d481c58c8cc2d688bdc3 |

The same run passed all 25 native registry-reader imports, authored VAD/worker
cases, isolated ASR native import, NTE app-local identity and frontend/API
HTTP/WebSocket/Setup probes. Application files were read-only during execution;
complete pre/post inventories including Hidden/System files and empty directories
matched. Owned process/fixture cleanup passed. API background side effects were
mocked; actual ASR inference, installed-game playback and OCR/capture were not run.
This workflow does not execute the full browser matrix or required PR merge gate.

Downloaded metadata artifact **13003287373**, **1,190,415 bytes**, matched ZIP
SHA-256 38376b6c10010daf3845c98ced4f06ee4c9b0ee56c4fe9e8a6045c516e7f472f.
Its exact four outer entries, source/build identity, complete-source ZIP bytes,
all 11 Xiph subtree entries, executable/DLL/notice hashes, PCM/input hashes,
failure/cleanup receipts and eight native-origin records were independently
checked. No legacy FFmpeg executable occurs in the collected file inventory.

The runtime inventory has **1,514 files, 636 directories, 624,463,838 bytes**;
its exact JSON SHA-256 is
ed6afb36f12ee855d5a6cff178bb5be6d96d4b7a4f695bac47e8abef5947788b.
All collection gates remain pending. Production execution is false, Windows 11
acceptance unavailable, installer not built and R19 incomplete in the downloaded
receipts. The source kit and sanitized metadata were downloaded; runtime binary
bytes were not uploaded or independently downloaded. The build-check's doctor
exit 2 retains missing full-scope browser prerequisites rather than claiming full
environment readiness. The scoped native pass does not override that limitation.
