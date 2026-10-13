# Online companion development and deployment

The [public companion](https://firebird55.github.io/Game-immersion-toolkit/) keeps
its existing bookmark. Only checked `main` builds replace production. Task
branches validate and upload review artifacts; pushing a `codex/` branch cannot
replace the public site. A failed check keeps the prior deployment live.

1. Work on a `codex/` branch. Edit the React shell in `mobile/` and lifecycle
   modules in `public/mobile-capture/`. Run `node scripts/prepare-mobile-assets.mjs`
   to bundle the reader, then `npm run mobile:dev` to serve the local allowlist.
2. Run the compatibility watch, shared consumer checks, `npm run mobile:check`,
   `npm run check` and `npm run audit:public`. Commit each verified logical change.
3. Push the branch and inspect the **Online companion** review artifact and checks.
4. Deploy any gateway change first using `npm run gateway:deploy`; verify health,
   CORS, authorization failure handling and mocked account operations.
5. Merge verified changes into `main`. The Pages workflow gates publication on
   desktop checks, browser checks and the public-data audit. It publishes only
   generated static allowlisted assets, through GitHub Pages OIDC.
6. Monitor Actions and verify the public build commit. Release desktop integration
   from clean `main` through [the runbook](../RELEASE.md), then verify downloaded
   checksums and source provenance.

No personal data, game libraries, recordings or credentials may enter artifacts.
Do not add credentials to workflow secrets. The gateway and pairing service are
separate Workers; desktop services/data stay on the PC. No cluster is required.

Use [developer verification](online-companion-development.md) for architecture,
protocol, credential storage, test commands and physical-device limitations.
