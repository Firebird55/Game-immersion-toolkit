// Build-host-only: this file and the exact compiler archive are retained evidence.
const fs = require('node:fs');
const [compiler, input, output] = process.argv.slice(2);
if (!compiler || !input || !output || process.argv.length !== 5) throw Error('Pass compiler, source and output');
const ts = require(compiler);
if (ts.version !== '5.9.3') throw Error('Unexpected compiler version');
const source = fs.readFileSync(input, 'utf8');
const result = ts.transpileModule(source + '\nexport { unpackMhyFile };', {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
  reportDiagnostics: true,
});
if (result.diagnostics?.some(item => item.category === ts.DiagnosticCategory.Error)) throw Error('Reader transpilation failed');
let code = result.outputText;
for (const [name, relative] of [['ooz-wasm', '../dependencies/ooz/index.js'],
                              ['xxhash-wasm', '../dependencies/xxhash/esm/xxhash-wasm.js']]) {
  const pattern = new RegExp(`from (['"])${name}\\1`, 'g');
  if ([...code.matchAll(pattern)].length !== 1) throw Error('Unexpected reader imports');
  code = code.replace(pattern, `from '${relative}'`);
}
fs.writeFileSync(output, code, { flag: 'wx' });
