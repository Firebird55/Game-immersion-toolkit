'use client';

import {useEffect, useRef, useState} from 'react';
import catalog from '../public/mobile-capture/games-data.json';
import {useInterfaceLanguage} from '@/lib/interface-language';
import {languageName} from '../public/mobile-capture/interface-language.mjs';

const API = 'http://127.0.0.1:8766';
const baseLanguage = (code: string) => code.toLowerCase().split('-')[0];
export const voicedLanguages = [...new Set(catalog.games.flatMap(game => game.audio.map(baseLanguage)))];
export const gamesForLanguage = (language: string) => catalog.games.filter(game => game.audio.some(code => baseLanguage(code) === language));

type Preferences = {languages: string[]};
async function preferences(account: string, signal: AbortSignal, languages?: string[]): Promise<Preferences> {
  const response = await fetch(API + '/api/lexirise/settings', {
    method: languages ? 'PATCH' : 'GET', cache: 'no-store', signal,
    headers: {'Content-Type': 'application/json', 'X-Proxy-Transcript': 'lexirise', 'X-Proxy-Transcript-Account': account},
    ...(languages ? {body: JSON.stringify({languages})} : {}),
  });
  const value = await response.json() as {detail?: unknown; languages?: unknown};
  if (!response.ok) throw Error(typeof value.detail === 'string' ? value.detail : 'Could not load Lexirise languages.');
  if (!Array.isArray(value.languages) || !value.languages.every((code: unknown) => typeof code === 'string')) throw Error('Could not load Lexirise languages.');
  return {languages: value.languages as string[]};
}

export function useTargetLanguage(mode: 'lexirise' | 'migaku', account?: string, configured = false) {
  const [loaded, setLoaded] = useState<{account: string; languages: string[]} | null>(null);
  const [selection, setSelection] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const owner = useRef<AbortController | null>(null);
  const addingRequest = useRef<AbortController | null>(null);
  const lexirise = mode === 'lexirise';
  const scope = lexirise ? `lexirise:${account ?? ''}` : 'migaku';
  const languages = lexirise ? configured && loaded && loaded.account === account ? loaded.languages : [] : voicedLanguages;
  const target = languages.includes(selection[scope]) ? selection[scope] : languages.includes('zh') ? 'zh' : languages[0] ?? '';
  const select = (code: string) => setSelection(previous => ({...previous, [scope]: code}));

  useEffect(() => {
    const reset = () => {owner.current?.abort(); setLoaded(null); setRevision(value => value + 1);};
    window.addEventListener('lexirise-credentials-changed', reset);
    window.addEventListener('lexirise-account-settings', reset);
    window.addEventListener('companion-runtime-reset', reset);
    return () => {
      window.removeEventListener('lexirise-credentials-changed', reset);
      window.removeEventListener('lexirise-account-settings', reset);
      window.removeEventListener('companion-runtime-reset', reset);
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    owner.current = controller;
    // Clear the old request's UI immediately when its account or generation changes.
    // oxlint-disable-next-line react/react-compiler
    setLoaded(null); setError(''); setBusy(false);
    if (lexirise && account && configured) {
      void preferences(account, controller.signal).then(value => {
        if (!controller.signal.aborted) setLoaded({account, languages: value.languages});
      }).catch(error => {if (!controller.signal.aborted) setError(error.message);});
    }
    return () => controller.abort();
  }, [lexirise, account, configured, revision]);

  async function addLanguage(code: string) {
    const controller = owner.current;
    if (!lexirise || !account || !configured || !controller || controller.signal.aborted || addingRequest.current === controller || !voicedLanguages.includes(code)) return;
    addingRequest.current = controller;
    setBusy(true); setError('');
    try {
      // Re-read before appending so settings edited elsewhere are preserved.
      const current = await preferences(account, controller.signal);
      if (controller.signal.aborted) return;
      const result = current.languages.includes(code) ? current : await preferences(account, controller.signal, [...current.languages, code]);
      if (controller.signal.aborted) return;
      setLoaded({account, languages: result.languages}); select(code);
      window.dispatchEvent(new Event('lexirise-account-settings'));
    } catch (error) {
      if (!controller.signal.aborted) setError(error instanceof Error ? error.message : 'Could not add language.');
    } finally {if (addingRequest.current === controller) addingRequest.current = null; if (!controller.signal.aborted) setBusy(false);}
  }
  return {target, select, languages, games: gamesForLanguage(target), error, busy, addLanguage,
    ready: configured && !!loaded && loaded.account === account,
    loading: lexirise && configured && !!account && loaded?.account !== account && !error,
    reload: () => setRevision(value => value + 1)};
}

export function GamePicker({picker, mode, selectedGame, onGameChange, sourceLocale}: {
  picker: ReturnType<typeof useTargetLanguage>; mode: 'lexirise' | 'migaku'; selectedGame: string;
  onGameChange: (game: string) => void; sourceLocale?: string;
}) {
  const {t, locale} = useInterfaceLanguage();
  const [search, setSearch] = useState('');
  const [adding, setAdding] = useState(false);
  const [addition, setAddition] = useState('');
  const available = voicedLanguages.filter(code => !picker.languages.includes(code));
  const sorted = (codes: string[]) => [...codes].sort((a, b) => languageName(a, locale).localeCompare(languageName(b, locale), locale));
  const games = picker.games.filter(game => game.name.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()));
  const selected = picker.games.find(game => game.id === selectedGame);
  const add = available.includes(addition) ? addition : sorted(available)[0] ?? '';
  return <section className="game-picker" aria-label={t('Games and target language')}>
    <div className="game-picker-toolbar">
      <label>{t('Game')}<select aria-label={t('Game')} value={selectedGame} onChange={event=>onGameChange(event.target.value)}>{!selected&&<option value={selectedGame}>{selectedGame}</option>}{picker.games.map(game=><option key={game.id} value={game.id}>{game.name}</option>)}</select></label>
      <label>{t('Target language')}<select aria-label={t('Target language')} value={picker.target} disabled={!picker.languages.length || picker.busy} onChange={event => picker.select(event.target.value)}>
        {!picker.languages.length && <option value="">{t(picker.loading ? 'Loading languages…' : 'No account languages available')}</option>}
        {sorted(picker.languages).map(code => <option key={code} value={code}>{languageName(code, locale)}</option>)}
      </select></label>

      {mode === 'lexirise' && <button type="button" className="reader-options-button" onClick={picker.reload} disabled={picker.busy}>{t('Reload languages')}</button>}
      {mode === 'lexirise' && picker.ready && !!available.length && <button type="button" className="reader-options-button" aria-expanded={adding} onClick={() => setAdding(!adding)}>{t('Add language to Lexirise')}</button>}
    </div>
    {mode === 'lexirise' && adding && picker.ready && !!available.length && <div className="game-picker-add">
      <label>{t('Language to add')}<select aria-label={t('Language to add')} disabled={picker.busy} value={add} onChange={event => setAddition(event.target.value)}>{sorted(available).map(code => <option key={code} value={code}>{languageName(code, locale)}</option>)}</select></label>
      <button type="button" className="secondary-button" disabled={picker.busy || !add} onClick={() => void picker.addLanguage(add)}>{t(picker.busy ? 'Saving…' : 'Add to my Lexirise account')}</button>
      <p>{t('Adds this learning language to the active account and keeps your existing languages.')}</p>
    </div>}
    {picker.error && <p role="alert">{picker.error}</p>}
    <details className="game-library"><summary>{t('Browse games and supported languages')} <span>({picker.games.length})</span></summary>
      <label>{t('Search games')}<input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder={t('Search games')} /></label>
    <div className="game-picker-heading"><strong>{t('Supported games')} <span>({games.length})</span></strong><small>{t('Filtered by original voice language')}</small></div>
    <nav className="game-card-list" aria-label={t('Game transcript')}>
      {games.map(game => <button key={game.id} type="button" aria-label={game.name} className={'game-choice ' + (game.id === selectedGame ? 'is-active' : '')} aria-pressed={game.id === selectedGame} onClick={() => onGameChange(game.id)}>
        <strong>{game.name}</strong><span>{game.audio.filter(code => baseLanguage(code) === picker.target).map(code => languageName(code, locale)).join(' · ')}</span>
      </button>)}
    </nav>
    {!games.length && !picker.loading && <output>{t(picker.target ? 'No supported games match this language and search.' : 'Choose an account language to browse games.')}</output>}
    {selected && <div className="game-subtitles">
      <strong>{selected.name} · {t('Supported subtitles')}</strong>
      <ul>{selected.targets.map(code => <li key={code} className={baseLanguage(code) === picker.target ? 'matches-target' : ''}>{languageName(code, locale)}{baseLanguage(code) !== picker.target && <small> · {t('Different from target')}</small>}{sourceLocale && <small> · {t(code.toLowerCase() === sourceLocale.toLowerCase() ? 'Current source' : 'Different from source')}</small>}</li>)}</ul>
      <p>{t('Different subtitle and account languages are allowed. Choose and prepare your source language in Settings → Games & Languages.')}</p>
      {sourceLocale && baseLanguage(sourceLocale) !== picker.target && <output>{t('Current source differs from target')}: {languageName(sourceLocale, locale)}. {t('Browsing games does not change your prepared language.')}</output>}
    </div>}
    </details>
  </section>;
}
