# Desktop target acceptance

Native installer eligibility and completion of the full R19 all-game plan are
separate claims. A distributable platform may truthfully retain
`r19_complete: false`; it must have a verified exact input/notice/source closure
and successful actual frozen-host evidence for that target. Signing is reported
explicitly; an unsigned build is not silently described as signed or notarized.

Build with `scripts/build-desktop-runtime.py` (default profile `runtime`). The
builder writes an unapproved `CANDIDATE-PROVENANCE.json`. Do not change any payload
byte after testing. The promotion command writes a separate accepted receipt:

```text
python scripts/accept-desktop-runtime.py --runtime-root <frozen-tree>
  --provenance <CANDIDATE-PROVENANCE.json> --target <target>
  --input-review <exact-input-review.json>
  --native-report <frozen-host-report.json>
  --native-report <visible-native-ui-report.json>
  --output <ACCEPTED-PROVENANCE.json>
```

Every evidence object binds `source_commit`, `build_id`, `target` and
`runtime_receipt_sha256` (the original candidate receipt's SHA-256). Synthetic
unit-test evidence exercises rejection behavior only; it is never native release
evidence. Windows, Linux and macOS require independent actual native runs.

The input review has schema `toolkit-desktop-input-review-v1`, `approved: true`,
and `file_inventory_sha256`, calculated from the candidate's files and directories
using `inventory_digest` in the acceptance script. Its boolean checks must cover
`python_supplier`, `exact_wheels`, `native_inputs`, `complete_notices`,
`corresponding_sources` and `frontend_licenses`. Approval follows inspection of
those exact inputs, retained full notices and applicable source/build obligations;
metadata labels or an operator changing booleans are not that inspection.

`capabilities` is a nonempty mapping from capability names to `available`,
`unavailable`, `requires-installed-pack` or `host-permission`. Capture backends,
codecs and optional game dependencies must be described as they actually exist in
that target. A missing installed voice pack does not become an unvoiced line.

Native reports have schema `toolkit-desktop-native-probe-v1` or
`toolkit-desktop-ui-probe-v1`, `execution: actual-frozen-process`, `passed: true`
and boolean `checks`. Across the reports, every required check must pass:
`host_check`, `frontend_gateway`, `api_crash_recovery`, `owned_shutdown`,
`browser_open`, `status_window` and `tray_icon`. A reported failed or unavailable
required check rejects promotion even if another report claims it passed.
Headless/offscreen runners cannot claim visible tray or browser observations.

Promotion validates the complete runtime before and after evidence review and
writes only the external acceptance receipt. The accepted receipt preserves the
same files, directories, embedded identity and R19 completion state. It records
its input review and native report hashes, target, explicit capabilities and
unsigned status. Public packaging uses that receipt without `--candidate`.
Candidate packaging remains available for private installer tests.

Immutable desktop updates verify the accepted release metadata, exact inventory,
source tag, resource/frontend identities and supported storage/host epochs before
starting a new child. They never infer release eligibility from `r19_complete`.
