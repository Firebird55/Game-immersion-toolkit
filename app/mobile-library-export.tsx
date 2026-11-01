'use client';
import {desktopApiBase} from '../lib/desktop-endpoints';

import {useInterfaceTranslation} from '../lib/interface-language';

import { useEffect, useRef, useState } from 'react';
import { Check, Download, FolderOpen, Smartphone, Square } from 'lucide-react';
import { Button } from '@/components/ui/button';

type Estimate = { estimatedBytes: number; estimateLowBytes: number; estimateHighBytes: number; workingBytes: number; freeBytes: number; rows: number; basis: string };
export type MobileExportStatus = { state: string; game?: string; selectedGame?: string; scope?: string; sourceLocale?: string; progress: number; message: string; folder?: string; bundle?: string; bytes?: number;
  destinationFolder?: string; outputFolder?: string; browseActive?: boolean; browsePhase?: string | null; browseMessage?: string; estimatedCatalogBytes?: number; estimatedAudioBytes?: number; audioBytes?: number;
  done?: number; total?: number; estimate?: Estimate; coverage?: { dialogue: number; exportedVoices: number } };
const activeStates = ['preparing', 'exporting', 'cancelling'];
const gb = (bytes: number) => `${(bytes / 1e9).toFixed(bytes > 0 && bytes < 1e7 ? 3 : 2)} GB`;

export function MobileLibraryExport({ game, title, ready, textOnly, busy, status, action }: {
  game: string; title: string; ready: boolean; textOnly: boolean; busy: boolean; status?: MobileExportStatus;
  action: (path: string, body?: object, success?: string) => Promise<boolean>;
}) {
 const uiText=useInterfaceTranslation();
  const [voices, setVoices] = useState(true), [folder, setFolder] = useState('');
  const [estimate, setEstimate] = useState<Estimate | null>(null), [estimating, setEstimating] = useState(false), [estimateError, setEstimateError] = useState('');
  const dirty = useRef(false);
  const languageMissing = status?.sourceLocale === 'unconfigured';
  const active = activeStates.includes(status?.state ?? ''), stopping = status?.state === 'cancelling';
  const thisJob = status?.game === game, includeAudio = voices && !textOnly;
  useEffect(() => { if (!dirty.current && status?.destinationFolder) setFolder(status.destinationFolder); }, [status?.destinationFolder]);
  useEffect(() => {
    if (!folder || active || languageMissing) return;
    const controller = new AbortController();
    setEstimating(true); setEstimateError(''); setEstimate(null);
    const timer = window.setTimeout(() => {
      void fetch(`${desktopApiBase()}/api/setup/games/${game}/mobile-export/preview`, { method: 'POST', signal: controller.signal,
        headers: { 'Content-Type': 'application/json', 'X-Proxy-Transcript': 'setup',
          ...(status?.scope ? {'X-Proxy-Transcript-Export-Scope':status.scope} : {}) },
        body: JSON.stringify({ include_audio: includeAudio, destination_folder: folder }) })
        .then(async response => { const value = await response.json() as Estimate & { detail?: string }; if (!response.ok) throw new Error(value.detail || 'Estimate unavailable.'); return value; })
        .then(value => { if (!controller.signal.aborted) setEstimate(value); })
        .catch(reason => { if (!controller.signal.aborted) setEstimateError(reason.message); })
        .finally(() => { if (!controller.signal.aborted) setEstimating(false); });
    }, 400);
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [game, includeAudio, folder, active, status?.scope, languageMissing]);
  const currentEstimate = active && thisJob ? status?.estimate : estimate;
  const measuredEstimate = thisJob && active && status?.estimatedAudioBytes != null
    ? status.estimatedAudioBytes + (status.estimatedCatalogBytes ?? 0) : currentEstimate?.estimatedBytes;
  const completed = thisJob && status?.state === 'complete';
  const normalizePath = (path: string) => path.replaceAll('\\', '/').replace(/\/+$/, '').toLowerCase();
  const completedHere = completed && !!status.outputFolder && !!status.destinationFolder && normalizePath(status.destinationFolder) === normalizePath(folder);
  const visibleStatus = thisJob && status?.state !== 'idle';
  return <section className="toolkit-export-card" aria-label={uiText("Mobile library export")}>
    <div className="toolkit-card-heading"><Smartphone size={20} /><div><h3>{uiText("Mobile library")}</h3><p>{uiText("Take")} {title}  {uiText("transcripts and voices to your phone.")}</p></div></div>
    <label className="toolkit-setup-checkbox toolkit-export-option"><input type="checkbox" checked={includeAudio} disabled={active || textOnly}
      onChange={event => setVoices(event.target.checked)} /><span><strong>{uiText("Original game voices")}</strong><small>{textOnly ? uiText("This game supports text only.") : uiText("Include playable audio. Uncheck for a smaller catalog-only export.")}</small></span></label>
    <div className="toolkit-destination">
      <label htmlFor="mobile-export-folder">{uiText("Save libraries to")}</label>
      <div className="toolkit-destination-row"><input id="mobile-export-folder" value={folder} disabled={active || status?.browseActive}
        spellCheck={false} autoComplete="off" placeholder={uiText("Choose a folder on this PC")} onChange={event => { dirty.current = true; setFolder(event.target.value); }} />
        <Button variant="outline" disabled={busy || active || languageMissing || status?.browseActive} onClick={() => { dirty.current = false;
          void action('/api/setup/mobile-export/browse', { game, destination_folder: folder || undefined }, 'Opening the Windows folder browser…'); }}><FolderOpen />{status?.browseActive ? status.browsePhase === 'open' ? uiText("Picker open…") : uiText("Opening…") : uiText("Browse")}</Button></div>
      {status?.browseActive && <div className="toolkit-setup-actions"><p role="status" className="toolkit-setup-note">{status.browsePhase === 'open' ? uiText("Choose a folder in the Windows dialog. If it stalls, close it here and paste a path.") : uiText("Starting the folder browser. You can close it here if no window appears.")}</p>
        <Button variant="outline" onClick={() => void action('/api/setup/mobile-export/browse/cancel', {game}, 'Folder browser closed.')}>{uiText("Close picker")}</Button></div>}
      {status?.browseMessage && <p role="status" className="toolkit-setup-note">{status.browseMessage}</p>}
      <small>{uiText("Creates separate folders for this account, learning language and game. This destination is remembered on this PC.")}</small>
    </div>
    <div className="toolkit-export-estimate" aria-live="polite">
      <div><span>{completedHere ? uiText("Exported size") : uiText("Estimated export size")}</span><strong>{completedHere && status.bytes != null ? gb(status.bytes)
        : measuredEstimate != null ? `≈ ${gb(measuredEstimate)}` : estimating ? uiText("Estimating…") : uiText("Awaiting game data")}</strong></div>
      <div><span>{uiText("Free at destination")}</span><strong>{currentEstimate ? gb(currentEstimate.freeBytes) : '—'}</strong></div>
    </div>
    {currentEstimate && !completedHere && <p className="toolkit-setup-note">{thisJob && active && status?.estimatedAudioBytes != null
      ? uiText("Estimate based on converted voices; it changes as clips are deduplicated.")
      : `${currentEstimate.basis}. Approximate range: ${gb(currentEstimate.estimateLowBytes)}–${gb(currentEstimate.estimateHighBytes)}.`}
      {' '}{uiText("Allow about")} {gb(currentEstimate.workingBytes)} {uiText("on this drive for ZIPs, conversion and reusable caches.")}</p>}
    {currentEstimate && currentEstimate.freeBytes < currentEstimate.workingBytes && !completedHere && <p className="toolkit-setup-warning">{uiText("This drive may not have enough working space. Choose a roomier drive or export without voices.")}</p>}
    {estimateError && <p role="alert" className="toolkit-setup-error">{estimateError}</p>}
    {!ready && <p className="toolkit-setup-warning">{uiText("Refresh game data before exporting.")}</p>}
    {active && !thisJob && <p role="status">{uiText("Another game is exporting. Cancel it below or wait for completion.")}</p>}
    <div className="toolkit-setup-actions toolkit-export-actions">
      <Button disabled={busy || !ready || languageMissing || active || !estimate || estimating || !!estimateError || status?.browseActive}
        onClick={() => void action(`/api/setup/games/${game}/mobile-export`, { include_audio: includeAudio, destination_folder: folder }, 'Export started. You can close Setup while it runs.')}><Download />{thisJob && status?.state === 'cancelled' ? uiText("Resume export") : uiText("Export mobile library")}</Button>
      {active && <Button variant="outline" disabled={stopping} onClick={() => void action('/api/setup/mobile-export/cancel', {game}, 'Stopping export…')}><Square size={14} />{stopping ? uiText("Stopping…") : uiText("Cancel export")}</Button>}
    </div>
    {languageMissing && <p className="toolkit-setup-note">{uiText("Select and prepare a learning language in Languages before exporting.")}</p>}
    {visibleStatus && <div className={`toolkit-export-progress ${completed ? 'is-complete' : ''}`}>
      <div className="toolkit-export-progress-heading"><strong>{completed ? <><Check size={16} /> {uiText("Ready to transfer")}</> : status.message}</strong><span>{status.state === 'preparing' ? uiText("Preparing…") : `${Math.round(status.progress)}%`}</span></div>
      <progress aria-label={uiText("Mobile export progress")} max={100} value={status.state === 'preparing' ? undefined : status.progress} />
      {status.total != null && <p className="toolkit-setup-note">{(status.done ?? 0).toLocaleString()} / {status.total.toLocaleString()} {uiText("dialogue entries")}{status.audioBytes != null ? ` · ${gb(status.audioBytes)} audio converted` : ''}</p>}
      {completed && <><p>{status.coverage?.dialogue.toLocaleString()} {uiText("bilingual lines ·")}{status.coverage?.exportedVoices.toLocaleString()} {uiText("voice-backed lines")}</p>
        <label>{uiText("Copy this library file to your phone")}<code className="toolkit-export-path">{status.bundle ?? status.folder}</code></label>
        <p className="toolkit-setup-note">{status.bytes != null ? `${gb(status.bytes)} to transfer. ` : ''}{uiText("One ZIP includes the catalog and voices. Keep it zipped.")}</p></>}
      {status.state === 'cancelled' && <p className="toolkit-setup-note">{uiText("Completed clips are kept. Resume with the same save folder to reuse them.")}</p>}
      {status.state === 'error' && <p className="toolkit-setup-error">{status.message}</p>}
    </div>}
    <details className="toolkit-export-help"><summary>{uiText("Play on your phone")}</summary><ol><li>{uiText("Copy the single Mobile Library ZIP to Files on your phone. Keep it zipped.")}</li><li>{uiText("Open the mobile page, open your library, paste the VDO.Ninja viewer link and tap Start playing.")}</li><li>{uiText("The PC can be off during play. Reopen the same library file after reloading the website.")}</li></ol></details>
  </section>;
}
