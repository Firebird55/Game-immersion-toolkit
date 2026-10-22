import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

export const browserSuites = {
  desktop: ['browser-e2e'],
  setup: ['setup-e2e', 'language-account-e2e', 'ui-state-e2e', 'ui-state-react-e2e', 'setup-build-e2e', 'local-access-e2e'],
  capture: ['companion-e2e', 'mobile-reader-layout-e2e', 'mobile-capture-e2e', 'mobile-recovery-e2e'],
  offline: ['mobile-update-e2e'],
  ocr: ['mobile-library-e2e', 'mobile-layout-e2e', 'mobile-games-e2e', 'ocr-packs-e2e'],
};

export function runBrowserSuite(suite) {
  const scripts = suite === 'all' ? Object.values(browserSuites).flat() : browserSuites[suite];
  if (!scripts) throw new Error('Unknown browser suite: ' + suite);
  for (const script of scripts) {
    console.log('Browser check: ' + script);
    execFileSync(process.execPath, [`scripts/${script}.mjs`], {stdio: 'inherit'});
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) runBrowserSuite(process.argv[2]);
