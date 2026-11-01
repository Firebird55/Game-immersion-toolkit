# Selected RE PAK runtime reader

Updated 2026-10-30. This implements part of R19 A/B and the
[desktop delivery plan](desktop-delivery-completion-plan.md). It replaces the
normal PRAGMATA archive extraction path with toolkit-owned Python code. Indexing
and lazy original-voice extraction use the same selected-file contract on every
platform. They do not invoke REE, .NET, a compiler, npm or a shell.

## Implemented formats and boundaries

`backend/re_pak.py` reads PAK 2.0 and 4.0–4.2: raw, raw-DEFLATE and Zstandard
resources; encrypted tables; the 8-byte chunk map, including the leading
16-byte map variant; and the evidenced resource block transform. It selects
paths by the archive's lower/upper UTF-16 Murmur3 hashes. Only requested
resources are read. Compression or encryption in an unselected entry does not
cause unrelated assets to be extracted.

Table and resource transformation parameters are separately acquired data, not
embedded game constants. `backend/re_pak_metadata.py` downloads two bounded
documents from exact upstream revision `d22c15314e84eecd31480acfe692092c48043ac0`,
verifies their SHA-256 digests, and parses only numerical arrays. The documents
stay in the private tools cache. They are never compiled, imported, evaluated
or redistributed. A changed download cannot replace cached data. Preparation
needs network access the first time these metadata documents are required.

Factual format references are the pinned upstream
[archive layout](https://github.com/Ekey/REE.PAK.Tool/blob/d22c15314e84eecd31480acfe692092c48043ac0/REE.Unpacker/REE.Unpacker/FileSystem/Package/PakUnpack.cs),
[chunk layout](https://github.com/Ekey/REE.PAK.Tool/blob/d22c15314e84eecd31480acfe692092c48043ac0/REE.Unpacker/REE.Unpacker/FileSystem/Package/PakChunks.cs),
[table transform](https://github.com/Ekey/REE.PAK.Tool/blob/d22c15314e84eecd31480acfe692092c48043ac0/REE.Unpacker/REE.Unpacker/FileSystem/Encryption/PakCipher.cs)
and [resource transform](https://github.com/Ekey/REE.PAK.Tool/blob/d22c15314e84eecd31480acfe692092c48043ac0/REE.Unpacker/REE.Unpacker/FileSystem/Encryption/ResourceCipher.cs).
The replacement implementation is independently authored; it does not ship
the upstream source or modified helper whose redistribution review remains open.

Limits are explicit: two million table entries, four million chunk entries,
100,000 selected paths, 256 MiB per selected compressed/decompressed resource,
and 2 GiB total selected output per archive call. Invalid extents, unsupported
formats, ambiguous selected hashes, output traversal and decompression overflow
fail before replacing previously extracted contents. Patch order remains the
existing base-then-patch order. Zstandard 0.25.0 and its native dependency are
part of the packaged runtime dependency inventory.

## Evidence and remaining acceptance

The authored regression suite exercises raw/DEFLATE/Zstandard data, encrypted
tables with independently chosen numerical parameters, chunked raw/compressed
blocks, resource transformations, version 2 archives, selected-only extraction,
malformed extents/counts, decompression overflow/trailing streams, cache integrity
and preservation of earlier patch output on failure. No fixture contains game
data or publisher transformation constants.

A private installed-file comparison read all six installed archive layers and
compared eight selected files against previously extracted bytes: two MSG
tables, two localized SBNK headers, two SPCK voice packages and two TMLFSM2
timelines. All eight matched, including the chunked SPCK path and a patched MSG
entry. This is native archive-format evidence, not a claim of playback,
uninstalled-language verification, live capture or full frozen acceptance.

Official language choices, text/audio bindings and missing-pack/unknown/unvoiced
classification are unchanged. See the [language report](pragmata-languages.md)
and [coverage audit](game-audits/pragmata.md). No voice is inferred from a missing
recording or from matching text.

Remaining work: run these same format tests in the actual frozen candidate on
each target platform; verify selected original-voice decoding with the shared
codec chain; include the dependency notices/native closure; and complete R19
C–F. The old selective x86 helper remains a historical private comparison tool,
not the production archive reader. This replacement does not complete unrelated
Endfield, NTE or ZZZ helper work.
