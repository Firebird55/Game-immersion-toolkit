# Separate legacy-lock READONLY mechanism experiment

This is a build-host source experiment, **native pending**. No Windows attribute
or owner-loss result is claimed from local authored tests. It is not registered
as a frozen child or production API and does not change existing C1/C3/C4/C5/C6,
keeper, migration, runtime or installer behavior. PR #59 remains untouched.

The question is narrow: can READONLY on the exact existing legacy operation
file preserve an unchanged launcher's refusal after the last genuine lease
owner exits? [File.Open](https://learn.microsoft.com/en-us/dotnet/api/system.io.file.open?view=netframework-4.8.1)
documents a refusal when ReadWrite is requested for a read-only file. This
would complement live sharing exclusion; it would not keep a dead process's
handle alive or prove any candidate writer stopped.

The [R18 contract](r18-storage-host-contract.md), steps 3 and 6, still requires
continuous handle ownership and both exclusions through writer shutdown.
Step 7 still requires verified process ownership for recovery. This experiment
cannot quietly replace those requirements with a sticky attribute. Its scope
contains **zero candidate/data writers**, no pointer change, no user data and no
activation. A passing mechanism result does not close the keeper-loss gate.

## Fixed mechanism and containment

[The standalone module](../backend/runtime_lock_attribute_probe.py) accepts no
fixture, source, executable or output path from the operator. On 64-bit Windows
it checks the existing temporary directory through root-first non-link metadata
guards and requires a fixed local NTFS volume before creating anything. It then
creates one marked temporary root and one original lock file with owned text.
The private child grant must name that exact temporary namespace and marker.
Initially READONLY, linked, multiply linked, deleting, unknown-attribute,
wrong-sized or changed-content files cannot become accepted observations.

Actual contenders execute only the unchanged `Enter-CompanionOperation` function
from [the current source](../scripts/companion-runtime.ps1). The whole source
is checked against its reviewed exact LF or Windows CRLF hash. A bounded
read-only source stream is hashed before its exact bytes are parsed as an AST;
there must be exactly one named definition. No script body is rewritten. The
operation still uses OpenOrCreate, ReadWrite and FileShare.None.

The existing [creation helper](../backend/windows_preparation_process.py) creates
the actual lease owner suspended directly into its retained Job. The retained
creation object resumes once and is the only authority used for termination and
signaling. No PID, copied handle or file journal is adopted. Each private local
named pipe has one first-instance server, rejects remote clients and has a
bounded 4 KiB frame. Lease grants and child responses use fixed JSON; the v5
legacy grant uses canonical C7G5 framing described below. Its client PID is only compared with the PID
queried from the genuine creation handle. It is not a process-ownership grant.
The lease child's pipe uses explicit nonblocking mode; there is no inherited
stdio, reader thread, raw log or arbitrary child command.

The fixed observation sequence is:

1. The actual legacy operation opens the writable file and closes successfully.
2. One genuine child acquires its original ReadWrite exclusive handle. A separate
   actual legacy contender reports the existing sharing refusal.
3. The child sets READONLY and reads back through that handle. It clears while
   retaining the same handle, proves sharing still refuses the contender, then
   re-arms and reads back before owner loss.
4. The parent stops only that retained creation object, waits for its signal,
   drains/closes its owned Job and closes the pipe. No duplicate lease is kept.
5. A temporary read-data/attribute observation handle verifies the same file and
   retained READONLY, then closes. With no file lease held, the actual legacy
   operation must take its specific UnauthorizedAccess/known access-denial path.
   A generic permission error is not a passing result. The initial and final
   writable controls and unchanged file identity constrain this contrast.
6. Only because this fixture admitted zero writers, a separate test restoration
   handle requests GENERIC_READ plus FILE_WRITE_ATTRIBUTES, no WRITE_DATA, with
   share=0. It verifies the armed file, clears while still holding data-read
   exclusion and proves sharing still refuses the contender. After explicit
   close, the actual old operation opens again. Final by-handle preservation is
   checked through a fresh observation handle.

An attribute-only handle is deliberately insufficient:
[CreateFile](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)
exempts attribute-only access from ordinary share checks. The native behavior
of the proposed read-data/write-attributes restoration combination is itself
pending. Failure is reported, without a clear-then-acquire gap or alternate
handle/permission strategy. This is not an automatic recovery route for a dead
keeper with unknown surviving writers.

## Private preservation and public result

Typed 64-bit Win32 APIs query FileIdInfo, FileStandardInfo and
[FileBasicInfo](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_basic_info)
on retained handles. The same volume/file ID, fixed content, link count and
unrelated attributes must remain valid. NORMAL is treated as the no-other-flags
placeholder; it is not combined with READONLY. The setter uses no undocumented
timestamp suppression. All four times remain private. The receipt includes
only four equality booleans for each transition. Creation and stream-write
time changes refuse preservation; access-time changes from reads and metadata
ChangeTime changes can be observed as false. They are not hidden or presented
as exact timestamp preservation. No private path, file ID, raw time, private
content hash, exception, environment, command or stack is serialized.

The public schema is `proxy-r19-legacy-lock-attribute-mechanism-v5`, scope
`authored-local-ntfs-no-writers-mechanism`. It revalidates exact keys, fixed
ordered observations, enum values, booleans and the known public legacy-source
hash. Its only successful status is `mechanism-observed`. The final gates stay
false: production, keeper-loss acceptance, rights and R19 completion; ordinary
Windows 11 acceptance stays unavailable.

Version 2 introduced the closed `baseline_checkpoint` object with three finite
strings: `parent_step`, `script_step` and `child_state`. The parent marks pipe
creation, owned process creation/resume, client binding, grant send, progress
receive, result receive and cleanup immediately before the action. On refusal,
cleanup cannot overwrite the first failed parent action. Child state is only
not-created, signaled, not-signaled or unavailable, queried through the genuine
retained creation handle before close. No closed handle, PID lookup or exit code
supplies it. Query failure is unavailable context; it cannot grant or revoke
the existing process cleanup or mechanism acceptance requirements.

Historical version 3 retained those exact three keys. Its PowerShell child sent
fixed ordered progress: connected, grantread, grantparsed, grantvalidated,
sourceopened, hashbound, definitionbound and operationentered. The existing
single ReadLine call returns before grantread; its result enters the same
string pipeline to ConvertFrom-Json, which returns before grantparsed.
Neither acknowledgement proves a non-null grant, its shape, or a successful
operation. Only the unchanged three-name/string-type checks permit
grantvalidated. Null, malformed or incomplete progress still refuses; no
line, property, parser output or exception is published.
Only actual hash equality permits hashbound; only the exact AST checks and
definition permit definitionbound. The terminal `state` result is unchanged.
Only a complete typed terminal record supplies operationresult. A stage before
the function call does not establish that the legacy operation opened.

All received bytes across an Attempt share one cumulative 4KiB cap. Grant,
progress, terminal and pipe completion share one existing10-second exchange
deadline, with no per-record extension. Unknown, skipped, duplicate, malformed
or trailing records refuse the attempt; only the last complete admitted stage
is retained. Terminal completion requires the peer to close without trailing
bytes within that deadline. There is no new runtime, process, raw output,
environment variable, source-function change, pipe-mode change or fallback.

### Version 5: canonical grant, native pending

Version 5 changes the authored parent-to-legacy grant harness. It does not
change the pinned legacy `Enter-CompanionOperation` bytes, source/hash/AST
checks, ReadWrite/FileShare.None operation, NTFS fixture, attribute/file identity,
private times, genuine owner-loss sequence or cleanup requirements. It is not
evidence of a ConvertFrom-Json cause or a weaker R18 criterion. Historical
v1–v4 receipts and the exact `11bf` source/tests keep their identities; none can
be admitted or relabeled as v5.

Only the legacy grant changes from JSON to one canonical ASCII frame:

```text
C7G5|base64(UTF8(root))|base64(UTF8(source))|base64(UTF8(sha256))\n
```

The parent accepts exactly those three nonempty string fields in fixed order,
not caller-supplied wire bytes. Strict UTF-8, a complete-frame 4096-byte cap,
per-field 3072-byte cap, no leading BOM, NUL or decoded CR/LF, and exactly
64 lowercase hexadecimal digest characters are required. The child consumes
at most 4096 characters including LF with a fixed TextReader buffer. Missing
LF, EOF, CR, NUL or overflow refuses before source-file access.

The child uses only its authored functions and .NET built-ins. Base64 decoding
must reproduce the original token through ordinal re-encoding; decoding alone
is insufficient because FromBase64String tolerates whitespace. Strict UTF-8
and an explicit leading-BOM check preserve exact Unicode strings without
normalization or fallback. The fixed PSCustomObject then enters the same
three-name/string-type checks, source read/hash, exact AST selection and actual
legacy operation. No grant JSON parser, module import, cmdlet, authored class,
new environment trial or fallback participates in that decoder. The later
explicit OS-module prerequisite is separate and described below. The Python lease child's
root/nonce JSON and all fixed child-response JSON remain unchanged.

This framing is not authentication or encryption. The same private pipe,
genuine creation handle/Job and client binding remain the authority. There is
one existing ten-second grant/progress/result/response-EOF deadline and the same
byte IO, nonblocking flags and cleanup. The sender creates exactly one frame.
The duplex byte pipe does **not** establish that no future unsolicited parent
bytes can follow its LF. The child never treats later bytes as another grant;
there is no new tail/EOF claim in the parent-to-child direction. Response EOF
and trailing-response rejection remain hard and unchanged.

`grant_conversion_failure` remains in the v5 envelope only as a strictly null
field. Non-null v4 exception context is rejected unconditionally. All public
observation, preservation, source and cleanup requirements stay hard; there are
no new success fields or diagnostic substitutes for actual mechanism results.

The active Windows preflight now runs the exact .NET reader/decoder under both
the inherited snapshot and the same fifteen-name Attempt map, in two fresh
protected legacy PowerShell children. It checks authored ASCII/Unicode round
trips, every negative vector, the exact 4096-byte boundary, missing terminator
and over-limit refusal. Its StringReader tail case explicitly leaves future
bytes unread, preserving the transport limitation above. Both environments must
pass, with no stderr and confirmed direct child/readers cleanup, before the
mechanism can run. The existing 8192-byte-per-stream capture and wait/cleanup
limits remain. These controls do not prove named-pipe, Job, attribute or owner
loss acceptance; that still requires the full actual v5 mechanism run.

| Earlier coverage | v5 disposition |
| --- | --- |
| Win32 ABI, file/attribute/identity/time, actual operation/owner-loss ordering, source guards, checkpoint/deadline/EOF and cleanup refusals | Keep; no acceptance relaxation. |
| Generic parent capture/thread-start/read/close/timeout/retention cases | Keep with the new closed codec result. |
| v4 JSON conversion context/catalog and diagnostic writer/rethrow engine cases | Retire to exact historical Git `11bf` and the private review snapshot; the v5 decoder has no such catch/projector. Replace with canonical codec/type/limit/null-only-envelope tests and owned primary/cleanup-error preservation. |
| v4 JSON literal pair, progress markers, system-search and StringWriter controls | Replace in active preflight with the exact v5 decoder's strict two-environment positive/negative test. Preserve every prior negative as historical evidence, without changing its expectations or adding a skip. |

The keep/replace decision changes an obsolete harness dependency, not a failed
legacy-operation test. A codec failure still fails preflight; a mechanism
failure still fails the experiment. There is no substitution of another
control's success. The old unresolved cause stays unresolved.

The API contracts are documented for
[FromBase64String](https://learn.microsoft.com/en-us/dotnet/api/system.convert.frombase64string?view=netframework-4.8.1),
[ToBase64String](https://learn.microsoft.com/en-us/dotnet/api/system.convert.tobase64string?view=netframework-4.8.1),
[strict UTF8Encoding](https://learn.microsoft.com/en-us/dotnet/api/system.text.utf8encoding.-ctor?view=netframework-4.8.1)
and [ordinal string equality](https://learn.microsoft.com/en-us/dotnet/api/system.string.equals?view=netframework-4.8.1).
Their availability does not establish the next host's outcome. Actual v5
execution remains pending; physical/global/copy/warm, keeper-loss, ordinary-user
Windows 11, rights and R19 gates stay open. No installer is built.

### Historical version 4: failure-only conversion context

Version 4 retains those checkpoints and adds only the nullable top-level
`grant_conversion_failure` field. Its default is null. A catch surrounds the
same existing string pipeline to ConvertFrom-Json. It may send one closed
failure frame, then rethrows the original error even when its diagnostic writer
fails. The projector definition is before connected; there is no new function
definition between grantread and the conversion call. The existing ReadLine,
parser, legacy operation body, environment, native calls and cleanup stay intact.

```json
{"kind":"grant-conversion-failure","line":"nonempty","exceptions":["cmdlet-invocation","argument"],"chain_end":"complete","category":"InvalidArgument"}
```

The parent recognizes this alternate frame only while expecting grantparsed,
after connected and grantread. It validates exact keys and enums, then requires
the existing EOF/no-trailing boundary under the same deadline before retaining
the candidate. Even then it refuses the attempt. Duplicate, unknown, malformed,
partial, trailing, over-cap or late input leaves the public field null. Neither
the frame nor cleanup advances the last complete grantread checkpoint. Later
contenders have no baseline result holder and cannot populate this field.

A non-null public value contains exactly line, exceptions, chain_end and category.
The line is only null/empty/nonempty, never its contents, length or hash. The
ordered exception families are limited to command-not-found, parameter-binding,
cmdlet-invocation, type-initialization, argument-null, argument and unknown.
At most eight existing exception nodes and eight InnerException references are
read, with no ninth node, GetBaseException or type-name output. Chain end is
complete, truncated or unknown; empty chains require unknown and truncated
chains require eight entries. The
[ErrorCategory mapping](https://learn.microsoft.com/en-us/dotnet/api/system.management.automation.errorcategory?view=powershellsdk-7.4.0)
is the fixed documented 0–31 list plus unknown. Future or unavailable categories
remain unknown; there is no automatic catalog growth.

Non-null context requires failed status at legacy-baseline, parent
receive-script-progress, script grantread, empty observations/timestamp equalities,
a known source hash, protocol-refused or owned-cleanup-unconfirmed, and
unconfirmed-fixture-retained. Every positive mechanism receipt requires null.
The independent publisher must recheck those same relations. Null does not prove
that conversion never ran or threw. Families/categories are caught context,
without a private target, inferred cause or authorization to repair the runtime.

Only fixed ASCII labels are written: the largest authored frame is 302 bytes
including LF, and connected + grantread + failure total at most 386 received
bytes. The unchanged normal sequence is at most 394 bytes. The actual cumulative
receive cap remains 4,096 bytes; the grant retains its existing separate send
bound. Grant, progress, failure and EOF share the original 10-second exchange.
No message, parameter name, target, invocation, raw code, stack or private path
is published. Owner/handle cleanup and sticky uncertainty remain mandatory.

Every owned cleanup stage is attempted independently. A failed handle close is
sticky and its numeric value is never retried as a possibly reused handle.
Unknown identity, source, protocol, attribute or owned cleanup fails the attempt.
The fixture is retained on success and failure: there is no unlink, chmod,
recursive deletion or path-based reset. Success says only
`owned-handles-closed-fixture-retained`; it is not full R19 cleanup acceptance.
Windows closes files on process termination, but no process-crash experiment or
[buffer flush](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-flushfilebuffers)
establishes power-loss durability.

## Execution and evidence

The historical version1 attempt at `a1c5e92`,
[run41225668722](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/41225668722),
passed57 authored Windows contracts using Python3.12.10 on hosted image
20261030.294.1. Its source-bound metadata then reported failed /
legacy-baseline / protocol-refused, no observations, no timestamp booleans and
unconfirmed-fixture-retained. Root and peer independently verified the provider
ZIP digest, exact single JSON entry, candidate source, equal before/after
fingerprints and false gates. No actual legacy Open, READONLY set or owner loss
was delivered. The phase conflated startup, pipe binding and the script's source
and operation steps; it established no native cause. It contains no version2
checkpoint. The new wire and projection need their own reviewed CI publisher
and actual exact-source Windows attempt; the old negative is not relabeled.

The historical version 2 attempt at `e8416e9`,
[run41229013616](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/41229013616),
passed 89 authored Windows contracts without skips on image `20261021.278.1`.
Its independently verified receipt stopped at legacy-baseline/protocol-refused:
parent receive-script-progress, script connected and child not-signaled before
close. Observations and timestamp equalities were empty; cleanup remained
unconfirmed-fixture-retained. It does not identify whether ReadLine, conversion
or shape validation returned, and establishes no successful legacy Open,
READONLY transition, owner loss or native cause.

Version 3 distinguishes only those existing grant boundaries, with no additional
read, conversion, parser/runtime import or acceptance authority. Its wire needs
the separately reviewed publisher and a new exact-source Windows receipt;
native execution remains pending. The v1/v2 negatives retain their original
schemas and meaning. No environment, timeout, source-function or pipe repair is
inferred from them.

The historical version 3 attempt at `f43cec7`,
[run41235281328](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/41235281328),
passed 100 Windows contracts without skips on image `20261021.278.1`. Its
independently verified failure receipt delivered grantread with parent
receive-script-progress and pre-close child not-signaled, then no complete
grantparsed. ReadLine returned before that acknowledgement; its result and the
underlying conversion boundary remain unknown. It still failed at
legacy-baseline/protocol-refused with empty observations/timestamp equalities
and unconfirmed cleanup. No legacy open, attribute or owner-loss result follows.
Version 4 and its separate publisher require a fresh exact-source Windows
attempt and independent receipt review. The v3 negative is not reinterpreted.

On the selected Windows build host, run the selected 64-bit source
interpreter directly:

```sh
python -I -B backend/runtime_lock_attribute_probe.py
```

It prints one finite JSON result and exits 0 only for the complete mechanism
observation; refusal exits 2. There is no output-path or cleanup-path option.
Its internal `--owned-lease` mode accepts only the fresh pipe name, then receives
the bounded private fixture grant after creation-identity binding. Do not run it
against a real installation. No native pass is currently recorded.

The existing **R19 integrated extracted runtime experiment** workflow exposes
the separate manual `source_replay=legacy-lock-attribute` selection. It runs
only this Windows source job, using Python `3.12.10` and the exactly locked
pytest dependency subset. The independent wrapper checks the finite receipt
schema, actual exit status, clean checkout and matching before/after raw source
fingerprints at the event commit. Its fixed output sink checks ancestors before
creating directories, rejects links and existing leaves, reads back the actual
written bytes through a bounded descriptor and checks source/cleanliness again
before the upload sentinel. It uploads only
`r19-legacy-lock-attribute.json`, including source binding; no fixture or raw
stdout/stderr is retained. A validated failed receipt remains failure evidence.
Its outer deadline records a failed, unverified attempt rather than cleanup
containment. Native acceptance still requires the actual job and independently
downloaded provider/artifact/receipt review.

The separate `eaa42b2` Windows [run 41238897590](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/41238897590)
passed 138 authored tests and failed both enginecatch cases before the actual
mechanism. Its generic failure did not distinguish nonzero exit from stderr.
The test-only `37b4dd5` [run 41240037303](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/41240037303)
passed 147 tests and failed the same two cases with `exit=record-identity` and
`stderr_present=false`. That is the existing exit32 assertion: outer and inner
ErrorRecord wrappers were not ReferenceEquals. The exception-identity, later
acknowledgement and frame checks were not reached. Neither run invoked the
mechanism/publisher or produced an artifact. This does not identify the ordinary
bare-rethrow baseline, historical grant-conversion cause or any cleanup result.
The [checkpoint ledger](r19-frozen-checkpoint-20261031.json) preserves both
receipt-free negatives separately from the successful main runtime checkpoint.

The subsequent `973` bare-rethrow baseline,
[run 41242358974](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/41242358974),
job `124658708683`, attempt 1 on image `20261021.278.1`, passed 161 portable
contracts and failed the two authored Windows engine cases. Each retained
`exit=record-identity` and `stderr_present=false`. In both the ordinary
bare-rethrow baseline and the instrumented variant, the measured record_equal
was false, while exception_equal, category_equal, identifier_equal and
finally_observed were all true. This was observed in each successful/throwing
diagnostic-writer case, with fresh ErrorRecords and exceptions per variant.

That controlled comparison identifies an overstrong internal test assumption:
ErrorRecord wrapper reference equality is not required when even the ordinary
bare-rethrow baseline changes it while preserving the underlying context.
The test now keeps wrapper equality only as a diagnostic boolean. It requires
all four preservation booleans to be true independently inside both variants,
using the same strict closed-frame parser. Missing, malformed or unavailable
frames and any false preservation boolean still fail. The original instrumented
exception-reference and presence/finally guards remain hard requirements.
No exception objects are compared across the two fresh variants.

This corrects only that authored test contract, with no producer, mechanism
schema, command, parser, environment, capture or cleanup change. It supplies no
actual C7 operation, grant-conversion cause, lock-attribute/recovery result or
rights/Windows 11 acceptance. A new exact-source Windows attempt remains
required. The earlier eaa/37 failures and their original evidence are preserved.

At `d329027b850ebd7fc01ad6db6d366ec3a3ee9bf9`,
[run 41245783408](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/41245783408),
attempt 1/job `124668821163` on image `20261021.278.1`, all 175 authored
contracts passed, including both Windows engine cases. The actual C7 step was
then reached and failed at legacy-baseline/protocol-refused. Its independently
verified v4 receipt still delivered only grantread, parent receive-script-progress,
pre-close child not-signaled, null grant_conversion_failure, empty observations
and timestamp equalities, and unconfirmed-fixture-retained. Null can also mean
that a diagnostic candidate was invalid or its EOF was unconfirmed; it does not
prove no caught error or no subsequent physical activity. The underlying C7
cause remains unknown. Earlier eaa/37/973 and f43 negatives keep their meaning.

### Separate paired real-cmdlet control and bounded parent observation

#### Historical v4 literal phase and writer comparison

The subsequent `11bf` v4 run delivered before-conversion for the original
authored-class and StringWriter Attempt controls and all three system-search
controls, with wait-deadline/no-stderr and confirmed direct cleanup. Both
inherited writer variants parsed without stderr. This establishes delivered
test progress, not a cmdlet/module cause or actual C7 mechanism acceptance.
The v5 codec does not reinterpret this negative.

At `b598`, run `41292608812` / job `124806810969` on image
`20261030.294.1` passed 223 contracts and failed the paired control in
44.43 seconds, with no skips. Inherited parsed with null context and no stderr.
The fifteen-name Attempt and all three system-search controls reported
`wait-deadline`, unavailable/null-context/no-stderr. All five direct children
and readers finished. No mechanism or artifact followed. This does not prove
a path/module cause, or that a filtered child reached the conversion call.

That v4 test-only source added three exact ASCII stdout markers: script-entry,
before-conversion and after-conversion. Direct managed Console writes and
flushes emit them; no logging cmdlet, serializer or authored marker class is
added. Script-entry is the first executable statement. Before-conversion follows
writer construction, literal initialization and the unchanged projector function
definition. After-conversion is emitted only after the unchanged conversion
fragment returns, before its existing shape check. Marker delivery does not
establish a cause, and absence does not prove that a statement never executed.

The existing five fresh controls keep their order. Two further fresh literal
controls use .NET StringWriter, first with the same inherited snapshot and then
with the exact Attempt map. There are at most seven child invocations, without
retry or a StringWriter search-path matrix. The original inherited and Attempt
controls still must both return parsed/null-context/no-stderr; no diagnostic
control can replace that gate. With the protected host available, all seven are
collected before the joint decision,
and every diagnostic child also requires confirmed direct-child/reader cleanup.

Both writer variants use the same protected executable, fixed input, preferences,
producer conversion/projector fragments and shape/exit checks. StringWriter
replaces the authored class only in its two additional controls. Its existing
buffer is emitted with managed Console.Write after the terminal line, avoiding
an extra newline or parser, and its owned instance is disposed in finally.
Microsoft documents [StringWriter](https://learn.microsoft.com/en-us/dotnet/api/system.io.stringwriter?view=netframework-4.8.1)
as an in-memory TextWriter backed by StringBuilder. This is an authored writer
comparison, not a substitute for the actual C7 named-pipe StreamWriter.

The separate closed progress projection has exactly `last_delivered` and
`protocol`. Last-delivered is not-observed, script-entry, before-conversion or
after-conversion; protocol is not-observed, ordered-prefix or malformed. Only
complete LF/CRLF marker lines in the exact order are admitted, at most three.
A partial, duplicate, unknown or reordered record cannot be skipped to admit
a later marker. Partial stdout preserves only the last delivered complete marker
and always keeps the parsing result unavailable. A parsed terminal requires all
three markers; an ordinary conversion-refused terminal can follow the first two.
The existing closed terminal/failure decoder still validates the remaining
records, exit code and context. Neither progress nor a timeout becomes success.

Each child's original 8192-byte-per-stream cap includes these markers. Its
ten-second wait, existing cleanup wait/reader joins and private uncertainty
retention stay unchanged. No extra stdout read, timeout extension, raw output,
path, environment value, error/type/identifier text or hash is published. The
producer, actual legacy script, schema v4 and environment policy are unchanged.

If the class and .NET variants differ at the delivered markers, that narrows a
test-construction or execution boundary under these supplied maps. It does not
identify the actual C7 cause. Missing script-entry still leaves startup, parsing,
type resolution and host/capture behavior unresolved. Those v4 measurements remain negative. Keeper-loss, physical/global, rights,
Windows 11 and R19 gates remain open.

#### Historical Windows-runtime environment and system-search controls

At `0f93531`, separate run `41254860334` on image `20261021.278.1` passed
216 authored contracts and failed the paired control (15.32 seconds, no skips).
Inherited reported `parsed`, null context, no stderr and refusal `none`;
the fifteen-name Attempt reported `unavailable`, null context, no stderr and
`wait-deadline`. Both direct test children/readers finished. Mechanism/upload
were skipped, with no artifact. The earlier four-name negatives remain intact;
this result does not identify a missing variable or an actual-mechanism cause.

That test-only diagnostic added three fresh literal-input children after
collecting the original pair: filtered environment plus a fixed system PATH,
plus a fixed PowerShell module path, and plus both. Paths are derived only from
the protected legacy PowerShell image obtained through GetSystemDirectoryW:
PATH contains System32 and that image's directory; PSModulePath is its Modules
directory. No inherited program/module path or new parent value is admitted.
These are three explicit prospective controls, not changes to Attempt policy.

The [documented module search](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_psmodulepath)
motivates measuring these inputs; it is not evidence that either caused the
refusal. PowerShell can further construct its effective module path, so the
supplied value alone does not prove exclusive loaded-module origin. The literal
script, conversion/projector, capture/wait/cleanup limits and original two-way
parsed/null-context/no-stderr requirement remain unchanged. All five children
are collected before that joint decision. Additional children must have
confirmed direct-child/reader cleanup before the test can pass. Only closed
observation/parent labels are included on refusal; environment values, program
paths, raw stderr and exception text are never added to the diagnostic.
Their later `b598` measurements are negative as recorded above. They grant no
keeper-loss, physical/global, rights, Windows 11 or R19 acceptance.

At `a2e1fb6`, run `41250877798` passed 214 contracts and failed the paired case
on image 20261021.278.1 (14.54 seconds, zero skips). Its closed parent labels
locate the four-name control refusal at the ten-second wait deadline; the owned
test child and reader threads then finished. The inherited control parsed and
its stderr began with the literal CLIXML marker. The marker does not classify
its records. Mechanism/upload were skipped with no artifact. This remains a
control observation, not proof of the earlier named-pipe failure's cause or
Job/descendant cleanup.

The later candidate replaces the artificial four-name filter with one explicit
allowlist of fifteen parent-provided Windows runtime folder/profile variables.
It preserves their original values without publishing them. PATH, inherited
PSModulePath/analysis-cache overrides, Python/Node/.NET/SDK/developer variables
remain excluded. The protected PowerShell executable, legacy script, actual
grant conversion, wire/schema, process limits and cleanup remain unchanged.
The paired test uses the exact same environment builder as the actual Attempt.

This is a prospective compatibility policy, not a finding that any particular
missing variable caused the timeout. Microsoft's
[module-path construction](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_psmodulepath)
documents default system/current-user locations and the separate problem of
inheriting PowerShell 7 module paths through an intermediate Python process.
Those documented inputs motivate preserving ordinary Windows runtime values
while excluding explicit caller module-path overrides; they do not prove the
candidate works or grant ordinary-user Windows acceptance.

Only the authored literal-control script also sets
`$ProgressPreference='SilentlyContinue'`, whose
[documented scope](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_preference_variables?view=powershell-5.1#progresspreference)
is progress presentation. ErrorAction remains Stop; errors/warnings/raw stderr
are not filtered, decoded or discarded. The existing parsed/no-context/no-stderr
joint success predicate and all capture/cleanup limits remain hard requirements.
The actual C7 legacy script does not receive that progress preference. Both
changes are explicit control differences; native results are pending. Historical
four-name refusals retain their exact source/environment interpretation, and no
cause, mechanism, keeper-loss, rights or R19 gate is closed by this candidate.

#### Historical paired controls and parent observations

At exact `ac5b7670da9fd613892f6d054e1b96ff51371d7c`, separate
[run 41247805821](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/41247805821)
on image 20261030.294.1 passed 203 contracts and failed only the new paired case
(zero skips, 13.69 seconds). Both prior Windows preservation cases passed.
The inherited control delivered parsed/null-context/stderr-present; the exact
four-name map delivered unavailable/null-context/no-stderr. The two identical
pytest diagnostic lines repeat one pair, not two independent observations.
Mechanism and upload were skipped; no artifact or mechanism receipt exists.
Root and peer independently checked the provider, fixed projection and exact
Git inputs. This image differs from d329's 20261021.278.1.

Parsed with stderr bytes does not classify those bytes as errors. Unavailable
does not distinguish timeout, startup, capture, protocol or cleanup failure.
Neither result identifies a variable/module/environment repair or the C7 cause.
The later test-only parent observation therefore adds fixed refusal-boundary,
stderr-prefix and child/reader-finish labels. Unknown fields/types/values are
reprojected to unavailable; no raw output, code, path, environment value or
exception text is published. The prefix label only compares the literal
`#< CLIXML` bytes: it does not parse XML, classify records as progress/errors,
or change the existing stderr refusal. Child/reader completion is limited to
this authored Popen harness, with no descendant or Job/pipe cleanup claim.
Native results for these added parent labels are pending.

The two preservation cases deliberately shadow ConvertFrom-Json with a synthetic
throwing function. They do not prove the real utility cmdlet works under the
actual Attempt environment. One additional Windows-only authored case therefore
measures two fresh children: ordinary inherited environment contents, then the
exact systemroot/windir/temp/tmp name filter used by Attempt. Both maps come
from one captured parent snapshot. Values are neither modified nor published;
no missing variable is restored. Both results are collected before a joint
assertion, including when the first child refuses or is unavailable.

Both children use the same protected `Windows().powershell()` selection, actual
legacy argument mode, exact producer conversion projector/catch, ten-second
wait and 8,192-byte-per-stream capture. Each invokes the real ConvertFrom-Json
once on the literal `{"owned":true}`, then checks exactly one boolean-true owned
property. There is no shadow, warm-up, Import-Module, Get-Command, ConvertTo-Json,
alternative parser or second conversion. A fixed managed writer and literal
Console output carry only the closed control observation. No real grant,
source path, C7 fixture, lease, account or data writer is supplied.

The fixed states are parsed, shape-refused, conversion-refused or unavailable,
alongside nullable existing bounded conversion-family/category context and a
stderr_present boolean. Exact frame keys/types/count, duplicate rejection and
exit/state correspondence are rechecked before either result can be printed.
Unknown text, raw code, module/type/identifier names, environment values, paths,
stderr, lengths and hashes are excluded. A pass requires parsed, no context and
no observed stderr in both sets. Missing/malformed output, timeout, readbudget,
start or cleanup uncertainty fails, without hiding the other collected result.

Cleanup from successful Popen creation covers both reader starts, retained-child
kill/wait and owned streams. Unconfirmed start/close/wait leaves private
process/pipe/thread records retained; uncertain closes are not raced or retried.
These are authored Popen/stdout observations: the selected executable and input
mode match C7, but the current directory, transport and ownership harness do not
recreate its named-pipe/retained-creation/Job path. Confirmed test-child exit
does not establish descendant closure, full C7 cleanup or recovery.

A difference between these controlled environment-set results cannot identify
which variable matters, explain the historical C7 failure or authorize an
environment fix. Shared-host state and the fixed run order also limit that
comparison. Both controls passing proves only this literal/control operation,
not actual ReadLine content, true grant conversion, pipe EOF or mechanism success.
The producer, public mechanism schema/publisher, environment policy and deadlines
remain unchanged. The initial native refusal above remains intact; rights,
ordinary-user Windows 11, keeper-loss and R19 gates remain open.

## Raw controls following the actual v5 baseline refusal

Exact `d35cd89fb31afa35cf4675709591860f99969e19`
[run 41308862562](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/41308862562),
job 124854867354, passed all 216 Windows contracts in 4.31 seconds, including
the two actual inherited/Attempt decoder children. The subsequent mechanism
failed at `legacy-baseline`, with no accepted observations. Its last complete
checkpoint was parent `receive-result`, script `operationentered`, child
`not-signaled`; failure was `protocol-refused`, cleanup was
`unconfirmed-fixture-retained`, conversion context was null and every
acceptance/production gate remained closed. The source before/after digest was
`5f899e1da29ed710eba666bc7bb4c7e5884d9b3af42f7deb57e2e3f8f322a335`.
The public legacy-source digest was the reviewed Windows CRLF pin
`f9469ccb51c99b814a615e66eb9b337e8b1ba8598a0fd794dbe420c8be4c8e9e`.
That negative receipt is not relabeled by the following source candidate.

`operationentered` is sent immediately **before** calling the unchanged
`Enter-CompanionOperation`. It does not prove function entry, File.Open,
attribute arming or absence of a later action. The source body first uses
Join-Path, `New-Item ... | Out-Null`, and another Join-Path before its managed
exclusive open. [Join-Path](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.management/join-path?view=powershell-5.1)
and [New-Item](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.management/new-item?view=powershell-5.1)
belong to Microsoft.PowerShell.Management;
[Out-Null is in Core](https://learn.microsoft.com/en-us/powershell/scripting/whats-new/cmdlet-versions?view=powershell-7.4).
This identifies static prerequisites, without proving a loading cause or
authorizing an Import-Module or environment repair.

One additional Windows-only test therefore measures at most two fresh children
after the separate decoder preflight, using the same protected executable,
legacy argument mode and captured 15-name Attempt environment:

1. **Prefix:** the exact three pre-Open source statements, including the original
   `New-Item -ItemType Directory -Path $data -Force | Out-Null` pipeline, with
   fixed managed before/after markers around each statement. It never opens the
   mechanism lock or calls a replacement legacy function.
2. **Managed IO:** managed Path.Combine followed by the same
   File.Open(OpenOrCreate, ReadWrite, None) and Dispose on a different authored
   empty file. Fixed markers distinguish before-open, open-returned and closed.
   This is only a basic IO diagnostic. It cannot count as an actual legacy open
   or replace the required original Enter call, source hash/AST verification,
   attribute/identity/time checks, owner-loss exclusion or cleanup acceptance.

Each child uses its own newly created marked temporary cwd. Parent root-first
non-link metadata, directory identity and exact nonce bytes are rechecked before
launch and deletion. The encoded command/arguments contain no fixture, source
or profile path; managed CurrentDirectory supplies the root. The child checks
the directory and non-reparse marker and reads only its exact bounded nonce
before any diagnostic action. At that raw-control revision, no real grant,
repository/data root, attributes, account, import, module discovery command,
environment addition or warm-up was supplied. The later candidate below adds
one explicit OS-module prerequisite. There is no automatic READONLY clearing.

The existing runner retains its default decoder behavior. Only these controls
use its optional cwd and closed marker observer. Each still has a ten-second
wait, 8,192 bytes per stdout/stderr stream, the existing five-second cleanup wait
and bounded reader joins. A timeout with confirmed direct-child/reader/stream
cleanup may proceed to the second measurement; uncertain cleanup stops further
creation. Both fixed observation slots are present before the joint assertion;
an unstarted second child remains unavailable/not-started, never a fabricated
measurement. Confirmed cleanup is required before removing only the fixed
authored entries. Unknown entries, replaced identities, links or uncertain
stream closes retain the private workmap/objects, with no recursive destructor,
chmod, blind delete or cleanup retry.

Only ordered complete literal marker lines are observed. Duplicate, reordered,
unknown, malformed or trailing output, an unfinished terminal line, nonzero
exit, stderr, deadline or unconfirmed cleanup cannot pass. Incomplete stdout
may retain only the last complete admitted marker; even a complete final marker
with a timeout remains unavailable. Marker absence is not evidence an action
did not occur. Direct Popen/stdout controls do not recreate the mechanism's
named pipe, Job or retained creation authority and cannot identify its cause.
At that source checkpoint both new controls were **native pending**; the later
589 result below records their actual raw outcomes. The producer schema, original
Enter bytes, actual mechanism criteria and rights/Win11/R18/R19 gates stayed
unchanged.

## 589 negative and explicit OS-module prerequisite candidate

Exact `589362e7dc2e73da899751c042adbeb260ba5e56`
[run 41311326652](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/41311326652),
job 124862187054, attempt 1, image `20261030.294.1`, passed 261 Windows contracts
and failed the operation-control case, with zero skips in 13.99 seconds. The raw
prefix's last complete marker was `before-join-data`; it hit the ten-second wait
deadline, with no stderr, confirmed direct-child/readers cleanup and removed
fixture. The separate raw managed-IO child reached `complete` with no stderr,
confirmed cleanup and removed fixture. The actual mechanism was not run because
the authored-contract gate failed; no artifacts were uploaded. The missing next
marker establishes neither a loading cause nor absence of a physical action.
This negative and the earlier d35 baseline refusal remain unchanged evidence.

The current source candidate adds one shared `LEGACY_SYSTEM_MODULE` inline
prerequisite between `definitionbound` and `operationentered`, and the identical
fragment before the two operation-control bodies after their private fixture
validation. The decoder-only children remain module-free. This is one explicit
OS-module selection, with no import fallback, environment repair, extra native
variant or replacement legacy function. The protected image, 15-name Attempt
environment, script mode, checkpoints, schema and all deadlines remain unchanged.

[Microsoft documents fully qualified imports](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/import-module?view=powershell-5.1).
The fragment binds Desktop Windows PowerShell 5.1/x64, the actual current-process
image and `PSHOME` to the OS System directory's `WindowsPowerShell/v1.0` install.
It forms only that install's absolute
`Modules/Microsoft.PowerShell.Management/Microsoft.PowerShell.Management.psd1`.
The manifest is bounded by file length and, like the image and actual assembly
locations, receives canonical root-first directory/non-reparse metadata checks.
Independent source review caught an earlier leaf-first metadata walk. The
corrected guard first collects bounded ancestor strings without file queries,
then checks the volume root through each directory before querying the leaf.
The original candidate review and its finding remain historical; the correction
has portable source/order and capacity checks, with actual Windows execution
still pending.
No harness-owned manifest stream is created. The temporary current-process
wrapper is retained before reading its image and disposed once in finally;
unknown close retains that actual wrapper and original error privately, throws
fixed refusal text and never retries. Existing actual Attempt/Job close failures
retain their original private owners under the unchanged cleanup policy.

Only the current Core ImportModuleCommand in the running SMA assembly may import
the absolute manifest, locally with NoClobber and the two required cmdlet names;
no functions, aliases or variables are selected. One actual module must match the
chosen manifest path and directory. Its Join-Path/New-Item exports and actual
visible commands must be the documented JoinPathCommand/NewItemCommand types in
one Management assembly. Out-Null must remain the Core OutNullCommand in SMA.
The Core command used to inspect these bindings is also tied to that actual SMA
assembly. Its [ListImported lookup](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/get-command?view=powershell-5.1)
examines only loaded PowerShell command types, with no PATH or available-module
scan. There is no new PSModulePath, PATH, profile, utility module or discovery
repair.

The loaded assembly origin check uses
[ImplementingType](https://learn.microsoft.com/en-us/dotnet/api/system.management.automation.cmdletinfo.implementingtype?view=powershellsdk-7.4.0),
file-backed [Assembly.Location](https://learn.microsoft.com/en-us/dotnet/api/system.reflection.assembly.location?view=netframework-4.8.1)
and .NET Framework GAC status. The actual SMA GAC family must be exactly the
OS Windows directory's `Microsoft.NET/assembly/GAC_MSIL`; Management must occupy
the same family, with its exact assembly directory/file/simple name, matching
nonempty SMA public-key token and on-disk/loaded assembly identity. All ancestors
are checked before trust. The candidate does not guess a version directory or
require a Windows PowerShell 5.1 GAC DLL to reside in PSHOME. A differing layout
refuses; no alternate GAC root is adopted from failure. These are checks within
the existing protected OS-installation trust base, not a new Microsoft signature,
ACL, exact OS-module-byte provenance or sandbox claim. Import-Module executes
that trusted OS manifest; post-import checks cannot sandbox an untrusted one or
prove the engine never consults its own internal metadata caches.

The readable shared fragment is capped at 6,400 ASCII characters. Portable
contracts check the actual legacy command builder and both control commands
using Windows quoting and UTF-16 code units, including the terminating NUL,
against 32,767 units. The Windows controls repeat the check with the actual
protected image path. No file-based script or different grant transport is
introduced. The existing process helper independently refuses an oversized
actual CreateProcess command. Overflow checks count surrogate pairs correctly;
a Python character count alone is insufficient.

All original Enter bytes, source hash/AST checks, grant decoder, ordered progress,
operation result/classification, native ABI/attributes/identity/times,
retained-creation owner-loss sequence and cleanup predicates remain unchanged.
Portable tests and source-preservation comparisons establish only these source
properties. At that source checkpoint the shared-bootstrap controls and actual
mechanism were **native pending**; the 020 result below records the controls
refusing before the mechanism. A later successful bootstrapped observation would
belong to this candidate, not relabel the raw 589 attempt or prove its cause.
Production, keeper-loss and rights approvals remain false; ordinary-user Windows
11 remains unavailable. R18 and R19 completion remain unestablished.

## 020 bootstrap refusal and closed phase-only localization

Exact `020c44fec8afd66de9e471fe732cb852af5a96da`
[run 41316192484](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/41316192484),
job 124876672717, image `20261021.278.1`, passed 267 Windows contracts and failed
one, with zero skips in 5.06 seconds. Both shared-bootstrap controls retained
only `fixture-validated`, with protocol refusal, stderr present and fixed CLIXML
prefix metadata. Both direct children/readers finished and both fixtures were
removed after confirmed cleanup. The actual mechanism was skipped and zero
artifacts were uploaded. This establishes no bootstrap stage or cause; in
particular it is not evidence for an autoload, parameter-binding or GAC cause.
The raw 589 result and this 020 negative keep their separate identities.

The new source candidate adds only one finite private `C7BootstrapPhase` variable
to the identical shared module fragment, immediately before image, paths, core,
import, module, assembly and visible checks, then complete. It adds no IO,
stdout, imports, trust paths, environment, conditions, retries or deadline to
that fragment. Removing these assignments recovers the entire reviewed 020
bootstrap byte-for-byte. The actual legacy script ignores the variable and
retains its original exception, named-pipe exchange, source/Enter criteria and
cleanup behavior. There is no public mechanism checkpoint or schema change.

Only the two existing operation controls wrap precisely that shared fragment in
try/catch, after private fixture validation and before the original operation
body. The original ErrorRecord is retained privately; no message, stack, path,
type name or arbitrary value is serialized. A caught error emits exactly one
fixed ASCII terminal line and exits 2:

```text
C7B|<finite phase>|<finite error category>
```

Phase is checked against the fixed eight stage names; unavailable is the fixed
fallback if the variable cannot supply one. Error is guard for the known fixed
bootstrap guard refusal, close for its known once-close refusal, binding for a
ParameterBindingException within at most four exception objects, or other.
These are coarse private-error families, not cause diagnoses or permission to
weaken a guard. Actual CurrentProcess close error/object retention is preserved;
the control catch never retries Dispose or replaces the original retained
ErrorRecord. Fixture, parsing, startup or later operation failures are outside
this narrowly caught fragment and cannot produce a fabricated bootstrap stage.

The test-only operation observer gains exactly two finite fields:
`bootstrap_phase` and `bootstrap_error`. It admits a C7B context only after the
single complete `fixture-validated` line, as the sole complete terminal record,
with exit 2 and no stderr. Unknown, duplicated, out-of-order, BOM/non-ASCII,
extra-field, trailing or incomplete records cannot supply context. A deadline
or uncertain runner cleanup supplies no accepted bootstrap context even if a
complete error line was captured. Unavailable means no such context was
admitted; it does not mean an operation did not occur. Full success still
requires every unchanged ordered operation marker, exit 0, complete/none
bootstrap fields, empty stderr and confirmed runner/fixture cleanup. An error
context never supplies an operation or mechanism success.

The fragment remains below 6,400 ASCII characters and all complete encoded
commands remain checked against the same 32,767 UTF-16-unit Windows limit,
including the actual protected image, quoting and terminating NUL. No file or
wire fallback, extra child or diagnostic variant is added. Portable contracts
cover every finite error context and malformed/deadline/privacy negatives,
plus preservation of the actual legacy script, Enter source, helper, schema,
15-name environment, deadlines and original operation/cleanup predicates.
The revised controls and actual mechanism remain **native pending**. No module
repair, historical failure cause or production/rights/Win11/R18/R19 acceptance
follows from portable checks or the earlier negative observations.

## 8449 module refusal and test-only predicate localization

Exact `8449d816bc52fedd11c0d531c05e46f0d693c795`
[run 41323022215](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/41323022215),
attempt 1, job 124897083316, image `20261021.278.1`, passed 350 Windows
contracts and failed one, with zero skips in 5.11 seconds. Both existing
controls reported `fixture-validated`, phase `module` and error `guard`, with
protocol refusal and empty stderr. Both direct children/readers finished and
both fixtures were removed after confirmed cleanup. The mechanism and metadata
retention steps were skipped; the provider returned zero artifacts. Duplicate
renderings of the same two control results are not additional observations.
These results identify the combined module guard, without identifying which
predicate failed or establishing an import, module path, type or GAC cause.
The earlier raw 589 and bootstrap 020 negatives retain their separate meaning.

The next source candidate changes only the existing test-control catch and its
closed observer. Only for `module` plus `guard`, it rereads the same five
metadata predicates in their original short-circuit order and reports the first
still-failing predicate as `guard-count`, `guard-type`, `guard-name`, `guard-path`
or `guard-base`. It performs no additional IO or import. If no predicate still
fails, the original `guard` remains. If classification throws, its actual
ErrorRecord is retained privately and the fixed category becomes `other`;
the original bootstrap ErrorRecord remains retained separately. No raw value,
path, type name, error message or stack is serialized.

The [PowerShell 5.1 Import-Module contract](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/import-module?view=powershell-5.1)
documents the PassThru module object and full-path import. The documented
[Path](https://learn.microsoft.com/en-us/dotnet/api/system.management.automation.psmoduleinfo.path?view=powershellsdk-7.4.0)
and [ModuleBase](https://learn.microsoft.com/en-us/dotnet/api/system.management.automation.psmoduleinfo.modulebase?view=powershellsdk-7.6.0)
properties distinguish the defining file and module directory. These contracts
do not reveal this run's actual metadata values or justify weakening its exact
path or origin checks. The finite predicate result is a later observation of
the existing metadata, not proof that a particular value caused the original
exception.

The five subcategories occupy the existing error field and are admitted only
with phase `module`, the complete existing terminal C7B frame, exit 2, empty
stderr and the existing order/cleanup requirements. Other phases, future or
malformed categories, extra fields, private bytes and partial/deadline output
refuse. They cannot supply success. No field, frame, child, checkpoint, schema,
environment, deadline or import/trust criterion is added. The actual shared
module fragment and legacy script, original Enter and process helper remain
byte-identical to 8449. Complete encoded commands retain the existing Windows
UTF-16 capacity check. Portable tests establish these source/parser properties;
PowerShell 5.1 execution and the revised native controls remain **unavailable
locally**. This is cause localization, with no proven fix or new mechanism,
cleanup, keeper, rights, Windows 11, R18 or R19 acceptance.

## Current source validation

The cheap portable [authored tests](../backend/tests/test_runtime_lock_attribute_probe.py)
cover canonical sender fields and UTF-8, malformed complete frames, fragmented
writes and one deadline, strict null-only v5 context and historical-schema
rejection. The preserved cases cover ABI widths, file/attribute/identity/time
preservation, zero-writer state ordering, creation-handle observation, strict
response checkpoints/EOF, once-close and sticky cleanup. Generic actual parent
capture fault cases retain uncertain process/reader objects without raw output.

One Windows-only preflight case exercises the exact v5 .NET codec using authored
StringReader inputs in both actual environment sets. It performs no C7 fixture,
source file, native file API or legacy operation. It is explicitly skipped on
other hosts and cannot substitute for the actual mechanism. The old v4 engine
and literal-control tests remain historical, not active v5 gates. A separate
Windows-only case covers the two authored prefix/managed-IO observations with
the identical OS bootstrap above; portable regressions cover strict markers, private cwd/nonce admission,
malformed/partial output, two-slot ordering, and actual retained marker streams
on injected close failure. Neither local skip establishes Windows behavior. Run
`python -B -m pytest --noconftest -q backend/tests/test_runtime_lock_attribute_probe.py`
and documentation checks. Shared process-helper evidence remains separate.
No installer, old ZIP edit, global writer admission, real data copy, owner-aware
update, preserving recovery or Windows 11 acceptance follows.

## 1b4366f guard-base refusal and control-only base-role projection

[Run 41337882449](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/41337882449),
attempt 1, tested exact `1b4366f81f9734ca6f4d95207dbbc4246dd15b64`.
Windows job 124941494224 on image windows-2025-vs2026/20261030.294.1
failed authored contracts with 455 passed, one failed, zero skipped in 5.69
seconds. Both actual controls reported `module/guard-base` after
`fixture-validated`, with `unavailable`, `protocol-refused` and empty stderr.
Both child/readers finished and both fixtures were removed after confirmed
cleanup. The mechanism and publisher steps were skipped; the run has zero
artifacts. This is negative evidence, not a C7 mechanism observation. The
earlier 8449 `module/guard` result is not retrospectively relabeled.

This concerns the protected OS `Microsoft.PowerShell.Management` module, not
the companion script. Its actual `ModuleBase` value was not emitted. The
[generic SDK property documentation](https://learn.microsoft.com/en-us/dotnet/api/system.management.automation.psmoduleinfo.modulebase?view=powershellsdk-7.6.0),
which also applies to Windows PowerShell 5.1, describes the manifest-parent
default. However, the official engine importer has a separate override for
engine modules to the PowerShell application base, and its engine-module set
includes `Microsoft.PowerShell.Management`.
See the [tagged importer](https://github.com/PowerShell/PowerShell/blob/v6.0.0/src/System.Management.Automation/engine/Modules/ImportModuleCommand.cs#L1645)
and [engine-module set](https://github.com/PowerShell/PowerShell/blob/v6.0.0/src/System.Management.Automation/engine/InitialSessionState.cs#L4469).
These Core-era sources are not an observation of this runner's protected
Desktop 5.1 implementation. They support checking the relationship; they do
not establish the actual role or explain the failure.

The next test-control observation reuses `bootstrap_error`, the existing third
field of the single `C7B|phase|category` terminal. After the existing classifier
has selected exactly `module/guard-base`, it reads the returned ModuleBase
once and emits only one fixed role category:

- `guard-base-system-home`: a string equals the already validated protected
  system home using OrdinalIgnoreCase.
- `guard-base-manifest-parent`: a string equals the parent of the already
  constructed exact OS manifest using OrdinalIgnoreCase.
- `guard-base-other`: a string matches neither fixed role; its value is private.
- `guard-base-unavailable`: the value is not a string or classification throws.

The original ErrorRecord stays retained; a classification error stays private
and cannot replace it or produce success. All four categories are admitted only
as an unavailable module-phase failure after the validated fixture, with the
existing complete exit2 terminal and no stderr. Historical `guard-base` remains
valid. Malformed, private, future, cross-phase, duplicated, trailing, partial,
deadline or unconfirmed-cleanup output still cannot pass the operation controls.

Only the test catch adds this 633-character projection. It performs string
comparisons and path-string processing, with no additional IO, import, process,
frame, field, environment or deadline. The actual producer module guard,
shared 6194-character fragment and its 6400-character cap, legacy script,
original Enter and process helper remain unchanged. There is no new origin
allowlist or mechanism eligibility. In particular, an assembly-parent role
cannot be inferred before the later actual assembly-origin validation.

Portable quoting checks count UTF-16 units including NUL: the conventional
protected system-image text fixture yields 26694 for the prefix control and
26470 for managed IO, below 32767. The unchanged legacy command yields 31126.
These are source-text measurements; the existing Windows pre-launch assertions
still check the actual protected executable before either control. Native
PowerShell is unavailable on this Mac. The actual base-role result, any later
origin-binding correction, C7 mechanism, rights, Windows 11 and R19 acceptance
remain unverified. No installer or release is authorized by this observation.

## 0898 system-home observation and exact engine-module base

[Run 41344420480](https://github.com/matthias-van-der-galien/Game-immersion-toolkit/actions/runs/41344420480),
attempt 1, tested exact `0898c1b431b77a5e6fc69c2a80f111e933496603`.
Windows job 124961112803 on image windows-2025-vs2026/20261030.294.1
failed the authored contracts with 705 passed, one failed and zero skipped in
5.22 seconds. Both actual prefix and managed-IO controls reported
`module/guard-base-system-home` after `fixture-validated`, with unavailable,
protocol-refused and empty stderr. Both direct child/readers finished and both
fixtures were removed after confirmed cleanup. These values came from the
genuine failure record, not a source-string match. The mechanism and publisher
were skipped and provider artifacts were empty. The earlier 1b and 8449
negative results remain unchanged.

The generic [ModuleBase API description](https://learn.microsoft.com/en-us/dotnet/api/system.management.automation.psmoduleinfo.modulebase?view=powershellsdk-7.6.0)
describes the normal manifest-parent base. Official PowerShell's
[engine-module override](https://github.com/PowerShell/PowerShell/blob/v6.0.0/src/System.Management.Automation/engine/Modules/ImportModuleCommand.cs#L1776)
uses the PowerShell application base, and the
[engine-module set](https://github.com/PowerShell/PowerShell/blob/v6.0.0/src/System.Management.Automation/engine/InitialSessionState.cs#L4857)
includes Microsoft.PowerShell.Management. These Core-era sources support the
relationship; they are not the runner's Windows5.1 binary/source identity.
The two current controls provide the actual Desktop5.1 role observation.

The fifth producer predicate and its classifier mirror now require ModuleBase
to equal exactly the already validated `$systemHome`, using OrdinalIgnoreCase.
This replaces the former manifest-parent expectation. There is no OR, alternate
base, trimming, path-search fallback or new allowlist. The independent
count/type/name/manifest-path guards and subsequent cmdlet/GAC/assembly/type,
root-first filesystem/reparse and ACL checks remain unchanged. The separate
manifest-parent role diagnostic remains available for a future refusal; it is
not an accepted base. Neither diagnostics nor a matching base bypasses the hard
operation-control or actual C7 mechanism criteria.

Only this exact expectation and its mirrored classifier change. The original
Enter body, companion/process-helper source pins, grant decoder, environment,
wire/public schemas, owners, deadlines and cleanup rules remain unchanged.
The shared fragment is now 6167 characters under the unchanged 6400 cap.
Source quoting measurements including NUL are prefix26550, managed-IO26326 and
legacy31054 under the unchanged 32767 limit. The previous figures above describe
0898 and earlier source; they are not relabelled. The current source contracts
reverse the exact predicate correction before comparing historical bytes, and
retain the actual Windows protected-executable pre-launch assertions.

Portable verification does not execute this PowerShell correction. A new
exact-head Windows result must still establish the unchanged assembly/visible
guards, pre-open operations and separate attribute/owner-loss mechanism. No
root/compiler/user permission, Windows11 hardware, rights, global/physical or
keeper-loss ownership, installer or R19 gate is closed by this source change.
