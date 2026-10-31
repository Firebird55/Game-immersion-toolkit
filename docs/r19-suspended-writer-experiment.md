# R19 retained suspended-writer primitive

`WindowsPreparationProcess.create_suspended` is an opt-in native creation
primitive, with no caller in the production host or source preparation path.
It creates the actual requested process suspended inside the owner's existing
Windows Job and retains the real process and primary-thread creation handles.
The existing `command()` and join-before-spawn `_bootstrap()` remain unchanged.
Suspending that legacy bootstrap alone would not register its eventual worker
before worker startup; this new route creates the selected writer directly.

The caller supplies an absolute executable, explicit argv, absolute working
directory and explicit Unicode environment. There is no shell, stdin command
protocol, PID-file adoption, added runtime child target or manifest permission.
The primitive does not verify an executable supplier or grant execution rights;
the caller must independently select and verify its fixed authored inputs.

## Creation and lifetime

The owner registers one child object holding the same `PROCESS_INFORMATION`
storage **before** calling `CreateProcessW`. Process/thread handles returned on
success therefore remain owned even if later membership validation, Python
processing or attribute cleanup fails. Failed creation outputs cannot be adopted
as handles; unexpected nonempty outputs leave ownership unconfirmed.

`STARTUPINFOEXW` contains exactly the owner's existing Job through
`PROC_THREAD_ATTRIBUTE_JOB_LIST`. The attribute storage and Job-handle array
remain alive until creation returns and the attribute list is deleted. Creation
uses `CREATE_SUSPENDED`, `EXTENDED_STARTUPINFO_PRESENT`,
`CREATE_UNICODE_ENVIRONMENT` and `CREATE_NO_WINDOW`. Handle inheritance is false;
no Job, lease, profile or control handle is delegated to the writer. Unsupported
Job-list creation fails without a later assign-after-spawn fallback. This needs
Windows 10/Server 2016 or later according to the
[attribute API](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute).

Before admission the retained process object must be live and belong to the
exact selected Job. `resume_once()` calls `ResumeThread` at most once and accepts
only previous suspend count 1. Zero, a count greater than 1 and native failure
close further admission. They are never repaired by blindly resuming again.
[ResumeThread contract](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-resumethread).

`stop_and_wait(deadline)` addresses only the retained creation object and waits
for that object to become signaled. Owner drainage first stops these registered
objects, then uses the existing descendant Job-drain contract. Primary-thread
and process handles are closed after confirmed exit, before closing the Job.
An early Job close refuses; a timeout retains handles for explicit cleanup.
Job-accounting zero alone remains insufficient to prove process completion.

Unknown native ownership poisons the child and owner, prevents handle exposure
and further native operations, and cannot report successful cleanup. A failed
close can be retried only for error 5 with an observed
`HANDLE_FLAG_PROTECT_FROM_CLOSE`; error 6 or other unclassified outcomes cannot
be queried or retried using a potentially recycled numeric value. This follows
the existing owner policy and the
[CloseHandle contract](https://learn.microsoft.com/en-us/windows/win32/api/handleapi/nf-handleapi-closehandle).

One owner `RLock` serializes the new create/resume/stop/child-close operations
with complete Job drainage and Job closure. Drain/close shut new admission at
entry even when the child registry is empty. A create already in progress keeps
its selected Job alive until the same registered output record is finalized;
a waiting drain/close then sees that record. Resume and drain have one ordered
admission decision. The legacy `command()`/bootstrap route keeps its existing
semantics and does not acquire the new admission requirement. Borrowed handle
values are not transferable ownership and must not be cached across concurrent
lifecycle changes.

## Authored Windows contract

The native regression process acts as the **living keeper**. It holds both
source-compatible legacy/target leases, creates a separate non-writing guardian,
and creates a fixed authored leaf writer with the real currently running
interpreter image. The writer has no venv redirector, frozen bootloader, hidden
worker launch or arbitrary stdin command. It writes only a newly authored
temporary marker after resume.

The two cases terminate the guardian either before admission or after the
writer has started. They require no marker before resume, genuine Job membership,
retained process/thread objects, writer signaling before cleanup, and independent
Windows error 32 lease exclusion before/after guardian loss through writer exit.
Successful independent access is required only after explicit keeper release.
Baseline writable access distinguishes sharing violation from permission failure.
The source launcher's unchanged operation function has separate interoperability
coverage in the guarded cold-slot experiment; this new test does not run the
source updater or create a nested-lock bypass.

Local fake-native tests exercise creation ordering, exact Job-list/flag use,
resume-count failures, post-create failures, timeout retention and invalid-handle
refusal. Event barriers also exercise create/drain, create/close and resume/drain
interleavings using a real reentrant lock; no timing sleeps establish their
ordering. Those tests do not establish native execution. The real Windows cases
must run on the exact checked-out source before native results are recorded.

## Remaining gates

This primitive provides no autonomous keeper, guardian IPC or lease handoff.
Keeper loss and simultaneous controller loss remain unproved. A registered
direct creation object is not admission coverage for arbitrary descendants,
future preparation/export/ASR workers or an entire frozen bootloader tree.
Existing Job cleanup may reap descendants without establishing that they were
registered before writes. Do not convert this result into an all-writers barrier.

The native fixture uses source/build-host Python only. Frozen entrypoint
integration, inherited PyInstaller DLL-directory behavior, exact executable/native
origins and compiler-free user operation need separate artifact evidence. No
frozen dispatcher, source bootstrap or production caller is changed here.
Warm routing, browser chunk continuity, capture/credentials, store copying,
rights/source-delivery approval, clean Windows 11 acceptance and full R19
completion remain separate gates. No installer is built.
