'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Check, Download, FolderOpen, RefreshCw, Settings2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';

const API = 'http://127.0.0.1:8766';
type GameId = 'zzz' | 'pragmata' | 'hito' | 'cyberpunk' | 'wuwa' | 'witcher3' | 'nte' | 'honkai3';
type GameSetup = {
  id: GameId; title: string; configured_path: string | null; detected_path: string | null;
  folder_state: string; folder_hint: string; voice_state: string; voice_hint: string;
  tools_missing: string[]; index_ready: boolean; audio_ready: boolean; indexed_lines: number;
  index_message: string; update_message: string; update_state: string; progress: number;
  last_checked: string | null; needs_attention: boolean;
  catalog_message?: string | null; catalog_warning?: boolean;
  expansion_message?: string; expansion_state?: string;
};
type Setup = {
  completed: boolean; version: string; games: GameSetup[]; auto_start: boolean; free_gb: number | null;
  lexirise_configured: boolean; requirements: { id: string; title: string; ready: boolean; help: string }[];
  jobs: Record<string, { state: string; message: string; progress: number }>;
  native: Record<string, boolean>; capture_check?: boolean | null;
};
const VOICE_LABELS: Record<string, string> = { present: 'Mandarin voice files found', missing: 'Mandarin voice pack needed',
  not_checked: 'Choose a game folder first', verify_during_indexing: 'Voice pack checked during indexing', not_required: 'Voice pack not required' };

export function ToolkitSetup({ online, game, onGameChange, readingMode, onReadingMode, onCapture, onReading, onAccount, onChanged }: {
  online: boolean; game: GameId; onGameChange: (game: GameId) => void;
  readingMode: 'migaku' | 'lexirise'; onReadingMode: (mode: 'migaku' | 'lexirise') => void;
  onCapture: () => void; onReading: () => void; onAccount: () => void; onChanged: () => void;
}) {
  const [open, setOpen] = useState(false), [step, setStep] = useState(0);
  const [data, setData] = useState<Setup | null>(null), [folder, setFolder] = useState('');
  const [autoStart, setAutoStart] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [message, setMessage] = useState('');
  const firstLoad = useRef(false), dirty = useRef(false);
  const current = data?.games.find(item => item.id === game);
  const job = data?.jobs[game];
  const preparing = Object.values(data?.jobs ?? {}).some(item => item.state === 'preparing');
  const nativeBusy = Object.values(data?.native ?? {}).some(Boolean);
  const refresh = useCallback(async () => {
    const response = await fetch(`${API}/api/setup`, { cache: 'no-store' });
    if (!response.ok) throw new Error('Could not load setup. Make sure the companion is running.');
    const value = await response.json() as Setup;
    if (!Array.isArray(value.games) || !Array.isArray(value.requirements)) throw new Error('Setup requires the latest companion backend.');
    setData(value);
    return value;
  }, []);
  useEffect(() => {
    if (!online || firstLoad.current) return;
    let active = true;
    void refresh().then(value => {
      if (active) { firstLoad.current = true; if (!value.completed) setOpen(true); }
    }).catch(() => undefined);
    return () => { active = false; };
  }, [online, refresh]);
  useEffect(() => {
    if (!open) return;
    void refresh().catch(reason => setError(reason.message));
    const timer = window.setInterval(() => { void refresh().catch(() => undefined); }, 5000);
    return () => window.clearInterval(timer);
  }, [open, refresh]);
  useEffect(() => {
    if (!dirty.current) setFolder(current?.configured_path ?? current?.detected_path ?? '');
  }, [game, current?.configured_path, current?.detected_path]);

  async function action(path: string, body: object = {}, success = '') {
    setBusy(true); setError(''); setMessage('');
    try {
      const response = await fetch(`${API}${path}`, { method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Proxy-Transcript': 'setup' }, body: JSON.stringify(body) });
      const result = await response.json() as { detail?: string; started?: boolean };
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Setup action failed. Please retry.');
      await refresh(); onChanged();
      setMessage(result.started === false ? 'A setup task is already running or queued.' : success || 'Checking game data in the background.');
      return true;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not reach the companion.');
      return false;
    } finally { setBusy(false); }
  }
  async function saveFolder() {
    dirty.current = false;
    if (!await action(`/api/setup/games/${game}`, { path: folder }, 'Folder saved on this PC. Prepare game tools if needed, then refresh game data.')) dirty.current = true;
  }
  function leaveFor(callback: () => void) { setOpen(false); callback(); }
  async function report() {
    setError('');
    try {
      const response = await fetch(`${API}/api/setup/report`, { cache: 'no-store' });
      if (!response.ok) throw new Error('Could not create the setup report.');
      const value = await response.json();
      const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }));
      const link = document.createElement('a'); link.href = url; link.download = 'toolkit-setup-report.json'; document.body.appendChild(link); link.click(); link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Report unavailable.'); }
  }
  return <>
    <Button variant="outline" disabled={!online} onClick={() => { setAutoStart(null); setError(''); setMessage(''); setStep(0); setOpen(true); }}>
      <Settings2 /> Setup
    </Button>
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="toolkit-setup-dialog sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Toolkit setup</DialogTitle>
          <DialogDescription>Connect your own installed games. Game archives and voices stay on this PC.</DialogDescription>
        </DialogHeader>
        <nav className="toolkit-setup-tabs" aria-label="Setup sections">
          {['Games', 'Capture', 'Reading'].map((name, index) => <button key={name} type="button" aria-pressed={step === index}
            onClick={() => setStep(index)}>{index + 1}. {name}</button>)}
        </nav>
        {!data && <p role="status">Loading local setup…</p>}
        {data && step === 0 && <section className="toolkit-setup-section" aria-label="Game files">
          <label>Game to configure<select aria-label="Game to configure" value={game} onChange={event => { dirty.current = false; setError(''); setMessage(''); onGameChange(event.target.value as GameId); }}>
            {data.games.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}
          </select></label>
          {current && <>
            <p>{current.folder_hint}</p>
            {game === 'nte' && current.tools_missing.includes('.NET 10 SDK') && <p>NTE needs the <a href="https://dotnet.microsoft.com/download/dotnet/10.0" target="_blank" rel="noreferrer">Microsoft .NET 10 SDK</a>. Install it, then prepare game tools.</p>}
            <label>Installed game folder<input value={folder} onChange={event => { dirty.current = true; setFolder(event.target.value); }}
              placeholder="Paste the folder path, or use Browse game folders" spellCheck={false} autoComplete="off" /></label>
            <div className="toolkit-setup-actions">
              <Button variant="outline" disabled={busy || nativeBusy} onClick={() => { dirty.current = false; void action('/api/setup/native/folders', {}, 'The Windows folder picker opened on this PC. Save your folders there; setup will refresh when it closes.'); }}><FolderOpen /> Browse game folders</Button>
              <Button disabled={busy || nativeBusy || !folder.trim()} onClick={() => void saveFolder()}>Save game folder</Button>
              <Button variant="outline" disabled={busy || nativeBusy} onClick={() => { dirty.current = false; void action(`/api/setup/games/${game}`, { use_automatic: true }, 'Automatic detection enabled for this game.'); }}>Use automatic detection</Button>
            </div>
            <div className="toolkit-setup-summary">
              <p><strong>Folder:</strong> {current.folder_state === 'configured' ? 'Verified' : current.folder_state === 'detected' ? 'Found automatically' : current.folder_state === 'invalid' ? 'Saved folder unavailable; choose its new location' : 'Not found yet'}</p>
              <p><strong>Voices:</strong> {VOICE_LABELS[current.voice_state] ?? current.voice_state}</p>
              <p>{current.voice_hint}</p>
              {current.expansion_message && <p role="status">{current.expansion_message}</p>}
              <p><strong>Game tools:</strong> {current.tools_missing.length ? 'Installation needed' : 'Ready'}</p>
              <div className="toolkit-setup-actions">
                {game !== 'hito' && <Button variant="outline" disabled={busy || preparing || !current.detected_path} onClick={() => void action(`/api/setup/games/${game}/tools`, {}, 'Preparing game tools. You can keep browsing while this runs.')}><Download /> {current.tools_missing.length ? 'Install game tools' : 'Repair game tools'}</Button>}
                <Button disabled={busy || preparing || !current.detected_path || !!current.tools_missing.length} onClick={() => void action(`/api/setup/games/${game}/refresh`)}><RefreshCw /> Refresh game data</Button>
              </div>
              {job && <p role="status" className={job.state === 'error' ? 'toolkit-setup-error' : ''}>{job.message}</p>}
              <p role="status">{current.update_message}</p>
              {current.catalog_message && <p role="status" className={current.catalog_warning ? 'toolkit-setup-error' : ''}>{current.catalog_message}</p>}
              {(current.update_state === 'checking' || current.update_state === 'updating' || job?.state === 'preparing') && <progress aria-label="Game setup progress" value={job?.state === 'preparing' ? job.progress : current.progress} max={100} />}
              <p>{current.index_ready ? `${current.indexed_lines.toLocaleString()} subtitle pairs indexed` : 'Subtitles will be indexed from your local game files.'}{current.audio_ready ? ' · Original voices ready' : ''}</p>
              {current.needs_attention && <p className="toolkit-setup-error">Indexing needs attention. Let the game launcher finish its download, check the voice pack, and retry.</p>}
              {current.last_checked && <small>Last check: {new Date(current.last_checked).toLocaleString()}</small>}
            </div>
            <p className="toolkit-setup-note">After updating the game through its launcher, use <strong>Refresh game data</strong>. Compatible game data and catalog updates need no new toolkit release. Automatic checks keep indexes current while the toolkit runs. A failed refresh keeps the previous complete index. Changed game formats may require a toolkit update.</p>
            <details><summary>Where game tools come from</summary><p>Selected games download their decoder and extraction tools separately. Upstream terms apply; tool downloads are checksum verified and kept outside your game installation.</p>
              <a href="https://github.com/vgmstream/vgmstream/releases/tag/r2117" target="_blank" rel="noreferrer">vgmstream</a>{' · '}
              <a href="https://github.com/simon300000/zenless-voice" target="_blank" rel="noreferrer">ZZZ reader</a>{' · '}
              <a href="https://github.com/Ekey/REE.PAK.Tool" target="_blank" rel="noreferrer">REE unpacker</a>{' · '}
              <a href="https://github.com/WolvenKit/WolvenKit" target="_blank" rel="noreferrer">WolvenKit</a>{' · '}
              <a href="https://github.com/Herselfta/FModelCLI" target="_blank" rel="noreferrer">FModelCLI</a>
            </details>
          </>}
        </section>}
        {data && step === 1 && <section className="toolkit-setup-section" aria-label="Capture checks">
          <h3>Capture and audio requirements</h3>
          <ul className="toolkit-setup-checks">{data.requirements.map(item => <li key={item.id}>
            <span className={item.ready ? 'is-ready' : 'needs-setup'}>{item.ready ? <Check size={16} /> : '!'} {item.title}: {item.ready ? 'Available' : 'Needs setup'}</span>
            {!item.ready && <p>{item.help}</p>}
          </li>)}</ul>
          <p>Run the OCR/display test, then start your game with English or Chinese subtitles. Use Capture setup to check the live subtitle crop and choose V or Rover's voice where applicable.</p>
          <div className="toolkit-setup-actions"><Button variant="outline" disabled={busy || nativeBusy} onClick={() => void action('/api/setup/native/checks', {}, 'The read-only OCR and display test opened in a local console. Its output stays on this PC.')}>Run OCR and display test</Button>
            <Button onClick={() => leaveFor(onCapture)}>Open capture setup</Button></div>
          {data.capture_check !== null && data.capture_check !== undefined && <p role="status">{data.capture_check ? 'OCR and display test passed.' : 'OCR and display test needs attention. Re-run Install.cmd to repair dependencies.'}</p>}
          {data.free_gb !== null && <p>{data.free_gb} GB free on the toolkit drive. Extracted indexes and played voice clips use additional local space.</p>}
          <label className="toolkit-setup-checkbox"><input type="checkbox" checked={autoStart ?? data.auto_start} onChange={event => setAutoStart(event.target.checked)} /> Start capture automatically when I open the toolkit</label>
          <p className="toolkit-setup-note">No microphone setup is needed: the toolkit reads visible subtitles and plays original audio from installed files.</p>
        </section>}
        {data && step === 2 && <section className="toolkit-setup-section" aria-label="Reading setup">
          <h3>Choose your reading mode</h3>
          <label>Reading mode<select aria-label="Reading mode" value={readingMode} onChange={event => onReadingMode(event.target.value as 'migaku' | 'lexirise')}><option value="migaku">Migaku</option><option value="lexirise">Lexirise</option></select></label>
          <p>Chinese game transcripts keep their original language. Reading preferences are stored locally.</p>
          {readingMode === 'migaku' ? <p>Use your installed Migaku browser extension with the selectable transcript text. You can switch reading modes at any time.</p> : <>
            <Button variant="outline" onClick={() => leaveFor(onReading)}>Configure reading options</Button>
            <h3>Optional Lexirise account</h3><p>{data.lexirise_configured ? 'An API key is configured on this PC.' : 'Add your own Lexirise API key to use lookups and explicit sentence exports.'}</p>
            <Button variant="outline" disabled={busy || nativeBusy} onClick={() => void action('/api/setup/native/lexirise', {}, 'A hidden-input prompt opened on this PC. Enter your key there; it is stored encrypted for this Windows user.')}>{data.lexirise_configured ? 'Replace local API key' : 'Set up local API key'}</Button>
            <Button variant="outline" disabled={!data.lexirise_configured} onClick={() => leaveFor(onAccount)}>Account and game deck</Button>
            <p className="toolkit-setup-note">Choose a destination for each game before exporting. Account writes and sentence uploads require your explicit action.</p>
          </>}
          <h3>Toolkit updates and support</h3><p><a href="https://github.com/Firebird55/Game-immersion-toolkit/releases/latest" target="_blank" rel="noreferrer">Get the latest toolkit release</a> · Installed version {data.version}</p>
          <Button variant="outline" onClick={() => void report()}>Download setup report</Button>
          <p className="toolkit-setup-note">The report includes versions and readiness flags. It excludes folder paths, credentials, account details and transcript contents.</p>
        </section>}
        {error && <p role="alert" className="toolkit-setup-error">{error}</p>}
        {message && <p role="status" className="toolkit-setup-note">{message}</p>}
        <div className="toolkit-setup-navigation">
          {step > 0 && <Button variant="outline" onClick={() => setStep(step - 1)}>Back</Button>}
          {step < 2 && <Button disabled={!data} onClick={() => setStep(step + 1)}>Next</Button>}
          {step === 2 && <Button disabled={busy || !data} onClick={() => { void action('/api/setup/complete', { auto_start: autoStart ?? data?.auto_start ?? false }, 'Setup saved.').then(saved => { if (saved) setOpen(false); }); }}>Finish setup</Button>}
        </div>
      </DialogContent>
    </Dialog>
  </>;
}
