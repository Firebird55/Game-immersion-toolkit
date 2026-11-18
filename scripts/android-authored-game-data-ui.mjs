// Generated DEBUG source only. The ordinary UI and game-data service own all
// planning, preparation, activation and restoration; no ZIP is imported.
import assert from 'node:assert/strict';
import {authoredReceiverLibraryReady} from './android-runtime-diagnostics.mjs';

export async function prepareAuthoredGameData(page, until, {bothModes = false} = {}) {
 const platform = await page.evaluate(async () => (await fetch('/api/platform')).json());
 assert.equal(platform.platform, 'android');
 assert.equal(platform.authored_game_data_fixture, true, 'Never substitute authored data into a production source registry');
 assert.equal(await page.getByLabel('Private toolkit library', {exact: true}).count(), 0);
 assert.equal(await page.getByRole('button', {name: 'Open library', exact: true}).count(), 0);
 assert.equal(await page.getByRole('combobox', {name: 'Reading', exact: true}).count(), 0);
 assert.equal(await page.getByRole('button', {name: 'Stop screen', exact: true}).count(), 0);
 const state = () => page.evaluate(async () => {
  const snapshot = await (await fetch('/api/snapshot')).json();
  const response = await fetch('/api/game-data', {headers: {
   'X-Toolkit-Account-Generation': String(snapshot.context.account_generation), 'X-Proxy-Transcript': 'setup'}});
  if (!response.ok) return null;
  const value = await response.json();
  return value.games.find(row => row.id === 'zzz');
 });
 await page.getByRole('button', {name: 'Settings', exact: true}).click();
 const settings = page.getByRole('dialog', {name: 'Zenless Zone Zero settings', exact: true});
 await settings.waitFor();
 const content = settings.getByRole('combobox', {name: 'Game data content', exact: true});
 assert.equal(await content.inputValue(), 'text', 'Text only is the initial download choice');
 await settings.getByRole('combobox', {name: 'Voice and source language', exact: true}).selectOption('en');
 await settings.getByRole('combobox', {name: 'Game data region', exact: true}).selectOption('global');
 let downloaded;
 for (const mode of bothModes ? ['text', 'text-audio'] : ['text-audio']) {
  await content.selectOption(mode);
  const download = settings.getByRole('button', {name: 'Download', exact: true});
  await until(() => download.isEnabled(), 'authored download button');
  await download.click();
  downloaded = await until(async () => {
   const row = await state();
   if (row?.job?.status === 'failed') throw Error('Authored direct game preparation failed');
   return row?.state === 'ready' && row.job?.status === 'complete' && row.installed_request?.content_mode === mode ? row : null;
  }, `authored ${mode} direct preparation`);
  assert.ok(downloaded.installed_bytes > 0);
  assert.equal(downloaded.job.total_bytes, downloaded.job.downloaded_bytes);
  assert.equal(downloaded.installed_request.source_locale, 'en');
 }
 await settings.getByRole('button', {name: 'Close', exact: true}).click();
 await settings.waitFor({state: 'hidden'});
 await until(() => authoredReceiverLibraryReady(page),
  'direct-source React receiver activation');
 return downloaded;
}
