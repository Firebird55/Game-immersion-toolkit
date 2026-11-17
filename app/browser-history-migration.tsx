'use client';
import {useEffect, useRef, useState} from 'react';
import {Button} from '../components/ui/button';
import {desktopApiBase} from '../lib/desktop-endpoints';
import {useNativeAccountGeneration} from '../lib/native-account-context';
import {nativeAccountHeaders} from '../lib/native-account-scope.mjs';
import browserHistoryExporter from '../scripts/export-browser-history.js?raw';

// JavaScript URL navigation decodes the whole URL before parsing its program.
// Encode the program once, preserving comments/newlines without string eval.
const exportBookmark = 'javascript:' + encodeURIComponent('void function () {\n' + browserHistoryExporter + '\n}()');

type Preview = {rows: number; favorites: number; excerpts: number; games: string[]; study_locales: string[]};
function previewReply(value: unknown): Preview {
  if (!value || typeof value !== 'object') throw Error('History preview is unavailable.');
  const row = value as Preview & {audio_included?: boolean};
  if (!Number.isInteger(row.rows) || row.rows < 1 || row.rows > 12000
      || !Number.isInteger(row.favorites) || row.favorites < 0 || row.favorites > row.rows
      || !Number.isInteger(row.excerpts) || row.excerpts < 0 || row.excerpts > row.rows
      || row.audio_included !== false
      || ![row.games, row.study_locales].every(list => Array.isArray(list) && list.length <= 100
        && list.every(text => typeof text === 'string' && /^[A-Za-z][A-Za-z0-9-]{0,63}$/.test(text))))
    throw Error('History preview is unavailable.');
  return row;
}

export function BrowserHistoryMigration({onChanged}: {onChanged: () => void}) {
  const accountGeneration = useNativeAccountGeneration();
  const owner = useRef(accountGeneration); owner.current = accountGeneration;
  const pending = useRef<AbortController | null>(null);
  const file = useRef<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  useEffect(() => () => {pending.current?.abort(); pending.current = null; file.current = null;}, [accountGeneration]);
  const transfer = async (selected: File, commit: boolean) => {
    if (selected.size < 1 || selected.size > 64 * 1024 ** 2) {
      setMessage('Choose a complete history backup smaller than 64 MiB.'); return;
    }
    pending.current?.abort();
    const controller = new AbortController(), captured = accountGeneration;
    pending.current = controller;setBusy(true);setMessage('');
    if (!commit) {file.current = null;setPreview(null);}
    try {
      const response = await fetch(desktopApiBase() + '/api/history/migration/' + (commit ? 'import' : 'preview'), {
        method: 'POST', body: selected, signal: controller.signal,
        headers: nativeAccountHeaders(captured, {'Content-Type': 'application/json', 'X-Proxy-Transcript': 'setup'}),
      });
      const value: unknown = await response.json();
      const details = value && typeof value === 'object' ? value as Record<string, unknown> : {};
      if (!response.ok) throw Error(typeof details.detail === 'string' ? details.detail : 'The history transfer could not be confirmed.');
      const result = previewReply(value);
      if (pending.current !== controller || owner.current !== captured) return;
      if (commit) {
        for (const key of ['imported', 'already_imported', 'favorites_promoted']) {
          const count = details[key];
          if (typeof count !== 'number' || !Number.isInteger(count) || count < 0 || count > result.rows)
            throw Error('The history import could not be confirmed. Check history before retrying.');
        }
        if ((details.imported as number) + (details.already_imported as number) !== result.rows)
          throw Error('The history import could not be confirmed. Check history before retrying.');
        file.current = null;setPreview(null);
        setMessage(`History imported: ${details.imported} new lines, ${details.already_imported} already imported. Original browser data is unchanged.`);
        onChanged();
      } else {file.current = selected;setPreview(result);}
    } catch (failure) {
      if (pending.current === controller && owner.current === captured && !controller.signal.aborted)
        setMessage(failure instanceof Error ? failure.message : 'History transfer failed. Keep the original backup.');
    } finally {
      if (pending.current === controller && owner.current === captured) {pending.current = null;setBusy(false);}
    }
  };
  return <details className="toolkit-export-help">
    <summary>Import old browser history</summary>
    <p>Use the history-only JSON export from the old toolkit browser. This adds history and favorites on this device. If you use accounts, select the right one first. Keep the original browser data.</p>
    <p>Voice files, account keys and private stream links are not included. Re-import a prepared library for future capture and playback. Reading preferences and screen calibration are configured separately in this app.</p>
    <details><summary>Export from the old browser</summary>
      <p>On the old device, keep the old toolkit browser data. In a browser that supports JavaScript bookmarks, save a bookmark and replace its address with the complete code below. Open the original toolkit address in that same browser, then run the bookmark to save the history JSON. A normal 404 page at the original address can still retain its browser storage.</p>
      <p>This reads only local history and favorites. It does not send data to a server or unlock credentials. Mobile bookmark execution still needs device verification; keep the original data if your browser blocks it.</p>
      <label>Old browser history export bookmark<textarea readOnly aria-label="Old browser history export bookmark"
        value={exportBookmark} rows={3} style={{width:'100%',overflowWrap:'anywhere'}} /></label>
    </details>
    <label>Browser history backup <input type="file" accept=".json,application/json" disabled={busy}
      aria-label="Browser history backup" onChange={event => {
        const selected = event.currentTarget.files?.[0];event.currentTarget.value = '';
        if (selected) void transfer(selected, false);
      }} /></label>
    {preview && <div><p>{preview.rows} lines · {preview.favorites} favorites · {preview.excerpts} excerpts. Games: {preview.games.join(', ')}. Study languages: {preview.study_locales.join(', ')}.</p>
      <Button disabled={busy} onClick={() => {if (file.current) void transfer(file.current, true);}}>Import history and favorites</Button></div>}
    {busy && <Button variant="outline" onClick={() => {
      pending.current?.abort();pending.current = null;setBusy(false);setMessage('Transfer stopped. Check history before retrying; importing the same backup does not duplicate lines.');onChanged();
    }}>Stop transfer</Button>}
    {message && <p role="status">{message}</p>}
  </details>;
}
