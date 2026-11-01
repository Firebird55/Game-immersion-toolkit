import React, {useState} from 'react';
import {desktopAddress} from '../lib/desktop-address.mjs';

export function DesktopConnection() {
  const [address, setAddress] = useState('');
  const [error, setError] = useState('');
  function connect(event) {
    event.preventDefault();
    try { window.location.assign(desktopAddress(address)); }
    catch (reason) { setError(reason.message); }
  }
  return <details className="desktop-connect"><summary>Connect to desktop</summary>
    <form onSubmit={connect}>
      <p>On the same Wi-Fi, enter the address shown under Share on your desktop.</p>
      <label>Desktop address and port<input inputMode="url" autoCapitalize="off" autoCorrect="off" spellCheck={false}
        placeholder="192.168.1.20:3000" value={address} onChange={event => setAddress(event.target.value)} required /></label>
      <button type="submit">Open desktop transcript</button>
      {error && <p role="alert">{error}</p>}
    </form>
  </details>;
}
