import {execFileSync} from 'node:child_process';
import {resolvePython} from './python-runtime.mjs';
const {command: python} = resolvePython();
// Export interoperability tests import the same generated OCR modules as the reader.
execFileSync(process.execPath,['scripts/prepare-mobile-assets.mjs'],{stdio:'inherit'});
execFileSync(python,['-m','pytest','backend/tests','tests','-q'],{stdio:'inherit',env:{...process.env,PROXY_TRANSCRIPT_PROJECT_ROOT:process.cwd()}});
