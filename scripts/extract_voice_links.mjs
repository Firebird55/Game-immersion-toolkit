// Read-only GalScript indexing using the separately downloaded upstream reader.
// Usage: node scripts/extract_voice_links.mjs GAME_DATA TOOL_DIR [scene-filter]
import { access, readFile, writeFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import ts from 'typescript';
import { sceneAssetPaths, sceneBundleRangesFromCatalog } from './scene-catalog.mjs';
import { comicVoicePairs, uniqueComicLinks } from './comic-links.mjs';

const [gameDataArg, toolsArg, filter = 'zenkov', outputName = 'scene-links.json'] = process.argv.slice(2);
if (!gameDataArg || !toolsArg) throw new Error('Pass GAME_DATA and TOOL_DIR');
const gameData = resolve(gameDataArg);
const toolDir = resolve(toolsArg);
if (toolDir.toLowerCase().startsWith(gameData.toLowerCase())) throw new Error('Tool directory must be outside the game');
const source = await readFile(join(toolDir, 'galgame-perform.ts'), 'utf8');
// Expose the pinned reader's unpacker to our owned comic-format adapter.
await writeFile(join(toolDir, 'galgame-perform.mjs'), ts.transpileModule(source + '\nexport { unpackMhyFile };', {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
}).outputText);
const { galGameBlockNamesFromCatalog, galGameLinksFromBlocks, unpackMhyFile, xxHash64 } =
  await import(pathToFileURL(join(toolDir, 'galgame-perform.mjs')).href);
const table = JSON.parse(await readFile(join(toolDir, 'PerformTemplateTb.json')));
const category = filter.toLowerCase() === 'comic' ? 'comic' : 'galgame';
const paths = sceneAssetPaths(table, category)
  .filter(path => ['galgame', 'comic'].includes(filter.toLowerCase()) || path.includes(filter.toLowerCase()));
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
const blocks = new Set(), ranges = new Map();
const unresolved = new Set(paths.map(path => xxHash64(path)));
for (const candidate of [...candidates].reverse()) {
  const path = await localFile(candidate);
  if (!path) continue;
  const bytes = await readFile(path);
  if (bytes[0] !== 31 || bytes[1] !== 139) continue;
  try {
    if (category === 'comic') {
      const resolved = sceneBundleRangesFromCatalog(bytes, unresolved);
      for (const hash of resolved.matchedHashes) unresolved.delete(hash);
      for (const range of resolved.ranges) {
        blocks.add(range.block);
        const selected = ranges.get(range.block) ?? new Map();
        selected.set(range.offset, range.size); ranges.set(range.block, selected);
      }
    } else {
      const resolved = galGameBlockNamesFromCatalog(bytes, paths);
      for (const block of resolved.blocks) blocks.add(block);
    }
  } catch { /* not a compatible resource catalog */ }
}
if (!blocks.size) throw new Error('No local catalog mapped these scenes');
const links = [];
for (const block of blocks) {
  const path = await localFile(block);
  if (!path) throw new Error(`Missing game block: ${block}`);
  const bytes = await readFile(path);
  if (category === 'comic') {
    for (const [offset, size] of ranges.get(block)) {
      if (!size || offset + size > bytes.length) throw new Error('Scene bundle exceeds installed block');
      const unpacked = unpackMhyFile(bytes, offset);
      if (unpacked.end !== offset + size) throw new Error('Scene bundle size changed during indexing');
      for (const cab of unpacked.files) links.push(...comicVoicePairs(cab));
    }
    continue;
  }
  const result = galGameLinksFromBlocks([bytes]);
  for (const [source, text_id] of result.links) {
    links.push({ source: result.sourceNames.get(source) ?? source, text_id });
  }
}
const verified = category === 'comic' ? uniqueComicLinks(links) : links;
if (!verified.length) throw new Error('No unambiguous text-to-voice links in matching scenes');
if (!/^[A-Za-z0-9_.-]+\.json$/.test(outputName)) throw new Error('Invalid output filename');
await writeFile(join(toolDir, outputName), JSON.stringify(verified, null, 2));
console.log(`Read ${blocks.size} game blocks; wrote ${verified.length} source links outside the game.`);
