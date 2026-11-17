// Run explicitly in the OLD browser origin. Reads only two history keys;
// never opens a vault, OPFS library, stream link, localStorage or account API.
(() => {
  'use strict';
  const FORMAT = 'toolkit-browser-history-v1', MAX_ROWS = 12000, MAX_BYTES = 64 * 1024 ** 2;
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
  const fields = ['textId', 'english', 'chinese', 'sourceText', 'sourceLocale', 'sourceLanguage',
    'translationText', 'translationLocale', 'audioLocale', 'audioScope', 'voiceStatus',
    'textCaptureVerified', 'textTruncated', 'speakerEnglish', 'speakerChinese', 'matching', 'score', 'playerVoice'];
  function backup(history, pcHistory) {
    if (!Array.isArray(history) || !Array.isArray(pcHistory) || history.length + pcHistory.length > MAX_ROWS)
      throw Error('This history is incomplete or too large. Keep the original browser data.');
    const rows = [];
    for (const [source, values] of [['mobile-ocr', history], ['pc', pcHistory]]) for (const row of values) {
      if (!row || typeof row !== 'object' || Array.isArray(row)) throw Error('Invalid saved history row.');
      const projected = {source: source === 'pc' ? row.source : 'mobile-ocr', id: row.id,
        game: row.game, createdAt: row.createdAt, favorite: row.favorite === true,
        hadAudio: row.audio === true || typeof row.audio === 'string' && /^[0-9a-f]{64}$/.test(row.audio)
          || typeof row.sourceVoice === 'string' && /^[0-9a-f]{64}$/.test(row.sourceVoice)};
      if (typeof row.audio === 'string' && /^[0-9a-f]{64}$/.test(row.audio)) projected.audioSha256 = row.audio;
      for (const key of fields) if (own(row, key) && row[key] !== null && row[key] !== undefined)
        projected[key] = row[key];
      // Defaults are the original legacy browser's Chinese/English contract.
      if (!own(projected, 'english')) projected.english = '';
      if (!own(projected, 'chinese')) projected.chinese = '';
      rows.push(projected);
    }
    if (!rows.length) throw Error('No saved history was found in this browser origin. Nothing was changed.');
    const raw = JSON.stringify({format: FORMAT, rows});
    if (new TextEncoder().encode(raw).byteLength > MAX_BYTES)
      throw Error('History exceeds the migration size limit. Keep the original browser data.');
    return raw;
  }
  async function readHistory(indexedDB) {
    const database = await new Promise((resolve, reject) => {
      const request = indexedDB.open('proxy-mobile-library');
      request.onupgradeneeded = () => {request.transaction.abort(); reject(Error('No existing toolkit browser database was found.'));};
      request.onerror = () => reject(Error('The old browser database could not be opened. Nothing was changed.'));
      request.onblocked = () => reject(Error('Close other toolkit tabs, then retry.'));
      request.onsuccess = () => resolve(request.result);
    });
    try {
      if (!database.objectStoreNames.contains('state')) throw Error('The old toolkit history store is missing.');
      return await new Promise((resolve, reject) => {
        const transaction = database.transaction('state', 'readonly'), store = transaction.objectStore('state');
        const values = {};
        for (const key of ['history', 'pc-history']) {
          const request = store.get(key);
          request.onsuccess = () => {values[key] = request.result ?? [];};
        }
        transaction.oncomplete = () => {
          try {resolve(backup(values.history, values['pc-history']));} catch (error) {reject(error);}
        };
        transaction.onabort = transaction.onerror = () => reject(Error('History could not be read completely. Nothing was changed.'));
      });
    } finally {database.close();}
  }
  async function download() {
    const raw = await readHistory(window.indexedDB);
    const url = URL.createObjectURL(new Blob([raw], {type: 'application/json'}));
    const link = document.createElement('a');
    link.href = url; link.download = 'toolkit-browser-history.json';
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    window.alert('History and favorites exported. Keep the old browser data and voice libraries. Credentials and stream links were not exported.');
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = {backup, readHistory};
  else if (typeof window !== 'undefined') void download().catch(error => window.alert(error.message));
})();
