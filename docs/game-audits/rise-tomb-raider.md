# Rise of the Tomb Raider narrative audit

Audited on 2026-10-27 using a read-only Windows Steam installation with
`ROTTR.exe`, 73 TAFS version-4 archive families, official patches through
`update3`, 57,116 effective archive directory entries and 21 Bink movies.
Only the English base voice pack was installed. Four DLC families supplied
original recordings in thirteen languages; Blood Ties and Cold Darkness also
supplied Arabic. No launcher account, entitlement or game file was changed.

All extracted text/audio, complete indexes, private paths and research checkouts
stay in ignored `output/checks/`. The repository contains only parser code,
synthetic tests and aggregate evidence.

## Narrative coverage

| Presentation | Verified handling | Remaining limit |
| --- | --- | --- |
| Conversations, missions, ambient speech and combat/traversal dialogue | MUL packets contain both multilingual captions and original FSB audio channels. The exact archive entry binds them without fuzzy text matching. | A stream with no authored caption does not become a guessed dialogue line. The native English selection contained 2,960 such streams. |
| Radio and voiced documents | Captioned recordings use the same MUL binding. Native archive evidence includes a radio-named original stream and long narrated Blood Ties recordings. | Internal filenames do not provide a complete narrative taxonomy. Readable titles, descriptions and spoken narration are not joined by similar text. |
| Cinematics | Original streams have one to eleven channels. Every channel is preserved and mixed with the original header's left/right gains. Caption timing uses authored 30 Hz frames. | Different languages can paginate at different frames. Cuts occur only at boundaries shared by the requested available languages; unmatched pages stay in the same performance group. This may yield a longer group instead of a guessed one-line translation. |
| Blood Ties, Cold Darkness, Endurance and Baba Yaga | Installed DLC directory entries participate in the same patch ordering, original-pack isolation and caption parser. All fourteen supported study languages have successful native DLC decodes. | Installed archives are not proof of entitlement or complete gameplay coverage. Arabic evidence is limited to two DLC families. |
| Readable/UI localization | Official `locals.bin` strings are inventoried with explicit unknown voice status. | The numeric localization table does not itself prove voice links or authored silence. No native unvoiced record was established. |
| Pre-rendered movies | Twenty-one Bink containers are inventoried: seven have no audio tracks, seven have one, and seven have fourteen, for 105 tracks. | Movie track-to-language order and caption bindings are unverified. The adapter does not infer track order or claim all Bink dialogue is mapped. |

## Format and identity review

The format author's MIT-licensed TrRebootModTools was reviewed at commit
`a79c48b75f1ffaaf623dc73a625211bf98ff0504`, specifically the
[TAFS directory](https://github.com/arcusmaximus/TrRebootModTools/blob/a79c48b75f1ffaaf623dc73a625211bf98ff0504/Shared/Cdc/Rise/RiseArchive.cs),
[CDRM blocks](https://github.com/arcusmaximus/TrRebootModTools/blob/a79c48b75f1ffaaf623dc73a625211bf98ff0504/Shared/Cdc/ArchiveDecompressionStream.cs),
[MUL/CINE packets](https://github.com/arcusmaximus/TrRebootModTools/blob/a79c48b75f1ffaaf623dc73a625211bf98ff0504/Shared/Cdc/MultiplexStream.cs),
[30 Hz frame construction](https://github.com/arcusmaximus/TrRebootModTools/blob/a79c48b75f1ffaaf623dc73a625211bf98ff0504/Shared/MultiplexStreamBuilder.cs),
and [localization layout](https://github.com/arcusmaximus/TrRebootModTools/blob/a79c48b75f1ffaaf623dc73a625211bf98ff0504/Shared/Cdc/Tr2013/Tr2013LocalsBin.cs).
These references establish format fields; native reads and synthetic tests
validate this independent bounded Python implementation. No upstream executable
or filename dictionary is required at runtime.

The shared reader resolves physical archive IDs/parts before reading, applies
`.nfo` package priorities, validates platform/version and bounds, rejects altered
references, and bounds decompression output. Rise chooses voice packs by their
explicit archive suffix, not locale bitmask overlap. Fingerprints include
archives, package metadata and movie metadata; changed inputs retain the prior
prepared snapshot instead of publishing a partial replacement.

Mono original FSB4 streams use the existing pinned vgmstream r2117. Its
[MUL reader](https://github.com/vgmstream/vgmstream/blob/r2117/src/meta/mul.c)
supports up to eight channels. Larger native streams are demultiplexed to their
original mono FSB channels, decoded under one 90-second deadline, checked for
identical PCM format and duration, and interleaved in bounded chunks. The
declared original sample count supplies the end boundary. No resampling,
padding, synthesized voice or guessed voice stem is used. Temporary channel PCM
is limited to 256 MiB before the equally bounded final interleaved output.

## Native verification

With English and Simplified Chinese requested as text languages, the English
index has **15,987 records: 8,573 voiced performance groups, 7,414 unknown
localization entries, zero unavailable groups and zero confirmed unvoiced
entries**. Counts depend on the requested text languages because their common
caption boundaries determine safe grouping.

Every configured voice language decoded an original Blood Ties sample to mono
PCM. English used 48 kHz in that sample; the other thirteen used 44.1 kHz.
This establishes installed DLC codec/layout support, not absent base-pack
playback. Separate Traditional/Simplified Chinese samples have different frame
counts and retain distinct archive identities.

All three installed streams beyond vgmstream's direct MUL channel limit passed
the bounded demultiplexer: ten channels for 76.307 seconds, nine for 102.601
seconds, and eleven for 17.330 seconds. Their mono source rates, widths and
frame counts matched exactly. The normal `LocalVoiceAssetService` then produced
a timed eleven-channel cinematic clip using its authored stereo mix. A separate
six-channel production test verified the 1,000–7,500 ms subtitle group. Observed
mix coefficients were 0 or 1 across 33 channel layouts.

Focused synthetic tests cover both TIGER versions, CDRM bounds/corruption,
cross-archive patch references, every Rise language, explicit absent packs,
unvoiced versus unavailable states, localization bounds, simultaneous captions,
staggered bilingual pages, altered playback references, all-channel interleaving,
mismatched decoder output and the shared deadline. No live gameplay/OCR capture
or absent base-language pack playback was claimed by these checks.

## Source attribution

Format reference copyright (c) 2023 arcusmaximus, licensed under the
[MIT License](https://github.com/arcusmaximus/TrRebootModTools/blob/a79c48b75f1ffaaf623dc73a625211bf98ff0504/LICENSE).
The following notice accompanies the source-informed format implementation:

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
