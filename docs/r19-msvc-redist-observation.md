# R19 MSVC REDIST metadata census

Status: a source-bound negative hosted census is verified. The observed
layout was refused; no complete directory census or CRT approval is available.
This first observation does not select, collect or approve a CRT component.
It changes no installer, release, PR #59 or Windows 11 acceptance policy.

## Fixed scope

[probe-msvc-redist.py](../scripts/probe-msvc-redist.py) inventories only the
metadata of four fixed STL/VCRUNTIME basenames beneath an explicitly selected
Visual Studio 18 instance. It does not open their content, calculate their
hashes, read version resources, inspect signatures or PE headers, copy files,
load a DLL, run an installer, acquire inputs or access accounts. `x64` is the
requested directory role, not a verified PE architecture observation.

The machine-installed `vswhere.exe` is the single content/execute exception:
its exact bytes/SHA-256 and two selected-instance queries are checked around
the census. Its location comes from authoritative OS
`FOLDERID_ProgramFilesX86` with `KF_FLAG_DONT_VERIFY`, not environment variables, PATH, a search result or
another VS installation. All roots remain private. Raw paths, other-instance
records, stderr, resource strings and arbitrary exceptions are never emitted.

The caller supplies the already selected absolute canonical VS root and exact
numeric `18.x.y.z` version. Queries use `-all -prerelease -products *`; they do
not use `-latest`. Exactly one query record must match that private root and
version. An unknown edition, missing prerequisite instance metadata or a
duplicate match makes the observation unavailable. Public edition and release
fields are fixed enums. A known prerelease instance may be described as such;
it receives no component or redistribution approval. Instance release state
does not establish that every installed component is non-preview.

The census enumerates every numeric directory within its bounds under
`VC/Redist/MSVC`, then every known x64 CRT family there. Versions have two to
four canonical numeric components, each at most six digits. Only fixed
`Microsoft.VC140.CRT` through `Microsoft.VC145.CRT` family roles are recognized.
There is no highest-version choice, rolling `v14x` alias, architecture fallback
or system-directory lookup. Multiple versions/families are observations rather
than an implicit choice. Unknown version/family entries, an absent x64 family,
missing/nonregular fixed files, duplicate case aliases or exceeded limits make
the entire census unavailable; no partial list claims completeness.

Each family is inspected only for `msvcp140.dll`, `msvcp140_1.dll`,
`vcruntime140.dll` and `vcruntime140_1.dll`. Other family members and non-x64
architecture directories are outside this census; it is not a complete REDIST
tree or dependency closure. Every ancestor is checked root-to-leaf with raw
no-follow metadata before directory enumeration or descendant metadata. Links
and Windows reparse points are refused. Two bounded metadata snapshots must
match. Their private file-ID/time tuples are neither published nor hashed;
stable metadata is not a vendor-byte seal.

Before each Windows ancestor walk, `QueryDosDeviceW` checks only that path's
explicit drive letter. One fixed 4096-wide-character buffer permits at most
16 terminated mapping entries, including the documented final extra NUL;
there is no enumeration, buffer-growth retry or alias-chain resolution. Only
the first/current mapping has authority. The supported layout is deliberately
narrow: a complete local `\Device\HarddiskVolume` root with a canonical
decimal suffix of at most ten digits. Missing, malformed, unknown, network,
DOS-alias and native-root-with-directory-suffix mappings are unavailable.
This is a local-volume layout policy, not a claim about every valid Windows
volume naming scheme. In particular a SUBST drive into a nested VS directory
must refuse before its descendant metadata is accessed.

At most four explicitly used drive mappings are retained privately. Initial
mappings are checked again before query-tool content, query execution and
exclusive report creation; changed or missing mappings refuse. Two drive
letters for the same accepted volume are compared in the private common
volume/component namespace when enforcing forbidden roots. No mapping, drive
identity or transformed path is emitted or used as a path to open. Multiple
drive letters do not authorize a report within either forbidden tree.

Raw component checks precede path normalization. Trailing dots/spaces,
alternate-data-stream colons, reserved DOS device names (including extensions
and COM/LPT superscript digits), UNC and extended/device namespaces are
refused. After the full raw no-link walk, Windows `GetLongPathNameW` must
return the supplied spelling, allowing only case and separator differences.
An 8.3 alias is refused rather than silently expanded; no tilde heuristic is
used. The query is restricted to name metadata and does not read CRT content.
For a missing leaf, the nearest existing ancestor still passes this check
before the missing result can be returned. An unavailable long-name query is
not accepted as a canonical spelling. These checks do not claim protection
against concurrent hostile replacement of filesystem entries or drive
mappings between a check and a path-based operation.

Limits are 16 version directories, six families per version, four file records
per family and 16 MiB reported size per fixed file. At most 384 file metadata
records can be published. Scandir iteration stops at the first excess entry,
without calling DirEntry metadata methods. Discovery has a 30-second deadline;
the exact owned query process has a separate five-second cleanup deadline.
The query utility is at most 16 MiB and its stdout is limited while reading to
1 MiB, with at most 32 instance records. Windows uses `PeekNamedPipe` before
reading available chunks; there is no unbounded capture followed by a length
check. Failure/timeout terminates and reaps only that retained Popen process and
closes its pipe/process handle. No query worker thread or raw stderr capture is
used. These are source contracts, not proof against an unresponsive filesystem.

## Invocation and receipt

Run the script with Python 3.12 on a separately prepared Windows x64 build host:

```text
python -B scripts/probe-msvc-redist.py observe --selected-vs-root ABSOLUTE_PRIVATE_VS_ROOT --selected-vs-version 18.X.Y.Z --vswhere ABSOLUTE_MACHINE_VSWHERE --source-commit EXACT_HEAD_LABEL --observation-id CENSUS_ID --output ABSOLUTE_NEW_JSON
```

The output must be outside the selected installation and query-tool directory.
Its parent must already exist and pass the same raw path checks. The
report is created exclusively; existing reports and linked targets are never
overwritten. Output and forbidden roots are checked before observation, then
again before exclusive creation; even an unavailable census cannot authorize
a sink through a short-name or alternate-drive spelling of the selected
installation. The CLI preserves one initial drive snapshot and 30-second
budget across preflight, observation and exclusive creation.
Compact JSON is at most 64 KiB. A complete census returns zero;
an unavailable census returns two. A failed output channel cannot become a
passing observation, and CLI errors do not echo private arguments.

The versioned census schema exposes fixed logical member names,
numeric version literals, regular-file presence/sizes, selected-instance enum
metadata and the query utility identity. Complete status is
`observed-not-approved`; failures use `unavailable` and a finite safe reason.
No source selection, candidate file hash/version/signature or license grant is
inferred. Redistribution, source-delivery/runtime/production permissions and R19 remain
false, with license eligibility unverified, rights pending, native closure unverified, Windows 11 acceptance
unavailable, entitlement probing not performed and installer not built.

`source_commit_label` is explicitly an **unverified caller label**;
`observation_id` binds a receipt without conferring authority. This script does
not run Git or establish a clean repository/source fingerprint. An argument
alone is not provenance.

The separate [hosted wrapper](../scripts/run-msvc-redist-census.mjs) adds the
manual `source_replay=msvc-redist-census` workflow choice. That choice skips all
runtime/codec/ASR build jobs. It uses a declared Node 24 observer and separately
prepared Python 3.12.10 x64; the latter is verified as that exact interpreter
version, not as a runtime supplier-byte identity. No pip or application
dependencies are installed. The interpreter setup action can download its
declared build-host prerequisite; this job is not described as download-free.

The wrapper first runs the authored stdlib contracts. It selects exactly one
VS18 VC-tools instance using the machine query tool with `-all -prerelease`,
the explicit `[18.0,19.0)` range and required VC component. Zero, multiple or
malformed records refuse; no newest/first/older fallback exists. The census
then independently verifies that exact private root/version twice. Query-tool
bytes must match before selection, in the census and after observation.

An independent binding receipt compares provider `GITHUB_SHA` with actual clean
HEAD and reuses `captureSourceSnapshot` before/after execution. Hidden index
entries, Git source transforms, dirty source or any changed raw source/index
fingerprint refuse publication. Ordinary CRLF bytes remain part of that
physical fingerprint. The wrapper validates the census's fixed schema,
enums/counts/member bounds and every closed permission gate, then binds its
exact bytes/SHA-256 and provider run/attempt. Only `MSVC-REDIST-CENSUS.json` and
`MSVC-REDIST-CI-BINDING.json` may be uploaded; no query JSON, roots, raw logs,
test failure text or vendor DLLs. An unavailable census remains a negative
source-bound observation. Setup/selection/source failures produce no fabricated
passing census. Provider artifact/head/digest and downloaded-file review are
still required independently. The first completed observation is recorded below.

Publication serializes only the validated report as canonically sorted JSON;
the raw observer envelope and duplicate-discarded values are never published.
The fixed Python publisher reuses `canonical_path`, `info`, `directory` and
`write_report`. It preflights both fresh leaves before either write, preserves
existing files, and reads both actual files back to require exact equality
with each validated serialized payload. The census SHA-256 binds those exact
bytes. A third clean-source snapshot after publication is mandatory. Only the
fixed validated-pair sentinel opens the upload gate for the two exact
filenames, including a source-bound negative observation.

## First hosted observation

[Run 41204341666](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/41204341666)
attempt 1 at `ed153abbbf29ab9c7cb5a71c8be58158513cf519` failed in the wrapper
step on image `20261021.278.1`, after six Node contract tests passed. The
available log proves neither the Python-method count nor the failing observer
subphase. Upload was skipped and the provider artifact list is empty: there is
no receipt digest, census, metadata snapshot or source-bound negative result to
accept. Python 3.12.10 and Node 24.22.1 were the declared/observed build tools.
The fixed generic failure alone justifies no source, environment or path-policy
change. Further diagnosis must retain finite phases/codes and privacy; no CRT
file is admitted by this failure.

## Later wrapper diagnosis and explicit interpreter binding

The isolated `ca95ac1` attempt (run `41205836451`, job `124550647064`)
passed eight Node contracts, then reported only the finite `observer-child`
phase without a child diagnostic. It produced no source-bound census pair or
artifact. The job completed in 34 seconds, including a one-second contract
step; its failure was not an elapsed 150-second child timeout.

At `14babb6`, run `41210450206` / job `124564189857` ran eleven Node
contracts: ten passed and the owned Python startup fixture skipped because its
explicit interpreter was unavailable to its absolute-path/existence guard.
The subsequent observer reported `observer-child`, `observer: null` and execution
`status: null`, `signal: null`, `code: ENOENT`, `stdout_state: no-data`.
Python category and program line were unavailable. This establishes a process
startup failure, not a failed Python contract or an observed VS/CRT layout.
The job used image `20261021.278.1`, Node `24.22.1` and setup CPython
`3.12.10`; it published no artifact. No raw interpreter value, stderr or
exception message is retained as public diagnostic context.

The observer now receives the exact `python-path` output of its named
`actions/setup-python@v7` step through the step environment. This removes the
separate PowerShell application lookup and binds one executable string directly
to the pinned setup result, including paths with spaces. There is no shell,
manual quoting, PATH fallback or alternate interpreter. The existing in-child
Python `3.12.10` / 64-bit checks remain. This binding change does not by itself
prove the original lookup's returned value or the underlying cause of ENOENT;
the changed workflow still requires its own hosted observation. The output
contract is documented by [setup-python v7](https://github.com/actions/setup-python/blob/v7/docs/advanced-usage.md#outputs).

## First source-bound negative census

Run `41210956581`, job `124565656571`, attempt 1 at `c3639ce` passed all
eleven Node contracts and 37 Python contracts without skips. Direct interpreter
binding allowed the real observer to run. The census then refused
`unknown-version-entry`; the workflow correctly remains failed. The name and
type of that entry are not delivered, so no rolling-alias or other cause is
inferred, and the layout policy is not relaxed.

Downloaded artifact `13045883628` is exactly 1,520 bytes with SHA-256
`0503ca359e59ecc3d53475002642f5de0ec4dcbd2386e5a5bbffd69fc609f34c`.
Its only members are the 1,200-byte census (SHA-256
`7b7cac53c62fd830e85f2eb6ea989581fad07bdf5381a297f445df0863127d47`)
and the 1,292-byte independent binding (SHA-256
`dc869de33e79c0d0d7c4b13ff83719d28660a4f53dfaa8ee8304a08608ec18db`).
Two reviewers verified provider identity, exact entries, report-byte binding,
clean source and equal before/after fingerprint
`7532be8c9fea9f0165d286d7118bebabede05ed049ad6ce53cd04319c277fc36`.

The selected instance was VS `18.11.12315.225`, enterprise/release, on image
`20261021.278.1`. The sole query utility was 469,456 bytes with SHA-256
`c54f3b7c9164ea9a0db8641e81ecdda80c2664ef5a47c4191406f848cc07c662`.
There are zero published versions, families or files; no partial census or
vendor-byte observation is admitted. Every redistribution, runtime and
production permission stays false, with Windows 11 unavailable and no installer.

## Versioned name-only refusal projection

The next source revision uses `proxy-r19-msvc-redist-census-v2` and requires
`version_entry_refusal`. It is null on success and every other refusal. Only
`unknown-version-entry` can carry `exact-v14-token`,
`other-noncanonical-name` or `both`. These labels classify the already bounded
immediate names, before any child metadata, content, iteration or long-name
query, including numeric siblings. The exact token is compared
case-insensitively; other noncanonical spellings share one opaque bucket.
No name, hash, entry type, directory or rolling-alias meaning is exposed.

The original refusal, empty version list, zero counts, false snapshot stability
and every closed gate remain unchanged. Invalid or misplaced exception context
escapes with a fixed failure before a standalone report or bound pair can be
published. The Node validator requires the exact v2 keys and conditional enum;
it accepts no generic extension fields. Historical v1 bytes are preserved and
remain evidence only for their historical source/shape. The independent binding
schema is unchanged because it binds the exact canonical report bytes.

Source contracts pass 37 Python methods with 138 subtests and eleven Node
tests, without skips. Its first source-bound hosted observation is now verified:
run `41215460473`, job `124578963405`, attempt 1 at `2a169bd` remains failed
with `unknown-version-entry` and **`other-noncanonical-name`**. That bucket is
neither an exact-v14-token observation nor a directory/type/alias assertion.
The earlier v1 entry remains unidentified; a different image/instance is not
proof that both attempts saw the same spelling.

Artifact `13048385190` is exactly 1,552 bytes, SHA-256
`fd3c1ba8643f7eaafd17c91a234f45ab0d0d1c868d98a1bb2a2704328cdf85eb`,
with the two exact metadata entries. The 1,250-byte v2 census has SHA-256
`4f06194c247f68b68deb61e4143909da8d81900cb2c9d6f9b2710844c67d895f`.
Root and peer checked provider identity, canonical fields, exact written-byte
binding and equal clean-source fingerprint
`efdcf6254f7f9c5fbfc548b46137eaf42640b7ba93547bc57796d93e727eba2d`.
Node contracts passed 11/0 skips; the binding records 37 Python methods/0 skips,
but the hosted subtest count was not published. The image was `20261030.294.1`,
with selected VS `18.11.12328.437`. Zero versions, families or files were
admitted. Further work needs a separately reviewed bounded layout question;
no speculative additional name buckets or policy relaxation follows.
No outcome admits a CRT member, relaxes the layout policy or closes rights,
source-delivery, ordinary-user Windows 11 or R19 acceptance.

## Remaining work

The [current native-image observation](r19-native-image-review.md) separates
system-directory-sourced STL files from the CPython-supplied VCRUNTIME pair.
This metadata census does not approve either route. Actual directory/family
evidence is needed before a separately reviewed exact-member content,
signature, resource-version, import and license study. No census record is an
input to runtime collection. Current API-set/UCRT names and the old unresolved
44/48 rows are separate questions; this adds no retention or complete-import
claim. App-local servicing, owner license eligibility and ordinary-user
Windows 11 25H2 acceptance remain open.

Primary references read 2026-10-31:

- [Microsoft VS instance tools](https://learn.microsoft.com/en-us/visualstudio/install/tools-for-managing-visual-studio-instances?view=visualstudio): machine `vswhere` and Setup Configuration queries.
- [Microsoft vswhere examples](https://github.com/microsoft/vswhere/wiki/Examples): installed-instance query tooling.
- [Microsoft Known Folder IDs](https://learn.microsoft.com/en-us/windows/win32/shell/knownfolderid), [SHGetKnownFolderPath](https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/nf-shlobj_core-shgetknownfolderpath) and [Known Folder flags](https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/ne-shlobj_core-known_folder_flag): ProgramFilesX86 identity, allocated-path ownership and suppression of the API's preliminary existence walk; no create flag is used.
- [Microsoft PeekNamedPipe](https://learn.microsoft.com/en-us/windows/win32/api/namedpipeapi/nf-namedpipeapi-peeknamedpipe): available-byte observation on an anonymous pipe.
- [Microsoft file naming](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file), [file streams](https://learn.microsoft.com/en-us/windows/win32/fileio/file-streams) and [GetLongPathNameW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getlongpathnamew): raw Win32 alias/device/stream exclusions and existing-name spelling verification without assuming short names contain a tilde.
- [QueryDosDeviceW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-querydosdevicew), [MS-DOS device namespaces](https://learn.microsoft.com/en-us/windows/win32/fileio/defining-an-ms-dos-device-name), [DefineDosDeviceW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-definedosdevicew) and [SUBST](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/subst): current-first bounded mapping responses, local/global name precedence and directory-alias refusal; no mapping is created by this census.
- [VS 2026 REDIST list](https://learn.microsoft.com/en-us/visualstudio/releases/2026/redistribution): conditional licensed-user redistribution, excluded preview/debug components.
- [Microsoft app-local deployment](https://learn.microsoft.com/en-us/cpp/windows/deployment-in-visual-cpp?view=msvc-170): supported deployment with distributor servicing responsibilities, not a permission inferred from file presence.

The [authored tests](../backend/tests/test_msvc_redist_probe.py) use owned
temporary directories, synthetic query JSON and owned Python process fixtures.
They verify metadata-only reads, all-within-cap enumeration, unknown/missing
layout refusal, links/reparse boundaries, raw Windows names, bounded drive
mappings, duplicate-volume letters, metadata-only long-name checks,
missing-output ancestry, query limits/cleanup and safe output.
They do not prove any installed VS layout, file architecture or licensing.
