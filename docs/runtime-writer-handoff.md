# Production writer handoff

The desktop host must retain ownership of the old runtime until its actual
writers stop. Cancelling an asyncio waiter does not stop work already running
in a Python executor or a native decoder.

The API now closes an admission barrier before draining requests, background
preparation, exports, capture, grammar readers and voice/reading executors.
The request barrier includes GET handlers that populate caches and remains held
through streamed responses and background tasks. Health and handoff endpoints
stay available. Other new requests receive 503 with Retry-After while draining.

Executor draining waits for queued work and completion callbacks. Timed-out OCR
executors remain owned until their threads exit. A timed-out handoff returns 503
without cancelling its drain task; activation is rejected while cleanup is
pending or failed. A retry must observe a successful drain before activation
can reopen admission. The original capture-running state survives retries.

Exports, preparation helpers, grammar services and native folder dialogs use
retained process ownership. Windows joins a Job Object before launching the
real command. The process-tree owner outlives the immediate child, so a parent
exiting does not orphan its decoder. Failed cleanup keeps ownership and blocks
replacement. Linux/macOS use the shared watchdog implementation; native results
remain separate from Windows evidence.

Tests exercise queued cache completion, in-flight streamed requests, cancelled
capture-stop waiters, a timed-out handoff and activation retry, failed preparation
cleanup with preserved account selection, and real decoder descendants after
their parent exits. Host probes cover API crash/restart at the retained gateway
origin. These checks do not close the remaining frozen update, migration and
artifact acceptance work in [R19 C–F](r19-completion-plan.md).
