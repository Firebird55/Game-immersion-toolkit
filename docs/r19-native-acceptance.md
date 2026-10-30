# R19 native acceptance inputs and receipt consistency

This is a private test protocol and a review-host consistency tool, not newly
executed native evidence. The [R18 acceptance table](r18-runtime-inventory.md#r19-acceptance-plan)
and [R19 D/E/F criteria](r19-completion-plan.md#d-clean-windows-11-acceptance)
remain authoritative. No installer, runtime promotion, live migration, account
write, browser-profile copying or change to PR #59 is authorized by this file.

## Minimum external environment still needed

The current standard [GitHub-hosted runner table](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
provides Windows x64 Server 2022/2025 images. Its Windows 11 labels are ARM64.
Those images do not supply the selected Windows 11 25H2 x64 ordinary-user and
physical display/profile environment. Windows-latest is not evidence of that
target. Microsoft identifies [25H2 as OS build 26200](https://learn.microsoft.com/en-us/windows/release-health/windows11-release-information).
The selected baseline is fixed; a later Windows release needs a separately
reviewed baseline change, not an assertion that it is equivalent.

Before native work, the tester/integrator needs:

1. Authorized access to a disposable Windows 11 25H2 **x64** client machine,
   non-elevated ordinary-user execution, no discoverable Python/Node/package
   manager/SDK/compiler, and exact eligible extracted candidate/inventory bytes.
2. An interactive owned display/window surface, two physical monitors allowing
   negative coordinates, and 125/150/200% DPI cases. Use independently authored
   Chinese and non-Chinese captions, never a captured private desktop as a
   public fixture. Missing hardware remains unavailable.
3. User-provided compatible Snipping Tool OCR assets and their build/digests.
   Keep proprietary files local. Test absent/stale/denied states separately;
   source imports or an OCR mock cannot substitute for actual capture output.
4. The selected ordinary Chromium and Firefox profiles with the relevant
   extensions and a disposable authored test state. Preserve origins and user
   stores; do not create a fresh profile and call it continuity. Do not copy raw
   browser databases or modify unrelated settings. Actual access and scope must
   be authorized before operating those profiles.
5. Same-user protected **TEST** blobs, synthetic copied data and a current
   writer-stop/owned-cleanup proof for data/update cases. No real credentials,
   account writes or existing-installation migration are required for these
   baseline cases. Optional installed-game probes are separately private and
   need their own authorization/input availability.

Record exact OS patch, hardware, CRT, OCR/browser/extension versions, display
topology and source/candidate measurement context privately. Keep raw paths,
profile names, screenshots, captions, protected bytes and private detailed logs
out of public reports. A random private installation identity may be represented
by its SHA-256 environment_id; do not hash a username and call it anonymous.

## One candidate and ten required rows

[The consistency verifier](../backend/r19_acceptance.py) defines stable row and
operation IDs for all ten R18 acceptance rows. Every row must be passed, failed
or unavailable. Missing rows, partial operation coverage, mixed source/build/
inventory identities, changed receipt bytes, unsafe paths and duplicate JSON
fields are rejected. A pass needs a receipt file and exact SHA-256, not an
unresolved CI delegation or a manually edited summary label alone.

Each private receipt uses schema proxy-r19-acceptance-receipt-v1, the exact
source_commit/build_id/inventory_sha256, row, status, method, operations,
environment, live_accounts_accessed=false, real_data_modified=false and
measurements. See OPERATIONS in the verifier for exact required operation IDs;
each claimed operation must be passed. Retain the independently inspectable
original native/fixture observations behind each receipt. The wrapper does not
create observations and a digest cannot prove that a claim happened.

The clean-host, native OCR/capture, ordinary-browser, copied-data and measurement
rows require method native-client. Their environment records exactly os,
release, display_version, build, architecture, elevated, developer_tools,
interactive, physical_display, environment_id and browser_profiles. Server,
ARM64, elevated, developer-equipped, noninteractive or missing-display claims
cannot satisfy that scope. Browser profiles must be ordinary-selected for both
chromium and firefox. Native continuity and measurement rows must identify the
same private environment. Other actual subprocess/format rows may use
native-client with the same strict client environment schema, or authored-native
on Windows Server 2025 x64 build 26100. Authored receipts use the same bounded
environment fields, require non-elevated execution and no discoverable developer
tools, and declare interactive/display availability as booleans. Their optional
chromium/firefox profile values are authored-test or ordinary-selected. A build
host with discoverable compilers cannot contribute an extracted-runtime pass.
Server rows do not require a physical display and never replace the five native
client rows; Linux, ARM64, arbitrary environment objects, source-only or mocked
process success remain insufficient.

The baseline_delivery row records separate source/candidate samples on that
environment: one cold start, five warm starts, first usable caption, process-tree
private/RSS/CPU, 60-second idle CPU, compressed/extracted size, peak preparation
and failed-update disk, and recovery within the preselected 30-second budget.
Signature and attestation observations remain separate, including honestly
not-signed/not-attested or unavailable. No retrospective speed threshold is
invented by this checker.

## Review-host commands and output limits

Run this stdlib-only tool on the review/build host. It does not require Python
on the clean acceptance PC and never launches capture, OCR, a browser or the
candidate. Keep inputs and output under private ignored check storage:

```text
python scripts/check-r19-acceptance.py --inventory <private-inventory.json> --template --output <fresh-matrix.json>
python scripts/check-r19-acceptance.py --inventory <private-inventory.json> --manifest <private-matrix.json> --evidence-root <private-receipts> --output <fresh-review.json>
```

The template answers every row unavailable and pins the exact inventory bytes.
An existing output is preserved. Relative receipt paths must stay inside their
explicit evidence root and cannot use links/reparse points. Receipt files are
size bounded. The report copies only fixed row statuses, receipt digests and
candidate identity; it does not copy private environment/caption/error content.

Exit 0 means the template was written, or all supplied row claims and component
dispositions are consistent enough for independent acceptance review. Exit 1
means required row coverage or exact component disposition is incomplete. Exit
2 means inconsistent/unavailable inputs or output refusal. None means native
execution was verified by this tool. Even a completely consistent matrix emits
production_execution_allowed=false and r19_complete=false. The actual acceptance
review and separately authorized implementation decision still own promotion;
JSON labels cannot grant licenses, prove hardware actions or enable a profile.

The focused tests use authored receipt objects only. They exercise rejection of
Server/ARM/developer/mock/fresh-profile and mixed-artifact claims, incomplete
R02b samples, changed bytes and path escapes. They are not Windows hardware,
native OCR, browser-profile or protected-credential acceptance results.
