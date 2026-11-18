'use client';

import {useEffect, useRef, useState, type FormEvent} from 'react';
import {desktopApiBase} from '../lib/desktop-endpoints';
import {useInterfaceTranslation} from '../lib/interface-language';
import {Input} from '../components/ui/input';
import {useNativeAccountGeneration} from '../lib/native-account-context';
import {nativeAccountHeaders} from '../lib/native-account-scope.mjs';

const API = desktopApiBase() + '/api/lexirise/accounts';
const headers = {'Content-Type': 'application/json', 'X-Proxy-Transcript': 'lexirise'};
type Accounts = {active: string; profiles: {id: string; name: string}[];
  recovery?: {state: string; action: string; message: string} | null};

async function accountResponse(response: Response, failure: string): Promise<Accounts> {
  if (!response.ok) {
    const error = await response.json().catch(() => null) as {detail?: unknown} | null;
    throw Error(typeof error?.detail === 'string' ? error.detail : failure);
  }
  return response.json();
}

async function readAccounts(generation?: number | null): Promise<Accounts> {
  const response = await fetch(API, {cache: 'no-store', headers: nativeAccountHeaders(generation)});
  if (!response.ok) throw Error('Could not load saved accounts.');
  const data = await response.json() as Partial<Accounts>;
  return {active: data.active ?? 'legacy', profiles: data.profiles ?? [], recovery: data.recovery};
}

export function AccountSwitcher({onChanged}: {onChanged: () => void}) {
  const accountGeneration = useNativeAccountGeneration();
  const mounted = useRef(true);
  const uiText = useInterfaceTranslation();
  const [accounts, setAccounts] = useState<Accounts>({active: 'legacy', profiles: []});
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(true);
  const [message, setMessage] = useState('');
  const keyInput = useRef<HTMLInputElement>(null);
  const nameInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    mounted.current = true;
    let current = true;
    readAccounts(accountGeneration).then(data => {
      if (current) {setAccounts(data); setAdding(!!data.recovery);}
    }).catch(() => {
      if (current) setMessage('Could not load saved accounts.');
    }).finally(() => {
      if (current) setBusy(false);
    });
    return () => { current = false; mounted.current = false; };
  }, [accountGeneration]);

  function changed(data: Accounts) {
    if (!mounted.current) return;
    setAccounts(data);
    window.dispatchEvent(new Event('lexirise-credentials-changed'));
    onChanged();
  }

  async function reload() {
    setBusy(true);
    setMessage('');
    try {
      changed(await readAccounts(accountGeneration));
    } catch {
      setMessage('Could not reload accounts.');
    } finally {
      setBusy(false);
    }
  }

  async function select(id: string) {
    setBusy(true);
    setMessage('');
    try {
      const response = await fetch(API + '/select', {method: 'POST', headers: nativeAccountHeaders(accountGeneration, headers), body: JSON.stringify({id})});
      changed(await accountResponse(response, 'Could not switch accounts.'));
      setMessage('Selected account loaded.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not switch accounts.');
    } finally {
      setBusy(false);
    }
  }

  function openForm() {
    if (!['localhost', '127.0.0.1'].includes(window.location.hostname)) {
      setMessage('Open account settings on the desktop PC to add an account.');
      return;
    }
    setMessage('');
    setAdding(true);
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const input = keyInput.current;
    if (busy || !input?.value) return;
    const body = JSON.stringify({key: input.value.trim(), name: nameInput.current?.value.trim()});
    input.value = '';
    setBusy(true);
    setMessage('Verifying account…');
    try {
      const response = await fetch(API + (accounts.recovery ? '/recover' : ''), {method: 'POST', headers: nativeAccountHeaders(accountGeneration, headers), body, cache: 'no-store', redirect: 'error'});
      const data = await accountResponse(response, 'Could not save the account.');
      setAdding(false);
      changed(data);
      setMessage('Account saved and selected.');
    } catch (error) {
      setMessage(error instanceof Error && !(error instanceof TypeError) ? error.message
        : 'Could not confirm the save. Reload accounts to check.');
    } finally {
      setBusy(false);
    }
  }

  return <fieldset className="settings-key">
    <legend>{accountGeneration === undefined ? uiText('Lexirise accounts on this PC') : 'Lexirise accounts on this device'}</legend>
    {accounts.recovery ? <p role="alert">{accounts.recovery.message}</p> : <label className="account-selection">{uiText('Active account')}
      <select aria-label={uiText('Active Lexirise account')} value={accounts.active} disabled={busy || adding}
        onChange={event => void select(event.target.value)}>
        <option value="legacy">{accountGeneration === undefined ? uiText('Existing local credential') : 'Local library without an account'}</option>
        {accounts.profiles.map(profile => <option key={profile.id} value={profile.id}>{profile.name}</option>)}
      </select>
    </label>}
    {adding ? <form className="account-entry" autoComplete="off" onSubmit={save}>
      <label>{uiText('Lexirise API key')}
        <Input ref={keyInput} type="password" autoFocus required maxLength={512} autoComplete="off"
          spellCheck={false} autoCapitalize="none" disabled={busy}/>
      </label>
      <label>{uiText('Account label (optional)')}
        <Input ref={nameInput} maxLength={80} disabled={busy}/>
      </label>
      <div className="settings-key-actions">
        <button type="submit" disabled={busy}>{accounts.recovery ? 'Verify and restore local data' : uiText('Verify and save')}</button>
        <button type="button" disabled={busy} onClick={() => { setAdding(false); setMessage(''); }}>{uiText('Cancel')}</button>
      </div>
    </form> : <div className="settings-key-actions">
      <button type="button" disabled={busy} onClick={openForm}>{accounts.recovery ? 'Recover account securely' : uiText('Add account securely')}</button>
      <button type="button" disabled={busy} onClick={() => void reload()}>{uiText('Reload accounts')}</button>
    </div>}
    <p role="status">{uiText(message)}</p>
    <small>{accountGeneration === undefined ? uiText('Keys remain encrypted on this PC. Switching does not change Lexirise settings or create decks.') : 'Keys remain protected on this device. Switching keeps each account’s library and history separate.'}</small>
  </fieldset>;
}
