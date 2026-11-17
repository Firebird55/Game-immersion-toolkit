# Bounded original-carrier streams

`PublisherTransport.consume_stream(url, consumer, limit=..., expected_size=...,
kind='asset', headers=..., digests=...)` lets an owned reader verify an entire
publisher carrier while retaining only a selected member. It returns the
consumer's result and a transport receipt only after size and requested digest
checks succeed. It creates no whole-carrier buffer, queue or worker.

The callback receives only `read(n)`. Each positive read is capped at 64 KiB,
checks the current source/account scope and spends the shared transfer budget.
Unbounded reads, premature return and use after the callback are rejected.
Bodies without Content-Length require observed EOF. Bytes already received
remain charged when cancellation occurs during a blocking read; no further
output may publish into that retired scope.

All normal HTTPS, allowlisted redirect, encoding, strong If-Match and size rules
also apply. Callbacks are packaged toolkit readers, never downloaded code.
They own provisional member cleanup after failure. A transport receipt alone
does not establish archive integrity, publisher signer trust or voice ownership.

The plan must disclose the complete carrier transfer and retained/scratch size.
If that carrier also contains unrelated media, text-only preparation must not
call it zero media transport. Optional voice acquisition remains a separate,
explicit choice. Authored streaming tests are not original-source or Android
acceptance evidence.
