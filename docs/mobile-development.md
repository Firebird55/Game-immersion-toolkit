# Develop on Windows, test on iPad

The repository is public. GitHub Pages hosts only the mobile capture page at
[the stable iPad preview bookmark](https://firebird55.github.io/Game-immersion-toolkit/).
Game frames use direct WebRTC between your devices; catalog data, reports, game
files, the Windows backend and credentials are not published. No deployment key
is added to workflow secrets: Pages uses the job's built-in GitHub token and OIDC.

## Daily cycle

1. Edit `public/mobile-capture` on this PC, on a `codex/` task branch.
   Run `npm run mobile:dev` and open `http://127.0.0.1:8444/` for a local browser
   preview. Reload after editing; this reads the source directly and does not
   require a frontend rebuild or stopping the desktop companion.
2. Use `npm run mobile:check` for quick pairing and browser checks while editing.
   Before pushing, run the repository checks required by AGENTS.md: `npm run check`
   and `npm run audit:public`. Stop the companion before the production
   build and restore it afterward as described in RELEASE.md.
3. Commit the logical change and `git push -u origin HEAD` (subsequent pushes can
   use `git push`).
4. Watch **Mobile preview** in GitHub Actions. It checks and publishes the browser
   page independently of **Checks and release**, so the preview does not wait for
   Python installation, game indexes, the desktop build or release packaging.
5. Open the deployment URL from the Actions run summary on iPad and phone. Bookmark
   it once. Tap **Reload latest** on both devices before pairing, then confirm
   that the displayed branch and commit match the push you want to test.
6. Pair and test. Downloaded capture reports include the loaded commit and branch
   so device results can be traced back to the code.

For an immediate test use the PC as **Share screen** and iPad as **Receive screen**;
follow [pairing and observation instructions](mobile-capture.md). The page tests
frame delivery only, without OCR or transcripts. Its capability check makes
unsupported sender browsers explicit; adding a Home Screen shortcut cannot
provide an unavailable screen-capture API.

Pushes to `main` and `codex/**` deploy when mobile files or preview tooling change.
The single bookmark shows the latest successful mobile deployment from any of
those branches. Newer pushes cancel pending preview runs. A failed preview keeps
the prior deployment live. Changing only desktop code does not redeploy the page.
Each preview uses content-hashed JS/CSS files to avoid mixing cached asset versions.
The full desktop CI remains independent and still needs to pass before a release.

`npm run mobile:build` creates a private local package under ignored `output/`.
The publisher copies only its six allowlisted files. Local builds identify the
last commit; uncommitted edits are not a deployed version. The GitHub-generated
package always comes from the run's checked-out commit.

## Hosting setup

The repo's Pages publishing source must be **GitHub Actions**, with HTTPS enabled.
The `github-pages` environment must allow `main` and `codex/**` branches to deploy.
Both the toolkit and shared source are public after the publication audit. Set repository variable `MOBILE_PREVIEW_ENABLED` to `true` once Pages is configured. The workflow then deploys without a private-repository hosting plan or a deployment credential.

The mobile page is public by choice. Its report and pairing messages stay on the
devices. Transfer pairing descriptions privately and use the same Wi-Fi without
client isolation. The page still does not establish that iPad background screen
capture works: follow the device test in `mobile-capture.md` before adding OCR.
