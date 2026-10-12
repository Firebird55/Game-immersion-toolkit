'use client';

import { useEffect, useRef, useState } from 'react';
import { Check, Download, FolderOpen, Smartphone, Square } from 'lucide-react';
import { Button } from '@/components/ui/button';

type Estimate = { estimatedBytes: number; estimateLowBytes: number; estimateHighBytes: number; workingBytes: number; freeBytes: number; rows: number; basis: string };
export type MobileExportStatus = { state: string; game?: string; progress: number; message: string; folder?: string; bytes?: number;
  destinationFolder?: string; outputFolder?: string; browseActive?: boolean; estimatedCatalogBytes?: number; estimatedAudioBytes?: number; audioBytes?: number;
  done?: number; total?: number; estimate?: Estimate; coverage?: { dialogue: number; exportedVoices: number } };
const activeStates = ['preparing', 'exporting', 'cancelling'];
const gb = (bytes: number) => `${(bytes / 1e9).toFixed(bytes > 0 && bytes < 1e7 ? 3 : 2)} GB`;

export function MobileLibraryExport({ game, title, ready, textOnly, busy, status, action }: {
  game: string; title: string; ready: boolean; textOnly: boolean; busy: boolean; status?: MobileExportStatus;
  action: (path: string, body?: object, success?: string) => Promise<boolean>;
}) {
  const [voices, setVoices] = useState(true), [folder, setFolder] = useState('');
  const [estimate, setEstimate] = useState<Estimate | null>(null), [estimating, setEstimating] = useState(false), [estimateError, setEstimateError] = useState('');
  const dirty = useRef(false);
  const active = activeStates.includes(status?.state ?? ''), stopping = status?.state === 'cancelling';
  const thisJob = status?.game === game, includeAudio = voices && !textOnly;
  useEffect(() => { if (!dirty.current && status?.destinationFolder) setFolder(status.destinationFolder); }, [status?.destinationFolder]);
  useEffect(() => {
    if (!folder || active) return;
    const controller = new AbortController();
    setEstimating(true); setEstimateError(''); setEstimate(null);
    const timer = window.setTimeout(() => {
      void fetch(`http://127.0.0.1:8766/api/setup/games/${game}/mobile-export/preview`, { method: 'POST', signal: controller.signal,
        headers: { 'Content-Type': 'application/json', 'X-Proxy-Transcript': 'setup' },
        body: JSON.stringify({ include_audio: includeAudio, destination_folder: folder }) })
        .then(async response => { const value = await response.json() as Estimate & { detail?: string }; if (!response.ok) throw new Error(value.detail || 'Estimate unavailable.'); return value; })
        .then(value => { if (!controller.signal.aborted) setEstimate(value); })
        .catch(reason => { if (!controller.signal.aborted) setEstimateError(reason.message); })
        .finally(() => { if (!controller.signal.aborted) setEstimating(false); });
    }, 400);
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [game, includeAudio, folder, active]);
  const currentEstimate = active && thisJob ? status?.estimate : estimate;
  const measuredEstimate = thisJob && active && status?.estimatedAudioBytes != null
    ? status.estimatedAudioBytes + (status.estimatedCatalogBytes ?? 0) : currentEstimate?.estimatedBytes;
  const completed = thisJob && status?.state === 'complete';
  const normalizePath = (path: string) => path.replaceAll('\\', '/').replace(/\/+$/, '').toLowerCase();
  const completedHere = completed && !!status.outputFolder && normalizePath(status.outputFolder) === normalizePath(`${folder}/${game}`);
  const visibleStatus = thisJob && status?.state !== 'idle';
  return <section className="toolkit-export-card" aria-label="Mobile library export">
    <div className="toolkit-card-heading"><Smartphone size={20} /><div><h3>Mobile library</h3><p>Take {title} transcripts and voices to your phone.</p></div></div>
    <label className="toolkit-setup-checkbox toolkit-export-option"><input type="checkbox" checked={includeAudio} disabled={active || textOnly}
      onChange={event => setVoices(event.target.checked)} /><span><strong>Original Mandarin voices</strong><small>{textOnly ? 'This game supports text only.' : 'Include playable audio. Uncheck for a smaller catalog-only export.'}</small></span></label>
    <div className="toolkit-destination">
      <label htmlFor="mobile-export-folder">Save libraries to</label>
      <div className="toolkit-destination-row"><input id="mobile-export-folder" value={folder} disabled={active || status?.browseActive}
        spellCheck={false} autoComplete="off" placeholder="Choose a folder on this PC" onChange={event => { dirty.current = true; setFolder(event.target.value); }} />
        <Button variant="outline" disabled={busy || active || status?.browseActive} onClick={() => { dirty.current = false;
          void action('/api/setup/mobile-export/browse', { destination_folder: folder || undefined }, 'Choose a save folder in the Windows dialog.'); }}><FolderOpen />{status?.browseActive ? 'Picker open…' : 'Browse'}</Button></div>
      <small>Creates a separate folder for each game. This choice is remembered on this PC.</small>
    </div>
    <div className="toolkit-export-estimate" aria-live="polite">
      <div><span>{completedHere ? 'Exported size' : 'Estimated export size'}</span><strong>{completedHere && status.bytes != null ? gb(status.bytes)
        : measuredEstimate != null ? `≈ ${gb(measuredEstimate)}` : estimating ? 'Estimating…' : 'Awaiting game data'}</strong></div>
      <div><span>Free at destination</span><strong>{currentEstimate ? gb(currentEstimate.freeBytes) : '—'}</strong></div>
    </div>
    {currentEstimate && !completedHere && <p className="toolkit-setup-note">{thisJob && active && status?.estimatedAudioBytes != null
      ? 'Estimate based on converted voices; it changes as clips are deduplicated.'
      : `${currentEstimate.basis}. Approximate range: ${gb(currentEstimate.estimateLowBytes)}–${gb(currentEstimate.estimateHighBytes)}.`}
      {' '}Allow about {gb(currentEstimate.workingBytes)} on this drive for ZIPs, conversion and reusable caches.</p>}
    {currentEstimate && currentEstimate.freeBytes < currentEstimate.workingBytes && !completedHere && <p className="toolkit-setup-warning">This drive may not have enough working space. Choose a roomier drive or export without voices.</p>}
    {estimateError && <p role="alert" className="toolkit-setup-error">{estimateError}</p>}
    {!ready && <p className="toolkit-setup-warning">Refresh game data before exporting.</p>}
    {active && !thisJob && <p role="status">Another game is exporting. Cancel it below or wait for completion.</p>}
    <div className="toolkit-setup-actions toolkit-export-actions">
      <Button disabled={busy || !ready || active || !estimate || estimating || !!estimateError || status?.browseActive}
        onClick={() => void action(`/api/setup/games/${game}/mobile-export`, { include_audio: includeAudio, destination_folder: folder }, 'Export started. You can close Setup while it runs.')}><Download />{thisJob && status?.state === 'cancelled' ? 'Resume export' : 'Export mobile library'}</Button>
      {active && <Button variant="outline" disabled={stopping} onClick={() => void action('/api/setup/mobile-export/cancel', {}, 'Stopping export…')}><Square size={14} />{stopping ? 'Stopping…' : 'Cancel export'}</Button>}
    </div>
    {visibleStatus && <div className={`toolkit-export-progress ${completed ? 'is-complete' : ''}`}>
      <div className="toolkit-export-progress-heading"><strong>{completed ? <><Check size={16} /> Ready to transfer</> : status.message}</strong><span>{status.state === 'preparing' ? 'Preparing…' : `${Math.round(status.progress)}%`}</span></div>
      <progress aria-label="Mobile export progress" max={100} value={status.state === 'preparing' ? undefined : status.progress} />
      {status.total != null && <p className="toolkit-setup-note">{(status.done ?? 0).toLocaleString()} / {status.total.toLocaleString()} dialogue entries{status.audioBytes != null ? ` · ${gb(status.audioBytes)} audio converted` : ''}</p>}
      {completed && <><p>{status.coverage?.dialogue.toLocaleString()} bilingual lines · {status.coverage?.exportedVoices.toLocaleString()} voice-backed lines</p>
        <label>Completed export folder<code className="toolkit-export-path">{status.folder}</code></label></>}
      {status.state === 'cancelled' && <p className="toolkit-setup-note">Completed clips are kept. Resume with the same save folder to reuse them.</p>}
      {status.state === 'error' && <p className="toolkit-setup-error">{status.message}</p>}
    </div>}
    <details className="toolkit-export-help"><summary>How to use the ZIPs on your phone</summary><ol><li>Copy the completed catalog ZIP and every voice ZIP to Files → On My iPhone. Keep them zipped. Voice ZIPs are split into packs of at most 512 MiB.</li><li>Open the mobile page, choose Open game library, and select those ZIPs.</li><li>The PC can be off during play. Reselect voice ZIPs after reopening the website.</li></ol></details>
  </section>;
}
