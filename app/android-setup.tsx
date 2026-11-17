'use client';
import {useEffect, useRef, useState} from 'react';
import {FolderOpen, Loader2} from 'lucide-react';
import {Button} from '../components/ui/button';
import {desktopApiBase} from '../lib/desktop-endpoints';
import {GAME_NAMES, type GameId} from '../lib/games';
import {type NativeCapabilities} from '../lib/native-host';
import {useNativeAccountGeneration} from '../lib/native-account-context';
import {nativeAccountHeaders} from '../lib/native-account-scope.mjs';
import './android-setup.css';

function importReply(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw Error('The app returned an invalid import response.');
  return value as Record<string, unknown>;
}

export function AndroidSetup({online, capabilities, error, libraryReady, onChanged, onAccount}: {
  online: boolean;
  capabilities: NativeCapabilities | null;
  error: string;
  libraryReady: boolean;
  onChanged: (game?: GameId) => void;
  onAccount: () => void;
}) {
  const accountGeneration = useNativeAccountGeneration();
  const fileInput = useRef<HTMLInputElement>(null);
  const pending = useRef<{controller: AbortController; id: string; cancelling: boolean; failed: boolean} | null>(null);
  const cancelRequest = useRef<AbortController | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  useEffect(() => () => {pending.current?.controller.abort(); cancelRequest.current?.abort(); pending.current = null;}, []);

  const cancelImport = async () => {
    const job = pending.current;
    if (!job || job.cancelling) return;
    job.cancelling = true;
    const controller = new AbortController();
    cancelRequest.current = controller;
    setMessage('Cancelling the import…');
    try {
      const response = await fetch(desktopApiBase() + '/api/library/import/cancel', {
        method: 'POST', headers: nativeAccountHeaders(accountGeneration, {'Content-Type': 'application/json', 'X-Proxy-Transcript': 'setup'}),
        body: JSON.stringify({import_id: job.id}), signal: controller.signal,
      });
      const value = importReply(await response.json());
      if (pending.current !== job) return;
      if (response.ok && value.cancelled === true) {
        job.controller.abort();
        setMessage('Import cancelled. Your previous library is kept.');
      } else if (response.status === 409 && value.state === 'already_committed') {
        job.controller.abort();
        setMessage('The library was already imported.');
      } else {
        throw Error('Cancellation could not be confirmed. Checking the active library.');
      }
      pending.current = null; setBusy(false); onChanged();
    } catch (failure) {
      if (pending.current !== job || controller.signal.aborted) return;
      job.cancelling = false;
      setMessage(failure instanceof Error ? failure.message : 'Cancellation could not be confirmed.');
      onChanged();
      if (job.failed) {pending.current = null; setBusy(false);}
    } finally {
      if (cancelRequest.current === controller) cancelRequest.current = null;
    }
  };

  const importLibrary = async (file: File) => {
    if (pending.current) return;
    const controller = new AbortController();
    const job = {controller, id: crypto.randomUUID(), cancelling: false, failed: false};
    pending.current = job;
    setBusy(true); setMessage('Opening the private library…');
    try {
      const response = await fetch(desktopApiBase() + '/api/library/import', {
        method: 'POST', headers: nativeAccountHeaders(accountGeneration, {'Content-Type': 'application/zip', 'X-Proxy-Transcript': 'setup', 'X-Toolkit-Import-Id': job.id}),
        body: file, signal: controller.signal,
      });
      const value = importReply(await response.json());
      if (!response.ok) throw Error(typeof value.detail === 'string' ? value.detail : 'The import could not be confirmed. Check the active library.');
      if (controller.signal.aborted || pending.current !== job) return;
      setMessage(typeof value.message === 'string' ? value.message : 'Private library ready.');
      onChanged(typeof value.game === 'string' && Object.hasOwn(GAME_NAMES, value.game) ? value.game as GameId : undefined);
      cancelRequest.current?.abort();
      pending.current = null; setBusy(false);
    } catch (failure) {
      job.failed = true;
      if (!controller.signal.aborted && pending.current === job && !job.cancelling) {
        setMessage(failure instanceof Error ? failure.message : 'The import could not be confirmed. Check the active library.');
        pending.current = null; setBusy(false); onChanged();
      }
    }
  };

  return <details className="android-device-setup" open={!libraryReady}>
    <summary><FolderOpen size={17} /> Library and device</summary>
    <div className="game-start-card android-library-card">
      <div>
        <h2>Private library on this device</h2>
        <p>Open a prepared toolkit library ZIP. Text, available original voices and history are processed in the app.</p>
        <p className="toolkit-setup-note">Keep the original ZIP. Account keys and private screen links do not belong in a library export.</p>
      </div>
      <div className="toolkit-setup-actions">
        <Button variant="outline" disabled={!online || !capabilities?.library_import || busy} onClick={() => fileInput.current?.click()}>
          {busy ? <Loader2 className="animate-spin" /> : <FolderOpen />} Open library
        </Button>
        <input ref={fileInput} type="file" accept=".zip,application/zip" hidden aria-label="Private toolkit library"
          onChange={event => {const file = event.currentTarget.files?.[0]; event.currentTarget.value = ''; if (file) void importLibrary(file);}} />
        {busy && <Button variant="outline" onClick={() => void cancelImport()}>Cancel import</Button>}
        {capabilities?.protected_accounts && <Button variant="outline" onClick={onAccount}>Lexirise account</Button>}
      </div>
      <p role="status">{message || error || capabilities?.message || 'Checking this app’s device features…'}</p>
      {capabilities?.capture_source === 'authored-observations' && <p className="toolkit-setup-note">This prototype verifies prepared dialogue with test observations. A game-screen source has not been verified for this build.</p>}
      {capabilities && !capabilities.protected_accounts && <p className="toolkit-setup-note">Account connection is unavailable in this app build. Local reading remains available.</p>}
      <p className="toolkit-setup-note">Desktop browser extensions do not run inside this app. Your independent reading mode and local reading preferences remain available.</p>
    </div>
  </details>;
}
