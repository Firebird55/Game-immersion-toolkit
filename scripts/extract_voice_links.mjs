// Read-only GalScript indexing using the separately downloaded upstream reader.
// Usage: node scripts/extract_voice_links.mjs GAME_DATA TOOL_DIR [scene-filter]
import { access, readFile, writeFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import ts from 'typescript';

const [gameDataArg, toolsArg, filter = 'zenkov'] = process.argv.slice(2);
if (!gameDataArg || !toolsArg) throw new Error('Pass GAME_DATA and TOOL_DIR');
const gameData = resolve(gameDataArg);
const toolDir = resolve(toolsArg);
if (toolDir.toLowerCase().startsWith(gameData.toLowerCase())) throw new Error('Tool directory must be outside the game');
const source = await readFile(join(toolDir, 'galgame-perform.ts'), 'utf8');
await writeFile(join(toolDir, 'galgame-perform.mjs'), ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
}).outputText);
const { galGamePerformAssetPaths, galGameBlockNamesFromCatalog, galGameLinksFromBlocks } =
  await import(pathToFileURL(join(toolDir, 'galgame-perform.mjs')).href);
const paths = galGamePerformAssetPaths(JSON.parse(await readFile(join(toolDir, 'PerformTemplateTb.json'))))
  .filter(path => path.includes(filter.toLowerCase()));
if (!paths.length) throw new Error('No matching scene paths');
async function localFile(name) {
  for (const directory of ['Persistent', 'StreamingAssets']) {
    const path = join(gameData, directory, name);
    try { await access(path); return path; } catch { /* absent in this layer */ }
  }
}
const candidates = new Set();
for (const [directory, versionFile] of [['StreamingAssets', 'res_version'], ['Persistent', 'res_version_persist']]) {
  const version = JSON.parse(await readFile(join(gameData, directory, versionFile)));
  for (const entry of version.files ?? []) {
    if (/^Blocks\/\d+\.blk$/.test(entry.remoteName) && !entry.tags?.length) candidates.add(entry.remoteName);
  }
}
const blocks = new Set();
for (const candidate of candidates) {
  const path = await localFile(candidate);
  if (!path) continue;
  const bytes = await readFile(path);
  if (bytes[0] !== 31 || bytes[1] !== 139) continue;
  try {
    const resolved = galGameBlockNamesFromCatalog(bytes, paths);
    for (const block of resolved.blocks) blocks.add(block);
  } catch { /* not a compatible resource catalog */ }
}
if (!blocks.size) throw new Error('No local catalog mapped these scenes');
const links = [];
for (const block of blocks) {
  const path = await localFile(block);
  if (!path) throw new Error(`Missing game block: ${block}`);
  const result = galGameLinksFromBlocks([await readFile(path)]);
  for (const [source, text_id] of result.links) {
    links.push({ source: result.sourceNames.get(source) ?? source, text_id });
  }
}
await writeFile(join(toolDir, 'scene-links.json'), JSON.stringify(links, null, 2));
console.log(`Read ${blocks.size} game blocks; wrote ${links.length} source links outside the game.`);
