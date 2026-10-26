'use client';
import {useInterfaceTranslation} from '../lib/interface-language';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Check, Download, FolderOpen, RefreshCw, Settings2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { AutomaticMobileLibrary } from './automatic-mobile-library';
import { MobileLibraryExport, type MobileExportStatus } from './mobile-library-export';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';

import {InterfaceLanguage,useInterfaceLanguage} from '@/lib/interface-language';
import {LanguageSetup} from './language-setup';

const API = 'http://127.0.0.1:8766';
type GameId = 'zzz' | 'pragmata' | 'hito' | 'cyberpunk' | 'wuwa' | 'witcher3' | 'nte' | 'beyond' | 'heavyrain' | 'starrail' | 'genshin' | 'endfield';
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
  mobile_export?: MobileExportStatus;
  completed: boolean; version: string; games: GameSetup[]; auto_start: boolean; free_gb: number | null;
  lexirise_configured: boolean; requirements: { id: string; title: string; ready: boolean; help: string }[];
  jobs: Record<string, { state: string; message: string; progress: number }>;
  native: Record<string, boolean>; capture_check?: boolean | null;
};
const VOICE_LABELS: Record<string, string> = { present: 'Original voice files found', missing: 'Selected voice pack needed',
  not_checked: 'Choose a game folder first', verify_during_indexing: 'Voice pack checked during indexing', not_required: 'Voice pack not required',
  needs_language_setup: 'Choose a learning language' };

export function ToolkitSetup({ online, game, onGameChange, readingMode, onReadingMode, onCapture, onReading, onAccount, onChanged, targetLanguage, allowedGames }: {
  online: boolean; game: GameId; onGameChange: (game: GameId) => void;
  readingMode: 'migaku' | 'lexirise'; onReadingMode: (mode: 'migaku' | 'lexirise') => void;
  onCapture: () => void; onReading: () => void; onAccount: (language?:string) => void; onChanged: () => void;
  targetLanguage?: string; allowedGames?: string[];
}) {
 const uiText=useInterfaceTranslation();
  const {t}=useInterfaceLanguage();
  const [open, setOpen] = useState(false), [step, setStep] = useState(0);
  const [data, setData] = useState<Setup | null>(null), [folder, setFolder] = useState('');
  const [autoStart, setAutoStart] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [message, setMessage] = useState('');
  const firstLoad = useRef(false), dirty = useRef(false);
  const refreshSequence = useRef(0);
  const exportStatus = data?.mobile_export?.selectedGame && data.mobile_export.selectedGame !== game ? undefined : data?.mobile_export;
  const current = data?.games.find(item => item.id === game);
  const job = data?.jobs[game];
  const preparing = Object.values(data?.jobs ?? {}).some(item => item.state === 'preparing');
  const nativeBusy = Object.values(data?.native ?? {}).some(Boolean) || !!data?.mobile_export?.browseActive;
  const refresh = useCallback(async () => {
    const sequence = ++refreshSequence.current;
    const response = await fetch(`${API}/api/setup?game=${game}`, { cache: 'no-store' });
    if (!response.ok) throw new Error('Could not load setup. Make sure the companion is running.');
    const value = await response.json() as Setup;
    if (!Array.isArray(value.games) || !Array.isArray(value.requirements)) throw new Error('Setup requires the latest companion backend.');
    if (sequence === refreshSequence.current) setData(value);
    return value;
  }, [game]);
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
    const timer = window.setInterval(() => { void refresh().catch(() => {
      setError('The companion disconnected. Start it again and reopen Setup.');
      setData(previous => previous?.mobile_export ? { ...previous, mobile_export: { ...previous.mobile_export, browseActive: false, browsePhase: null } } : previous);
    }); }, ['preparing', 'exporting', 'cancelling'].includes(data?.mobile_export?.state ?? '') || data?.mobile_export?.browseActive ? 1000 : 5000);
    return () => window.clearInterval(timer);
  }, [open, refresh, data?.mobile_export?.state, data?.mobile_export?.browseActive]);
  useEffect(() => {
    if (!dirty.current) setFolder(current?.configured_path ?? current?.detected_path ?? '');
  }, [game, current?.configured_path, current?.detected_path]);
  useEffect(() => {
    if (['cancelled', 'complete', 'error'].includes(data?.mobile_export?.state ?? '')) setMessage('');
  }, [data?.mobile_export?.state]);
  useEffect(() => {
    if (data?.mobile_export?.browseActive === false) setMessage('');
  }, [data?.mobile_export?.browseActive]);

  async function action(path: string, body: object = {}, success = '') {
    setBusy(true); setError(''); setMessage('');
    try {
      const response = await fetch(`${API}${path}`, { method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Proxy-Transcript': 'setup',
          ...(path.includes('/mobile-export') && data?.mobile_export?.scope ? {'X-Proxy-Transcript-Export-Scope':data.mobile_export.scope} : {}) }, body: JSON.stringify(body) });
      const result = await response.json() as { detail?: string; started?: boolean; cancelled?: boolean };
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Setup action failed. Please retry.');
      await refresh(); onChanged();
      setMessage(result.cancelled === false ? path.endsWith('/browse/cancel') ? 'No folder browser is open.' : 'No export is running.' : result.started === false ? 'A setup task is already running or queued.' : success || 'Checking game data in the background.');
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
      <Settings2 /> {t('Settings')}
    </Button>
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="toolkit-setup-dialog sm:max-w-6xl">
        <DialogHeader>
          <DialogTitle>{t('Settings')}</DialogTitle>
          <DialogDescription>{t('Prepare only your chosen languages. Your game files stay on this PC.')}</DialogDescription>
        </DialogHeader>
        <nav className="toolkit-setup-tabs" aria-label={uiText("Setup sections")}>
          {['Games & Languages', 'Capture', 'Reading', 'Accounts', 'Storage', 'General & Updates'].map((name, index) => <button key={name} type="button" aria-pressed={step === index}
            onClick={() => setStep(index)}>{t(name)}</button>)}
        </nav>
        {!data && <p role="status">{uiText("Loading local setup…")}</p>}
        {data && step === 0 && <section className="toolkit-setup-section" aria-label={uiText("Game files")}>
          <label>{uiText("Game to configure")}<select aria-label={uiText("Game to configure")} value={allowedGames?.includes(game) === false ? '' : game} onChange={event => { dirty.current = false; setError(''); setMessage(''); onGameChange(event.target.value as GameId); }}>
            {allowedGames?.includes(game) === false && <option value="">{t('No matching game selected')}</option>}
            {data.games.filter(item => !allowedGames || allowedGames.includes(item.id)).map(item => <option key={item.id} value={item.id}>{item.title}</option>)}
          </select></label>
          {current && (!allowedGames || allowedGames.includes(game)) && <div className="toolkit-game-grid">
            <section className="toolkit-game-card" aria-label={uiText("Installed game readiness")}>
              <div className="toolkit-card-heading"><FolderOpen size={20} /><div><h3>{uiText("Game files")}</h3><p>{uiText("Your installed files supply the subtitles and voices.")}</p></div></div>
              <div className="toolkit-readiness-grid">
                <div><span>{uiText("Installation")}</span><strong className={current.detected_path ? "is-ready" : "needs-setup"}>{current.detected_path ? uiText("Found") : uiText("Choose folder")}</strong></div>
                <div><span>{uiText("Original voices")}</span><strong className={current.voice_state === 'present' || game === 'hito' ? "is-ready" : "needs-setup"}>{game === 'hito' ? uiText("Text only") : current.voice_state === 'present' ? uiText("Installed") : uiText("Needs setup")}</strong></div>
                <div><span>{uiText("Bilingual catalog")}</span><strong>{current.index_ready ? current.indexed_lines.toLocaleString() + ' pairs' : uiText("Not indexed")}</strong></div>
              </div>
              {current.detected_path && <code className="toolkit-installed-path">{current.detected_path}</code>}
              <details className="toolkit-folder-details" open={!current.detected_path}>
                <summary>{current.detected_path ? uiText("Change installation folder") : uiText("Choose installation folder")}</summary>
                <p className="toolkit-setup-note">{current.folder_hint}</p>
                {game === 'nte' && current.tools_missing.includes('.NET 10 SDK') && <p>{uiText("NTE needs the")} <a href="https://dotnet.microsoft.com/download/dotnet/10.0" target="_blank" rel="noreferrer">{uiText("Microsoft .NET 10 SDK")}</a>{uiText(". Install it, then prepare game tools.")}</p>}
                <label>{uiText("Installed game folder")}<input value={folder} onChange={event => { dirty.current = true; setFolder(event.target.value); }} placeholder={uiText("Paste the installed game folder")} spellCheck={false} autoComplete="off" /></label>
                <div className="toolkit-setup-actions">
                  <Button variant="outline" disabled={busy || nativeBusy} onClick={() => { dirty.current = false; void action('/api/setup/native/folders', {}, 'The Windows folder picker opened. Save your folders there.'); }}><FolderOpen /> {uiText("Browse game folders")}</Button>
                  <Button disabled={busy || nativeBusy || !folder.trim()} onClick={() => void saveFolder()}>{uiText("Save game folder")}</Button>
                  <Button variant="outline" disabled={busy || nativeBusy} onClick={() => { dirty.current = false; void action(`/api/setup/games/${game}`, { use_automatic: true }, 'Automatic detection enabled.'); }}>{uiText("Auto-detect")}</Button>
                </div>
              </details>
              {current.voice_state !== 'present' && game !== 'hito' && <p className="toolkit-setup-warning">{VOICE_LABELS[current.voice_state] ?? current.voice_state}. {current.voice_hint}</p>}
              {current.expansion_message && <p role="status" className="toolkit-setup-note">{current.expansion_message}</p>}
              <div className="toolkit-setup-actions">
                {current.tools_missing.length > 0 && game !== 'hito' && <Button variant="outline" disabled={busy || preparing || !current.detected_path} onClick={() => void action(`/api/setup/games/${game}/tools`, {}, 'Preparing game tools.')}><Download /> {uiText("Install game tools")}</Button>}
                <Button variant="outline" disabled={busy || preparing || !current.detected_path || !!current.tools_missing.length || ['preparing','exporting','cancelling'].includes(data.mobile_export?.state ?? '')}
                  onClick={() => void action(`/api/setup/games/${game}/refresh`)}><RefreshCw /> {uiText("Refresh game data")}</Button>
              </div>
              {job && <p role="status" className={job.state === 'error' ? "toolkit-setup-error" : "toolkit-setup-note"}>{job.message}</p>}
              <p role="status" className="toolkit-setup-note">{current.update_message}</p>
              {current.catalog_message && <p role="status" className={current.catalog_warning ? "toolkit-setup-warning" : "toolkit-setup-note"}>{current.catalog_message}</p>}
              {(current.update_state === 'checking' || current.update_state === 'updating' || job?.state === 'preparing') && <progress aria-label={uiText("Game setup progress")} value={job?.state === 'preparing' ? job.progress : current.progress} max={100} />}
              {current.needs_attention && <p className="toolkit-setup-error">{uiText("Indexing needs attention. Let the launcher finish downloading, check the voice pack, and retry.")}</p>}
              {current.last_checked && <small>{uiText("Last checked")}: {new Date(current.last_checked).toLocaleString()}</small>}
              <details className="toolkit-export-help"><summary>{uiText("Game updates and tools")}</summary>
                <p>{uiText("After a launcher update, refresh game data here. Compatible updates need no new toolkit release. A failed refresh keeps the previous complete index. Changed formats may require a toolkit update.")}</p>
                {game !== 'hito' && <Button variant="outline" disabled={busy || preparing || !current.detected_path} onClick={() => void action(`/api/setup/games/${game}/tools`, {}, 'Repairing game tools.')}><Download /> {uiText("Repair game tools")}</Button>}
                <p>{uiText("Reader tools are downloaded separately and checksum verified. Game files stay in place.")}</p>
                <p><a href="https://github.com/vgmstream/vgmstream/releases/tag/r2117" target="_blank" rel="noreferrer">{uiText("vgmstream")}</a>{' · '}<a href="https://github.com/simon300000/zenless-voice" target="_blank" rel="noreferrer">{uiText("ZZZ reader")}</a>{' · '}<a href="https://github.com/Ekey/REE.PAK.Tool" target="_blank" rel="noreferrer">{uiText("REE unpacker")}</a>{' · '}<a href="https://github.com/WolvenKit/WolvenKit" target="_blank" rel="noreferrer">{uiText("WolvenKit")}</a>{' · '}<a href="https://github.com/Herselfta/FModelCLI" target="_blank" rel="noreferrer">{uiText("FModelCLI")}</a></p>
              </details>
            </section>
            {game !== 'hito' && <LanguageSetup game={game} targetLanguage={targetLanguage} onConfigure={language=>leaveFor(()=>onAccount(language))} onChanged={onChanged}/>}
            <AutomaticMobileLibrary key={game} game={game} /><details className="toolkit-mobile-export"><summary>{uiText("Export mobile library")}</summary><MobileLibraryExport key={`${game}-${exportStatus?.scope ?? 'legacy'}`} game={game} title={current.title} ready={current.index_ready && !!current.detected_path} textOnly={game === 'hito'} busy={busy || nativeBusy} status={exportStatus} action={action} /></details>
          </div>}
        </section>}
        {data && step === 1 && <section className="toolkit-setup-section" aria-label={uiText("Capture checks")}>
          <h3>{uiText("Capture and audio requirements")}</h3>
          <ul className="toolkit-setup-checks">{data.requirements.map(item => <li key={item.id}>
            <span className={item.ready ? "is-ready" : "needs-setup"}>{item.ready ? <Check size={16} /> : '!'} {item.title}: {item.ready ? uiText("Available") : uiText("Needs setup")}</span>
            {!item.ready && <p>{item.help}</p>}
          </li>)}</ul>
          <p>{uiText("Run the OCR/display test, then start your game with subtitles in a prepared language. Use Capture setup to check the live subtitle crop and choose V or Rover's voice where applicable.")}</p>
          <div className="toolkit-setup-actions"><Button variant="outline" disabled={busy || nativeBusy} onClick={() => void action('/api/setup/native/checks', {}, 'The read-only OCR and display test opened in a local console. Its output stays on this PC.')}>{uiText("Run OCR and display test")}</Button>
            <Button onClick={() => leaveFor(onCapture)}>{uiText("Open capture setup")}</Button></div>
          {data.capture_check !== null && data.capture_check !== undefined && <p role="status">{data.capture_check ? uiText("OCR and display test passed.") : uiText("OCR and display test needs attention. Re-run Install.cmd to repair dependencies.")}</p>}
          {data.free_gb !== null && <p>{data.free_gb} {uiText("GB free on the toolkit drive. Extracted indexes and played voice clips use additional local space.")}</p>}
          <label className="toolkit-setup-checkbox"><input type="checkbox" checked={autoStart ?? data.auto_start} onChange={event => setAutoStart(event.target.checked)} /> {uiText("Start capture automatically when I open the toolkit")}</label>
          <p className="toolkit-setup-note">{uiText("No microphone setup is needed: the toolkit reads visible subtitles and plays original audio from installed files.")}</p>
        </section>}
        {data && step === 2 && <section className="toolkit-setup-section" aria-label={uiText("Reading setup")}>
          <h3>{uiText("Choose your reading mode")}</h3>
          <label>{uiText("Reading mode")}<select aria-label={uiText("Reading mode")} value={readingMode} onChange={event => onReadingMode(event.target.value as 'migaku' | 'lexirise')}><option value="migaku">{uiText("Migaku")}</option><option value="lexirise">{uiText("Lexirise")}</option></select></label>
          <p>{uiText("Chinese game transcripts keep their original language. Reading preferences are stored locally.")}</p>
          {readingMode === 'migaku' ? <p>{uiText("Use your installed Migaku browser extension with the selectable transcript text. You can switch reading modes at any time.")}</p> : <>
            <Button variant="outline" onClick={() => leaveFor(onReading)}>{uiText("Configure reading options")}</Button>
          </>}
        </section>}
        {data && step === 3 && <section className="toolkit-setup-section">            <h3>{uiText("Optional Lexirise account")}</h3><p>{data.lexirise_configured ? uiText("An API key is configured on this PC.") : uiText("Add your own Lexirise API key to use lookups and explicit sentence exports.")}</p>
            <Button variant="outline" disabled={busy || nativeBusy} onClick={() => void action('/api/setup/native/lexirise', {}, 'A hidden-input prompt opened on this PC. Enter your key there; it is stored encrypted for this Windows user.')}>{data.lexirise_configured ? uiText("Replace local API key") : uiText("Set up local API key")}</Button>
            <Button variant="outline" disabled={!data.lexirise_configured} onClick={() => leaveFor(onAccount)}>{uiText("Account and game deck")}</Button>
            <p className="toolkit-setup-note">{uiText("Choose a destination for each game before exporting. Account writes and sentence uploads require your explicit action.")}</p>
        </section>}
        {data && step === 4 && <section className="toolkit-setup-section">{game !== 'hito' ? <LanguageSetup game={game} storageOnly onConfigure={language=>leaveFor(()=>onAccount(language))} onChanged={onChanged}/> : <p>{uiText("Hito uses its existing text catalog.")}</p>}</section>}
        {data && step === 5 && <section className="toolkit-setup-section"><InterfaceLanguage/>
          <h3>{uiText("Toolkit updates and support")}</h3><p><a href="https://github.com/Firebird55/Game-immersion-toolkit/releases/latest" target="_blank" rel="noreferrer">{uiText("Get the latest toolkit release")}</a> {uiText("· Installed version")} {data.version}</p>
          <Button variant="outline" onClick={() => void report()}>{uiText("Download setup report")}</Button>
          <p className="toolkit-setup-note">{uiText("The report includes versions and readiness flags. It excludes folder paths, credentials, account details and transcript contents.")}</p>
        </section>}
        {error && <p role="alert" className="toolkit-setup-error">{error}</p>}
        {message && <p role="status" className="toolkit-setup-note">{message}</p>}
        <div className="toolkit-setup-navigation">
          {step > 0 && <Button variant="outline" onClick={() => setStep(step - 1)}>{t('Back')}</Button>}
          {step < 5 && <Button disabled={!data} onClick={() => setStep(step + 1)}>{t('Next')}</Button>}
          {step === 5 && <Button disabled={busy || !data} onClick={() => { void action('/api/setup/complete', { auto_start: autoStart ?? data?.auto_start ?? false }, 'Setup saved.').then(saved => { if (saved) setOpen(false); }); }}>{t('Finish setup')}</Button>}
        </div>
      </DialogContent>
    </Dialog>
  </>;
}
