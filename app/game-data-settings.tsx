'use client';
import {useEffect, useRef, useState, type ReactNode} from 'react';
import {Button} from '../components/ui/button';
import {Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription} from '../components/ui/dialog';
import {desktopApiBase} from '../lib/desktop-endpoints';
import {useNativeAccountGeneration} from '../lib/native-account-context';
import {nativeAccountHeaders} from '../lib/native-account-scope.mjs';
import {validateGameDataList, validateGameDataRow, formatGameBytes, canDownloadGame} from '../lib/game-data-client.mjs';
import catalog from '../public/mobile-capture/games-data.json';
import {languageName} from '../public/mobile-capture/interface-language.mjs';
import './game-data-settings.css';

export type GameDataRow = {id: string; title: string; state: string; revision: string | null; installed_revision: string | null; can_activate: boolean; region: string; content_mode: 'text' | 'text-audio';
 installed_request?: null | {region:string; source_locale:string; target_locales:string[]; content_mode:'text'|'text-audio'};
 source_locale: string; target_locales: string[]; installed_bytes: number; deletable_bytes: number; retained_bytes: number;
 download_bytes: number | null; download_is_upper_bound: boolean; required_disk_bytes: number | null; plan_id: string | null;
 job: null | {id: string; status: string; phase: string; downloaded_bytes: number; total_bytes: number | null; message: string};
 can_plan: boolean; can_download: boolean; can_delete: boolean; message: string};

export function GameDataSettings({game, targetLanguage, online, account, onChanged, onGames, children, buttonLabel = 'Settings', pollClosed = true}: {
 game: string; targetLanguage: string; online: boolean; account: string; onChanged: () => void;
 onGames?: (rows: GameDataRow[]) => void;
 children?: ReactNode;
 buttonLabel?: string;
 pollClosed?: boolean;
}) {
 const generation = useNativeAccountGeneration();
 const [open, setOpen] = useState(false), [rows, setRows] = useState<GameDataRow[]>([]);
 const [error, setError] = useState(''), [pending, setPending] = useState(false), [confirmDelete, setConfirmDelete] = useState(false);
 const [region, setRegion] = useState('global'), [source, setSource] = useState(''), [targets, setTargets] = useState<string[]>([]);
 const [contentMode, setContentMode] = useState<'text' | 'text-audio'>('text');
 const requests = useRef(new Set<AbortController>()), epoch = useRef(0), live = useRef(true);
 const mutationPending = useRef(false);
 const callbacks = useRef({onChanged, onGames}); callbacks.current = {onChanged, onGames};
 const row = rows.find(value => value.id === game);
 const info = catalog.games.find(value => value.id === game);
 const sourceChoices = [...new Set([...(info?.audio ?? []), ...(row?.source_locale ? [row.source_locale] : [])])];
 const targetChoices = [...new Set([...(info?.targets ?? []), ...(row?.target_locales ?? [])])];

 useEffect(() => {live.current = true; return () => {live.current = false; epoch.current++; for (const controller of requests.current) controller.abort();};}, []);
 useEffect(() => {
  setConfirmDelete(false);
  if (!row) return;
  setRegion(row.region || 'global');
  setContentMode(row.content_mode);
  setSource(row.source_locale || sourceChoices.find(value => value.split('-')[0] === targetLanguage) || sourceChoices[0] || 'en');
  setTargets(row.target_locales.length ? row.target_locales : targetChoices.filter(value => value === 'en'));
  // Polling a job must not replace language edits in progress.
  // eslint-disable-next-line react-hooks/exhaustive-deps
 }, [game, row?.id]);

 async function request(path = '', method = 'GET', body?: unknown) {
  const controller = new AbortController(); requests.current.add(controller);
  try {
   const response = await fetch(desktopApiBase() + '/api/game-data' + path, {method, cache: 'no-store', signal: controller.signal,
    headers: nativeAccountHeaders(generation, {'Content-Type': 'application/json', 'X-Proxy-Transcript': 'setup', 'X-Proxy-Transcript-Account': account}),
    ...(body === undefined ? {} : {body: JSON.stringify(body)})});
   const raw = await response.json();
   if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw Error('Game data response is unavailable. Refresh Settings.');
   const value = raw as Record<string, unknown>;
   if (!response.ok) throw Error(typeof value?.detail === 'string' && value.detail.length <= 1000 ? value.detail : 'Game data operation could not be confirmed. Refresh Settings.');
   return value;
  } finally {requests.current.delete(controller);}
 }

 useEffect(() => {
  if (!online || generation === null || !open && !pollClosed) return;
  let current = true, timer: ReturnType<typeof setTimeout>;
  const refresh = async () => {
   if (mutationPending.current) {if (current) timer = setTimeout(refresh, 1500); return;}
   const owner = epoch.current;
   try {
    const value = validateGameDataList(await request());
    if (current && live.current && owner === epoch.current) {
     setRows(value.games); setError(''); callbacks.current.onGames?.(value.games);
    }
   } catch {if (current && live.current && owner === epoch.current) setError('Game data information is unavailable. Retry in Settings.');}
   if (current) timer = setTimeout(refresh, open ? 1500 : 10000);
  };
  void refresh(); return () => {current = false; clearTimeout(timer);};
  // Requests belong to this immutable account-generation component.
  // eslint-disable-next-line react-hooks/exhaustive-deps
 }, [online, generation, open, pollClosed]);

 async function mutate(action: 'plan' | 'download' | 'delete' | 'activate') {
  if (!row || mutationPending.current) return;
  const owner = ++epoch.current; mutationPending.current = true; setPending(true); setError('');
  try {
   const selection = {region, source_locale: source, target_locales: targets, content_mode: contentMode};
   const value = await request(`/${encodeURIComponent(game)}/${action === 'delete' ? 'data' : action}`, action === 'delete' ? 'DELETE' : 'POST',
    action === 'plan' ? selection : action === 'download' ? {plan_id: row.plan_id, revision: row.revision}
      : {revision: action === 'activate' ? row.installed_revision : row.revision});
   const updated = validateGameDataRow(value.game) as GameDataRow;
   if (updated.id !== game) throw Error('Game changed. Refresh Settings.');
   if (!live.current || owner !== epoch.current) return;
   setRows(current => current.map(item => item.id === game ? updated : item)); setConfirmDelete(false);
   callbacks.current.onChanged();
  } catch (failure) {
   if (live.current && owner === epoch.current) setError(failure instanceof Error ? failure.message : 'Game data operation could not be confirmed. Refresh Settings.');
  } finally {if (live.current && owner === epoch.current) {mutationPending.current = false; setPending(false);}}
 }

 const selection = {region, source_locale: source, target_locales: targets, content_mode: contentMode};
 const busy = pending || row?.state === 'downloading' || row?.state === 'planning';
 const needsNextQuote = row?.job?.status === 'needs_plan';
 return <>
  <Button variant="outline" onClick={() => setOpen(true)}>{buttonLabel}</Button>
  <Dialog open={open} onOpenChange={setOpen}><DialogContent className="setup-dialog game-data-settings"><DialogHeader>
   <DialogTitle>{row?.title || info?.name || game} settings</DialogTitle>
   <DialogDescription>Choose text only or text with the available original audio, then check the download size.</DialogDescription>
  </DialogHeader>
  {row ? <>
   <label>Game data<select aria-label="Game data content" value={contentMode} disabled={busy} onChange={event => setContentMode(event.target.value as 'text' | 'text-audio')}>
    <option value="text">Text only</option><option value="text-audio">Text + audio</option>
   </select></label>
   <label>Region<select aria-label="Game data region" value={region} disabled={busy} onChange={event => setRegion(event.target.value)}>
    <option value="global">Global</option><option value="cn">Mainland China</option>
   </select></label>
   <label>Voice and source language<select aria-label="Voice and source language" value={source} disabled={busy} onChange={event => setSource(event.target.value)}>
    {sourceChoices.map(code => <option key={code} value={code}>{languageName(code, 'en')}</option>)}
   </select></label>
   <fieldset><legend>Translations</legend>{targetChoices.filter(code => code !== source).map(code => <label key={code}>
    <input type="checkbox" disabled={busy} checked={targets.includes(code)} onChange={event => setTargets(previous => event.target.checked ? [...previous, code] : previous.filter(value => value !== code))}/>{languageName(code, 'en')}
   </label>)}</fieldset>
   <dl><dt>Downloaded data</dt><dd>{formatGameBytes(row.installed_bytes)}</dd>
    {row.installed_request && <><dt>Downloaded contents</dt><dd>{row.installed_request.content_mode === 'text-audio' ? 'Text + audio' : 'Text only'} · {languageName(row.installed_request.source_locale, 'en')}</dd></>}
    <dt>{row.download_is_upper_bound && !needsNextQuote ? 'Download size, up to' : 'Download size'}</dt>
    <dd>{needsNextQuote ? 'Check next stage' : formatGameBytes(row.download_bytes)}</dd>
    <dt>Additional storage needed</dt><dd>{needsNextQuote ? 'Check next stage' : formatGameBytes(row.required_disk_bytes)}</dd>
    {row.retained_bytes > 0 && <><dt>Saved recordings kept with history</dt><dd>{formatGameBytes(row.retained_bytes)}</dd></>}
   </dl>
   <div className="toolkit-setup-actions">
    <Button variant="outline" disabled={!online || busy || !row.can_activate} onClick={() => void mutate('activate')}>Use downloaded data</Button>
    <Button variant="outline" disabled={!online || busy || !row.can_plan || !source} onClick={() => void mutate('plan')}>Check download size</Button>
    <Button disabled={!online || busy || !canDownloadGame(row, selection)} onClick={() => void mutate('download')}>{row.installed_bytes > 0 && row.state !== 'not_downloaded' ? 'Update' : 'Download'}</Button>
    <Button variant="outline" disabled={!online || busy || !row.can_delete} onClick={() => setConfirmDelete(true)}>Delete downloaded data</Button>
   </div>
   {confirmDelete && <div role="alert"><p>Delete downloaded game data? History, favorites and saved recordings stay.</p>
    <Button variant="outline" onClick={() => setConfirmDelete(false)}>Keep data</Button><Button onClick={() => void mutate('delete')}>Confirm delete</Button></div>}
   {row.job && <p role="status">{row.job.message} · {formatGameBytes(row.job.downloaded_bytes)} / {formatGameBytes(row.job.total_bytes)}</p>}
   {row.message && row.message !== row.job?.message && <p role="status">{row.message}</p>}
  </> : <p>Game data information is unavailable.</p>}
  {error && <p role="alert">{error}</p>}
  {children}
  </DialogContent></Dialog>
 </>;
}
