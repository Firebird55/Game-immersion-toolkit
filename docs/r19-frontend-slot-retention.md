# R19 experimental immutable frontend retention

`DesktopFrontendServer.from_experimental_slots` is an in-process experiment
adapter for the existing closed-manifest static server. It binds only an
OS-selected private loopback port. It preserves old hashed Vite `assets/*` and
supported Next `/_next/static/*` resources across a fixed current/retired
frontend snapshot, without a second router or runtime dependency.

This adapter does not select an active runtime, migrate data, start capture,
transfer a lease, claim browser continuity or enable production activation.
The source `companion-router.mjs` and its Next asset-copy behavior are unchanged.
The frozen frontend CLI still rejects `--retained-root`; no CLI flag, HTTP
endpoint, route JSON field or production child target enables this adapter.

## Owner prerequisite and verified subset

The caller supplies the current `RuntimeLayout` and a **trusted SHA-256 of that
slot's runtime manifest**, plus at most sixteen retired `(RuntimeLayout, SHA-256)`
pairs. Only `bundle` layouts with `frontend-experiment` or `runtime-experiment`
profiles are accepted. A production `runtime` layout and a dictionary containing
paths are refused. The factory cannot choose a public/canonical port.

The trusted hash must come from independently verified complete immutable-slot
provenance controlled by the owner. Reading a target JSON file and hashing that
same untrusted file cannot establish this prerequisite. The adapter validates
the **frontend subset only**: complete application inventory/provenance,
executable/native-library eligibility, rights, live process ownership and the
keeper's lease lifetime remain separate owner requirements. The hash argument
is content binding, not an authorization flag or a replacement for those checks.

Before opening a listener, each selected slot must satisfy:

- The bounded, regular runtime manifest has the supplied hash and no duplicate
  JSON keys. Its schema, profile, version, source commit, build identity,
  children and resource map match the selected layout.
- The closed `desktop/desktop-manifest.json` matches the runtime resource hash.
  Its complete file set, individual hashes, sizes, MIME types, frontend identity
  and source/version match the pinned runtime resource subset. Unknown files or
  directories, unsafe names, links and reparse points are refused.
- Current and retired immutable URL names cannot disagree in bytes/size/MIME.
  Different Windows case spellings are refused across retained builds as well.
  The bound includes all retired builds before any socket is created.

The server reuses `FrontendBuild`, `DesktopFrontendHandler`, the existing local
Host/Origin checks and the existing immutable-path allowlist. It introduces no
filesystem root authority from a browser or serialized route state. The ordinary
source constructor still supports its existing explicit built-root contract.

Runtime and desktop manifest pins are verified at construction. They are not
continuously rehashed or watched. Replacing a manifest afterward cannot change
the captured resource map or grant access to a new file; unchanged, previously
bound public resources can still be served. A future owner must recheck complete
slot eligibility before another activation rather than treat this running
frontend as proof that every manifest and native file remains unchanged.

## HTTP behavior

The current build supplies `/`, mutable mobile resources and notices. Only
supported hashed immutable paths may fall back to a retired build; an old
`index.html`, mutable worker or unknown path cannot be resurrected. GET, HEAD,
ETag/304, MIME, CSP and cache behavior use the same handler as the current static
frontend. Traversal, Windows aliases, private resources and mutating methods
retain their existing refusal behavior.

Every served resource is read and checked against its pinned bytes. If an old
chunk changes, disappears or becomes a symlink after startup, its request fails
with 503 instead of serving altered bytes. Current/retired file selections are
fixed for this server lifetime; this is not an atomic route-swap API or a
retention garbage collector. Read-only attributes/ACLs and complete native slot
immutability are not established by these frontend request checks.

## Evidence and remaining gates

The authored regression fixtures construct independent current/retired runtime
and frontend manifests. They exercise real loopback HTTP for old Vite and Next
chunks, GET/HEAD/304, current-index selection, mutable/unknown-path refusal and
post-start corruption/link refusal. Negative trust, profile, inventory and
cross-slot collision cases must fail before a listener opens. Source Next
router tests remain a separate regression check.

These fixtures contain no real executable, account, game file, model or live
store. They cannot prove frozen/native execution, a real browser retaining a
lazy chunk through an actual update, warm private-port routing, reconnect/profile
continuity or a complete version/schema rollback. Those still require the exact
frozen artifact, verified owner/keeper boundary, applicable browser matrix and
native Windows acceptance. Production execution, rights approval, source delivery,
store-copy capability and full R19 completion remain unavailable. No installer
is built by this change.
