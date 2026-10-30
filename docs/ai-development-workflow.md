# AI development workflow for the rework

This is the execution proposal for the [rework roadmap](rework-roadmap.md).
[AGENTS.md](../AGENTS.md) and [RELEASE.md](../RELEASE.md) remain authoritative.
Reading these documents does not start implementation or authorize a release.

**Write in English**, even when the assignment or review is in Dutch or another
language. Use English for engineering documentation, task/PR descriptions,
comments and reports. Preserve intended multilingual product text and test input;
do not introduce mixed-language explanatory prose.

Treat supported games equally. Do not prioritize ZZZ because it has existing
special handling or an available package. Select work by demonstrated defects,
missing presentation coverage, user impact and useful evidence. A ZZZ pilot is
one input to reusable infrastructure, not the definition of game support.

## Bounded work and ownership

Plan around observable outcomes and evidence, not lines of generated code or
agent count. AI can help with investigation, implementation, annotations and
review; integration, reliable expected results and device access remain real
constraints. Do not promise a fixed AI speed multiplier.

| Role | Responsibility |
| --- | --- |
| Workstream owner | Own W1 UX, W2 recognition or W3 installation, including necessary tests and delivery |
| Integrator | Coordinate interfaces, overlapping changes, migrations, R25 test reduction and combined acceptance |
| Implementer | Deliver one assigned bounded task with relevant checks and a reviewable commit |
| Reviewer | Examine criteria, actual code/diff and check output independently of the implementation summary |
| Device tester/maintainer | Provide physical verification and decisions requiring actual hardware or owner judgment |

One workstream owner can also integrate. There is no need for a fourth full-time
role or a global discovery phase. Start with one concrete task per assigned
workstream. Parallel implementation is useful only when explicitly assigned,
interfaces are clear and review capacity exists. Reading a roadmap about parallel
work does not itself authorize spawning agents or messaging other tasks.

Avoid simultaneous writers to the same shared file or contract. Use suitable
isolated worktrees when needed, preserving host workspace-location instructions
and unrelated local work. Worktrees do not resolve semantic conflicts; one owner
integrates and checks the result. See the
[ownership table](rework-roadmap.md#ownership-and-milestones).

Architecture tasks have concrete owners in R12/R13. Do not start a generic layer,
event-bus, language or storage rewrite. Extract only the boundary needed by the
assigned change. Tests remain part of that change, not an additional broad lane.

## Task contract

Keep a concise contract in the task/PR or a linked execution note. Do not create
a task database or collection of empty status files. Store only sanitized evidence.

```text
Task: Rxx — concrete outcome
Workstream/owner: W1, W2, W3 or assigned R25 area
Status: planned | ready | active | implemented | verified | blocked
Baseline: branch/commit and relevant changes since the research
PR target/check base: repository, branch, fetched remote/ref and base SHA
Goal: observable behavior or measurable maintenance improvement
Scope: modules, integration owner and explicit adjacent exclusions
Dependencies: exact contracts/tasks; work that can proceed independently
Invariants: applicable data/account/language/capture/storage rules
Acceptance: independent success/failure examples and expected outputs
Evidence boundary: what this task proves; remaining consumer/device evidence
Inputs: fixture/package/model versions, presentation and sampled language pairs
Checks: exact commands, supported host, reason for each added/retained test
Cost: measured timing or planned budget for expensive checks
Unavailable resources: missing inputs/hardware and affected claims
Rollback: safe reversal and data-preservation strategy
Delivery: commit, results, review and remaining work
Next step: specific continuation within scope or concrete decision
```

`ready` requires known scope, interfaces and testable criteria, not another
permission round. `implemented` means code exists but required evidence may still
be missing. `verified` requires the task's actual acceptance evidence, including
applicable consumer/device checks. `blocked` names a specific missing prerequisite
and independent work that can continue. A documentation pass does not complete
a product task. M1 is per workstream; M2 checks integration; M3 checks the candidate.

## Execution loop

1. Read instructions, inspect Git status and the relevant current code, and use
   a `codex/` task branch. Preserve unrelated work. Reuse the study rather than
   restarting a repository-wide investigation.
2. Establish independent expected behavior. Reproduce a defect; characterize
   relevant invariants before risky extraction. Do not add tests for simple copy
   or styling merely to increase coverage counts.
3. Implement the smallest coherent change using existing contracts. New game
   heuristics, storage migrations and runtime decisions need their own evidence.
4. Run selected checks and justified additional cases. Investigate failures;
   do not weaken assertions or delete regressions to obtain a green result.
5. Review proportionately. Capture, accounts, migration and lifecycle need an
   independent reviewer of the actual diff and outputs. Documentation needs a
   focused consistency review, not the full product test matrix.
6. Fix valid findings, check affected behavior and commit the logical change
   using GitHub noreply author/committer identity. Check the integrated result.

Routine authorized work does not require repeated permission. Deliver independent
work before presenting a genuine scope decision or missing external prerequisite.
The roadmap grants no implicit permission to release or write to real accounts.

## Screenshot and package assignments

Follow the [screenshot regression plan](screenshot-regression-plan.md). Keep
presentation coverage separate from sampled language coverage:

- Inventory every active game's known and uninspected presentations. Gather
  screenshots for reported holes and nearby negative cases. Cover non-comic
  layouts such as overhead speech, cards, wrapped captions and legacy panels.
- Select a few supported language combinations, initially three to five across
  the chosen corpus. Record why each adds distinct evidence. Keep bug regressions
  pinned; rotate only supplemental samples, with exact versions and selection.
- Independently annotate required/forbidden catalog identities, language/voice
  bindings and order or unknown order. The implementation cannot generate its
  own expected truth. A reviewer repeating an unchecked assumption is not an
  independent oracle.
- Test the normal mobile ZIP importer and production image/OCR/matching/controller
  path in the built artifact. Distinguish real OCR from injected observations,
  synthetic packages from real packages, and binding checks from real audio decoding.
- Single images do not prove chronology or phone stability. Use small ordered
  screenshot sequences and controlled clocks for movement, repetition and stale
  results. Resampled duplicates are not new observations; distinct observations
  can have identical pixels.
- Prove the harness catches a representative wrong identity, omission, duplicate,
  stale result and wrong locale. Do not create an unrestricted mutation campaign.
- Keep held-out scenes independent of tuning. When one becomes a bug regression,
  version the corpus and replace that independent evaluation case.
- Do not fetch live YouTube playback in CI. The review's real ZZZ package remains
  an unverified pilot candidate until inspected; do not report it as tested or
  publish its link/data in fixtures or logs. Use the same contract for other games.

R07a characterizes the current production page. R13c then extracts its controller,
proving the existing shell and direct harness. R07b reuses that factory for
screenshot execution. Never require finished R07b before R13c or build a second
test-only recognition loop. Preserve known defects as explicit baseline findings,
separate from desired acceptance; extraction and behavior changes have separate commits.

## Necessary tests and supported platforms

Each new test names the failure it prevents and why existing cheaper coverage is
insufficient. R25 reviews the existing thousand-plus Python tests and overlapping
browser jobs with the same standard. Consolidate redundant cases and remove
obsolete/unsupported behavior checks with a documented rationale or replacement.
Preserve distinct regression and safety guarantees. Test count is not a target;
failing product regressions are not candidates for deletion to conceal the failure.

Prefer a cheap unit/contract test for logic plus a few actual OCR/package/browser
checks for integration. Reuse builds and fixture/model initialization, select only
affected cases and record timings in ignored `output/checks/`. Measure before
setting or expanding an expensive job's budget. Repeat a passing broad suite only
after relevant changes, failures or unresolved concerns.

Windows is the supported desktop platform. Use macOS/WebKit when needed for mobile
browser coverage; it does not prove physical iOS or macOS desktop support. Do not
add Linux product/browser checks. Plan removal or relocation of existing Linux
test jobs in R25 without losing needed supported-target coverage. A Linux static
publication job is infrastructure, not a product compatibility test.

## Handoff and integration

Producer and consumer owners agree field meaning, errors, compatibility and the
necessary tests. One owner integrates a small preparatory contract change before
dependent work uses it. Consumers need the contract, not a finished workstream.

For example, R17 needs R04 reading preferences and the R14/R18 storage agreement,
but discovery/bundling can progress meanwhile. R08 defines occurrence/group/order
semantics with W1; R09 proves desktop, restored history and paired-PC reconnect;
R10 proves the local mobile path and restored history. Favorite semantics must
not collapse genuine later occurrences. Include visible UI and persistence evidence.

Changes to an agreed interface identify affected consumers and carry the required
adapter/migration. Development with stubs is useful but does not prove integration.
Do not silently hand off a breaking contract or assume the other stream will fix it.

## Verification and evidence

Use the existing selector; see [development checks](development-checks.md).

| Situation | Verification |
| --- | --- |
| Working changes | `npm run check:changed` |
| Task branch | `npm run check:changed -- --base <target-ref>` after fetching/validating the actual PR target |
| Criterion not covered by selector | Named additional scenario with a reason |
| Candidate/release | Existing comprehensive supported-target browser/packaging gates in GitHub-hosted CI |
| Native Windows or physical iPhone/iPad claim | Relevant device protocol on the actual candidate |

Check the target repository/branch in the PR and map it to a Git remote. Fetch
that target and record `git rev-parse <target-ref>` with the checked commit.
For a fork whose `upstream` points to `Firebird55/Game-immersion-toolkit`, use
`git fetch upstream main` and `npm run check:changed -- --base upstream/main`.
If `origin` points to that target repository, use `origin/main` instead. The push
remote is not automatically the check base. A missing/stale base is not success;
do not select an older base to omit checks.

The selector at the research baseline compares the base directly with HEAD and
includes local changes. If the target advances, assess the difference and record
remaining integration evidence. Stage new docs before link checks because the
checker uses `git ls-files`. Keep raw timing output ignored.

Report each check as **pass**, **fail**, **not run** or **unavailable**, with commit,
command, fixture/package/model versions, environment and reason. Missing assets
or host dependencies are different from reproduced product defects. A skipped
Windows test on another host is not a pass. Real-input hosted execution is
conditional on the screenshot plan's access and privacy rules; a local real-input
run must not be labelled a GitHub result.

The minimal sanitized handoff contains the task ID, commit, criterion outcomes,
check results, review findings, rollback and exact remaining work. Private media,
accounts, download URLs, paths and raw logs stay out of Git and public artifacts.
After context loss, read that handoff and current state instead of restarting
completed work or declaring missing evidence successful.

## Device evidence and scope limits

Mock OCR does not prove native OCR installation. Desktop WebKit does not prove
iOS background capture, physical file-provider access or session endurance.
A source build does not prove a clean Windows installation. Synthetic DOM fixtures
do not establish compatibility with a real browser extension.

Prepare an installable candidate, concrete steps, expected results and a sanitized
report format before asking a tester to act. Use the existing
[mobile acceptance protocol](mobile-capture-verification.md). Results apply only
to the named hardware, OS, browser, game and artifact versions. Continue independent
work while device evidence is unavailable.

## Example assignment

Use this only after a task has actually been assigned:

> Execute task Rxx from the rework roadmap. Read AGENTS.md, RELEASE.md and the task
> contract. Verify the baseline and Git status; preserve the stated invariants and
> stay within the assigned modules. Write all engineering prose in English. Use
> independent expectations, justify any new tests and run relevant checks on
> supported targets. Review risky behavior and deliver a checked commit with
> evidence and rollback. Report missing input/device evidence accurately, continue
> independent work and do not expand scope silently. This assignment includes no release.
