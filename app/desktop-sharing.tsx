'use client';
import {useEffect, useState} from 'react';
import {Smartphone} from 'lucide-react';

type Connection = {local: boolean; paired: boolean; urls?: string[]; code?: string; expires_in?: number};

export function DesktopSharing({game}: {game: string}) {
  const [open, setOpen] = useState(false);
  const [connection, setConnection] = useState<Connection | null>(null);
  const [message, setMessage] = useState('');
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    const refresh = async () => {
      try {
        const response = await fetch('/api/connection', {cache: 'no-store', signal: controller.signal});
        if (!response.ok) throw Error('Start the desktop executable to share this transcript.');
        const value = await response.json() as Connection;
        if (typeof value.local !== 'boolean') throw Error('Start the desktop executable to share this transcript.');
        setConnection(value); setMessage('');
      } catch (error) {
        if (!controller.signal.aborted) setMessage(error instanceof Error ? error.message : 'Desktop unavailable.');
      }
    };
    void refresh();
    const interval = setInterval(() => {void refresh();}, 30000);
    return () => {controller.abort(); clearInterval(interval);};
  }, [open]);
  return <details className="desktop-sharing" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary><Smartphone size={17}/><span>Share</span></summary>
    <div className="desktop-sharing-panel">
      <strong>Connect a phone or tablet</strong>
      {message && <p role="status">{message}</p>}
      {connection?.local ? <>
        <p>On the same Wi-Fi, open this address in your browser:</p>
        {connection.urls?.length ? connection.urls.map(url => <p key={url}><a href={url}>{url}</a></p>) : <p>Connect this desktop to your local network first.</p>}
        <label>Connection code <output>{connection.code}</output></label>
        <p>The code refreshes every ten minutes. Connected devices stay connected for 24 hours.</p>
      </> : connection && <p>You’re connected to this desktop. Use Share on the desktop to connect another device.</p>}
      <a href={'/mobile-capture/?pc=1&game='+game} target="_blank" rel="noopener noreferrer">More connection options</a>
    </div>
  </details>;
}
