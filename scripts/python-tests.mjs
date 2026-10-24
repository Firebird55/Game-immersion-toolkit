
import {execFileSync} from 'node:child_process';import {existsSync} from 'node:fs';import {join} from 'node:path';
const local=process.env.LOCALAPPDATA?join(process.env.LOCALAPPDATA,'Programs','Proxy Transcript','venv','Scripts','python.exe'):'';
const python=process.env.PYTHON|| (existsSync(local)?local:'python');
// Export interoperability tests import the same generated OCR modules as the reader.
execFileSync(process.execPath,['scripts/prepare-mobile-assets.mjs'],{stdio:'inherit'});
execFileSync(python,['-m','pytest','backend/tests','tests','-q'],{stdio:'inherit',env:{...process.env,PROXY_TRANSCRIPT_PROJECT_ROOT:process.cwd()}});
