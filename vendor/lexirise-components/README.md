# Lexirise shared components

Private shared React/TypeScript package for Emulingo Lexirise userscript and Game immersion toolkit.

Exports: `SettingsPanel`, `createReader` (reader and identical LookupWindow), `createLexiriseClient`, account PATCH helpers, scoped CSS, types and versioned 31-language capabilities.
React is a peer dependency. Each host owns credential storage, transport, popup portal and local preferences. No credential belongs in this repository.

`npm ci && npm run check`
See [release runbook](RELEASE.md). Published package copies in sibling applications are generated; edit this repository, never a consumer's vendor directory.

Account settings are read when the panel opens or reconnects. Local display settings apply immediately. Only Save to Lexirise writes remote settings. Read-only fields are excluded; unrelated language settings remain unchanged.
Capability data was reviewed against [Lexirise API reference](https://lexirise.app/api-reference) and public language options on 2026-10-09.
