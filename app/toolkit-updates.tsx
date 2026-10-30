'use client';
import {desktopApiBase} from '../lib/desktop-endpoints';

import {useEffect, useState} from 'react';
import {Button} from '@/components/ui/button';
const API = desktopApiBase()+'/api/toolkit-update';
type Update = {installed_version?: string; available_version?: string; enabled?: boolean; supported?: boolean; state?: string; message?: string; stage?: string; downloaded_bytes?: number; total_bytes?: number; updated_at?: string};
export function ToolkitUpdates() {
  const [status, setStatus] = useState<Update>({}), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    const poll = async () => {try {
      const response = await fetch(API, {cache: 'no-store', signal: controller.signal});
      if (!response.ok) throw Error('Cannot reach the toolkit updater. Keep the desktop launcher open.');
      setStatus(await response.json());
      setError('');
    } catch(e) {if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Cannot reach the toolkit updater.');}};
    void poll(); const timer = setInterval(() => void poll(), 3000);
    return () => {controller.abort(); clearInterval(timer);};
  }, []);
  async function action(path: string, body?: object) {
    setBusy(true); setError('');
    try {
      const response = await fetch(API + path, {method: 'POST', headers: {'Content-Type':'application/json', 'X-Proxy-Transcript':'setup'}, body: JSON.stringify(body ?? {})});
      if (!response.ok) {
        const failure = await response.json().catch(() => ({})) as {detail?: unknown};
        throw Error(typeof failure.detail === 'string' ? failure.detail : 'Could not start the update. Keep the desktop launcher open and try again.');
      }
      if (body) setStatus(await response.json());
    } catch(e) {setError(e instanceof Error ? e.message : 'Update request failed.');} finally {setBusy(false);}
  }
  return <section aria-label="Toolkit software updates"><h3>Toolkit software updates</h3>
    <p>Running version: {status.installed_version ?? 'Checking…'}{status.available_version && ` · Latest checked: ${status.available_version}`}</p>
    <label><input type="checkbox" checked={status.enabled ?? false} disabled={busy || status.enabled == null || status.supported === false} onChange={e => void action('/preferences', {enabled: e.target.checked})}/>Automatically install verified stable releases</label>
    {status.supported !== false && <p>Checks run on startup and every 6 hours. Game-language checks run separately every 2 minutes. Updates preserve your history, calibration and accounts.</p>}
    <p role="status">{status.stage ?? status.message ?? 'Checking updater status…'}</p>
    {status.total_bytes ? <progress max={status.total_bytes} value={status.downloaded_bytes ?? 0} aria-label="Toolkit download progress"/> : null}
    {status.updated_at && <small>Last progress: {new Date(status.updated_at).toLocaleString()}</small>}
    <Button disabled={busy || status.supported === false || ['checking','downloading','verifying','installing','preparing','quiescing','activating','rolling_back'].includes(status.state ?? '')} onClick={() => void action('/check')}>Check and install now</Button>
    {error && <p role="alert">{error}</p>}
  </section>;
}
