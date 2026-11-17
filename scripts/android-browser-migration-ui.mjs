// Actual Android UI acceptance; only the exported authored fixture enters the app.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {authoredReceiverLibraryReady} from './android-runtime-diagnostics.mjs';

export const migrationRows = 22;

export function authoredBrowserHistoryBackup() {
  const context = {module: {exports: {}}, TextEncoder};
  vm.runInNewContext(readFileSync(new URL('./export-browser-history.js', import.meta.url), 'utf8'), context);
  const history = Array.from({length: 21}, (_, n) => ({id: 'native-authored-mobile-' + n,
    textId: 'zzz:authored:native-history:' + n, game: 'zzz', createdAt: 1794783739000 + n,
    favorite: n === 0, english: 'Preserved legacy history ' + n + '.', chinese: '保存された旧文章 ' + n + '。',
    sourceText: '保存された旧文章 ' + n + '。', sourceLocale: 'ja', sourceLanguage: 'ja',
    translationLocale: 'en', translationText: 'Preserved legacy history ' + n + '.', audioLocale: 'ja',
    textTruncated: n === 20, sourceVoice: '1'.repeat(64), rememberedKey: 'authored-private-vault-sentinel',
    viewerLink: 'authored-private-stream-sentinel'}));
  const pc = [{source: 'pc-1234567890abcdef', id: 1, game: 'zzz', createdAt: 1794783739999,
    favorite: false, english: 'Preserved desktop history.', chinese: '保留的电脑历史。', audio: true}];
  const raw = context.module.exports.backup(history, pc);
  assert.doesNotMatch(raw, /private-vault|private-stream|rememberedKey|viewerLink/);
  assert.equal(JSON.parse(raw).rows.length, migrationRows);
  return Buffer.from(raw);
}

const snapshot = page => page.evaluate(async () => (await fetch('/api/snapshot')).json());

async function importedTab(page) {
  if (!await page.getByRole('region', {name: 'Imported browser history', exact: true}).count())
    await page.getByRole('button', {name: 'Imported history', exact: true}).click();
  return page.getByRole('region', {name: 'Imported browser history', exact: true});
}

export async function verifyMigratedHistory(page, until, expectedTotal, nativeLineId) {
  await until(() => authoredReceiverLibraryReady(page), 'ordinary reader library scope after restart');
  await until(async () => (await snapshot(page)).status.session.total_line_count === expectedTotal, 'retained native browser-history count');
  const value = await snapshot(page), original = value.lines.find(line => line.id === nativeLineId);
  assert.equal(original?.favorite, true);assert.equal(original?.has_audio, true);
  const imported = value.lines.filter(line => line.match_kind === 'browser_migration');
  assert.equal(imported.length, migrationRows);
  assert.ok(imported.every(line => !line.has_audio && line.voice_status === 'unavailable'));
  const archive = await importedTab(page);
  await page.getByLabel('Imported favorites only', {exact: true}).check();
  await archive.getByText('保存された旧文章 0。', {exact: true}).waitFor();
  assert.equal(await archive.locator('.transcript-line').count(), 1);
  assert.equal(await archive.getByRole('button', {name: /Remove from favorites/}).count(), 1);
  assert.equal(await archive.getByText('0%', {exact: true}).count(), 0);
  return value;
}

export async function importBrowserHistoryThroughUi(page, until, nativeLineId, selectBackup = null) {
  await until(() => authoredReceiverLibraryReady(page), 'ordinary reader library scope before migration');
  const baseline = await snapshot(page), total = baseline.status.session.total_line_count + migrationRows;
  const file = {name: 'authored-browser-history.json', mimeType: 'application/json', buffer: authoredBrowserHistoryBackup()};
  const openMigration = async () => {
    await page.getByRole('button', {name: 'Settings', exact: true}).click();
    await page.getByText('Previous browser history', {exact: true}).click();
    await page.getByText('Import old browser history', {exact: true}).click();
  };
  const closeMigration = async () => {
    await page.getByRole('dialog', {name: 'Zenless Zone Zero settings', exact: true})
      .getByRole('button', {name: 'Close', exact: true}).click();
  };
  await openMigration();
  if (selectBackup) await selectBackup(file.buffer);
  else await page.getByLabel('Browser history backup', {exact: true}).setInputFiles(file);
  await page.getByText('22 lines · 1 favorites · 1 excerpts.', {exact: false}).waitFor();
  assert.deepEqual((await snapshot(page)).lines, baseline.lines, 'Preview must preserve existing native rows');
  assert.equal((await snapshot(page)).status.session.total_line_count, total - migrationRows);
  await page.getByRole('button', {name: 'Import history and favorites', exact: true}).click();
  await page.getByText('History imported: 22 new lines, 0 already imported. Original browser data is unchanged.', {exact: true}).waitFor();
  await closeMigration();
  const archive = await importedTab(page);
  await archive.getByText('保留的电脑历史。', {exact: true}).waitFor();
  await archive.getByText('Imported browser excerpt', {exact: true}).waitFor();
  await page.getByRole('button', {name: 'Previous 10', exact: true}).click();
  await archive.getByText('保存された旧文章 11。', {exact: true}).waitFor();
  await verifyMigratedHistory(page, until, total, nativeLineId);
  await openMigration();
  await page.getByLabel('Browser history backup', {exact: true}).setInputFiles(file);
  await page.getByRole('button', {name: 'Import history and favorites', exact: true}).click();
  await page.getByText('History imported: 0 new lines, 22 already imported. Original browser data is unchanged.', {exact: true}).waitFor();
  await closeMigration();
  await verifyMigratedHistory(page, until, total, nativeLineId);
  return total;
}
