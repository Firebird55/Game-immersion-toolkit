'use client';

import { memo, useEffect, useState } from 'react';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';

export type ReadingScope = 'unknown' | 'all' | 'off';
export type ReadingOptions = {
  pinyin: ReadingScope;
  zhuyin: ReadingScope;
  toneMarks: ReadingScope;
  meanings: ReadingScope;
  toneColors: ReadingScope;
  palette: [string, string, string, string, string];
};
export const MIGAKU_TONE_PALETTE: ReadingOptions['palette'] = ['#ff526b', '#ffd34d', '#43cfa1', '#4fa8ff', '#9ca9b7'];
export const DEFAULT_READING_OPTIONS: ReadingOptions = {
  pinyin: 'unknown', zhuyin: 'off', toneMarks: 'off', meanings: 'unknown',
  toneColors: 'all', palette: [...MIGAKU_TONE_PALETTE],
};
export function isReadingScope(value: unknown): value is ReadingScope {
  return value === 'unknown' || value === 'all' || value === 'off';
}
export function restoreReadingOptions(value: unknown): ReadingOptions {
  if (!value || typeof value !== 'object') return { ...DEFAULT_READING_OPTIONS, palette: [...MIGAKU_TONE_PALETTE] };
  const saved = value as Record<string, unknown>;
  const palette = Array.isArray(saved.palette) && saved.palette.length === 5
    && saved.palette.every(color => typeof color === 'string' && /^#[0-9a-f]{6}$/i.test(color))
    ? saved.palette as ReadingOptions['palette'] : [...MIGAKU_TONE_PALETTE] as ReadingOptions['palette'];
  return {
    pinyin: isReadingScope(saved.pinyin) ? saved.pinyin : 'unknown',
    zhuyin: isReadingScope(saved.zhuyin) ? saved.zhuyin : 'off',
    toneMarks: isReadingScope(saved.toneMarks) ? saved.toneMarks : 'off',
    meanings: isReadingScope(saved.meanings) ? saved.meanings : 'unknown',
    toneColors: isReadingScope(saved.toneColors) ? saved.toneColors : 'all',
    palette,
  };
}
type Token = { start: number; end: number; word: string; pinyin: string; zhuyin: string; tones: number[]; proficiency: number; meaning: string; entryId?: number | null };
type Reading = { text: string; tokens: Token[]; pendingMeanings?: boolean };
type Lookup = {
  translations: { meaning: string; partOfSpeech: string[]; examples: { text: string; translation: string }[] }[];
  dictionaries: { name: string; headword: string; reading: string; definitions: string[] }[];
  hskLevel?: number; rank?: number; frequencyScore?: number;
  alternateReadings: string[];
  components: { character: string; type: string[]; hint: string }[];
  characterHint?: string; strokeCount?: number; character?: string;
};
type ContextMeaning = { meaning: string; conciseMeaning: string; reading: string };
type CharacterBreakdown = { partial?: boolean; characters: { character: string; hint: string; strokeCount?: number;
  unavailable?: boolean; components: { character: string; type: string[]; hint: string }[] }[] };
type WordTab = 'definition' | 'translation' | 'context' | 'components';
const API_URL = 'http://127.0.0.1:8766';
const cache = new Map<number, { reading: Reading; at: number }>();
const lookupCache = new Map<string, Lookup>();
const proficiencyOverrides = new Map<number, number>();
function applyOverrides(reading: Reading): Reading {
  return { ...reading, tokens: reading.tokens.map(token => {
    const level = token.entryId == null ? undefined : proficiencyOverrides.get(token.entryId);
    return level == null ? token : { ...token, proficiency: level };
  }) };
}
function cachedReading(id: number, text: string): Reading | null {
  const saved = cache.get(id);
  return saved && saved.reading.text === text && Date.now() - saved.at < 10 * 60_000 ? applyOverrides(saved.reading) : null;
}
function shortGloss(meaning: string) {
  const first = meaning.split(/[,;]/, 1)[0].trim();
  return first.length > 32 ? `${first.slice(0, 29)}…` : first;
}
function enabled(scope: ReadingScope, unknown: boolean) {
  return scope === 'all' || (scope === 'unknown' && unknown);
}
const TONE_MARKS: Record<number, string> = { 1: '¯', 2: 'ˊ', 3: 'ˇ', 4: 'ˋ', 5: '˙' };
function toneStyle(tones: number[], text: string, palette: ReadingOptions['palette']): React.CSSProperties | undefined {
  const first = tones.find(value => value >= 1 && value <= 5);
  if (!first) return undefined;
  if (tones.length !== text.length || tones.length === 1 || tones.some(value => value < 1 || value > 5))
    return { color: palette[first - 1] };
  const stops = tones.map((value, index) =>
    `${palette[value - 1]} ${index * 100 / tones.length}% ${(index + 1) * 100 / tones.length}%`);
  return { backgroundImage: `linear-gradient(90deg, ${stops.join(', ')})`,
    backgroundClip: 'text', WebkitBackgroundClip: 'text', color: 'transparent' };
}

const WORD_LEVELS = [
  { value: 1, short: 'T', label: 'Tracked' },
  { value: 2, short: 'L', label: 'Learning' },
  { value: 3, short: 'F', label: 'Fresh' },
  { value: 4, short: 'K', label: 'Known' },
] as const;

function WordSheet({ id, text, token, lookup, lookupError, onClose, onProficiency, onRetry }: {
  id: number; text: string; token: Token; lookup?: Lookup; lookupError: boolean;
  onClose: () => void; onProficiency: (level: number) => void; onRetry: () => void;
}) {
  const [tab, setTab] = useState<WordTab>('definition');
  const [context, setContext] = useState<ContextMeaning | null>(null);
  const [contextError, setContextError] = useState(false);
  const [characters, setCharacters] = useState<CharacterBreakdown | null>(null);
  const [charactersError, setCharactersError] = useState(false);
  const [saving, setSaving] = useState<number | null>(null);
  const [saveError, setSaveError] = useState('');
  useEffect(() => {
    if (tab !== 'context' || context || contextError) return;
    const controller = new AbortController();
    fetch(`${API_URL}/api/lines/${id}/reading/context?start=${token.start}`,
      { cache: 'no-store', signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error('Context unavailable'); return response.json() as Promise<ContextMeaning>; })
      .then(setContext)
      .catch(() => { if (!controller.signal.aborted) setContextError(true); });
    return () => controller.abort();
  }, [tab, context, contextError, id, token.start]);
  useEffect(() => {
    if (tab !== 'components' || token.word.length === 1 || characters || charactersError) return;
    const controller = new AbortController();
    fetch(`${API_URL}/api/lines/${id}/reading/characters?start=${token.start}`,
      { cache: 'no-store', signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error('Components unavailable'); return response.json() as Promise<CharacterBreakdown>; })
      .then(setCharacters)
      .catch(() => { if (!controller.signal.aborted) setCharactersError(true); });
    return () => controller.abort();
  }, [tab, characters, charactersError, id, token.start, token.word]);
  async function setLevel(level: number) {
    if (saving !== null || level === token.proficiency) return;
    setSaving(level);
    setSaveError('');
    try {
      const response = await fetch(`${API_URL}/api/lines/${id}/reading/proficiency`, {
        method: 'POST', cache: 'no-store',
        headers: { 'Content-Type': 'application/json', 'X-Proxy-Transcript': 'lexirise' },
        body: JSON.stringify({ start: token.start, proficiency: level }),
      });
      if (!response.ok) throw new Error('Lexirise could not save this word. Try again.');
      onProficiency(level);
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : 'Could not save this word.');
    } finally {
      setSaving(null);
    }
  }
  function speak() {
    if (!('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(token.word);
    utterance.lang = 'zh-CN';
    utterance.rate = 0.82;
    const voice = window.speechSynthesis.getVoices().find(value => value.lang.toLowerCase().startsWith('zh'));
    if (voice) utterance.voice = voice;
    window.speechSynthesis.speak(utterance);
  }
  const primary = lookup?.translations.find(value => value.partOfSpeech.length) || lookup?.translations[0];
  return <Dialog open onOpenChange={open => { if (!open) onClose(); }}>
    <DialogContent className="word-sheet" showCloseButton>
      <div className="word-sheet-top">
        <div className="word-sheet-identity">
          <div className="word-sheet-headword"><DialogTitle>{token.word}</DialogTitle>
            <button type="button" className="word-speak" onClick={speak} title="Speak using this device's Chinese voice" aria-label={`Pronounce ${token.word}`}>▶</button>
          </div>
          <div className="word-sheet-reading">{token.pinyin}{lookup?.alternateReadings?.length ? ` · ${lookup.alternateReadings.join(' · ')}` : ''}</div>
          {token.zhuyin && <div className="word-sheet-zhuyin">{token.zhuyin}</div>}
        </div>
        <div className="word-levels" role="group" aria-label="Lexirise vocabulary status">
          {WORD_LEVELS.map(level => <button key={level.value} type="button"
            className={token.proficiency === level.value ? 'active' : ''}
            disabled={saving !== null} onClick={() => void setLevel(level.value)}
            title={level.label} aria-label={`Mark ${token.word} ${level.label}`}
            aria-pressed={token.proficiency === level.value}>{saving === level.value ? '…' : level.short}</button>)}
        </div>
      </div>
      {saveError && <p className="word-sheet-error" role="alert">{saveError}</p>}
      <div className="word-tabs" role="tablist" aria-label="Word details">
        {(['definition', 'translation', 'context', 'components'] as const).map(value =>
          <button key={value} type="button" role="tab" aria-selected={tab === value}
            className={tab === value ? 'active' : ''} onClick={() => setTab(value)}>{value[0].toUpperCase() + value.slice(1)}</button>)}
      </div>
      <div className="word-sheet-body" role="tabpanel">
        {!lookup && !lookupError && (tab === 'definition' || tab === 'translation' || (tab === 'components' && token.word.length === 1)) &&
          <p>{token.meaning || 'Looking up word details…'}<small className="word-loading-note">Loading dictionary details…</small></p>}
        {lookupError && (tab === 'definition' || tab === 'translation' || (tab === 'components' && token.word.length === 1)) &&
          <p>Dictionary details are unavailable. {token.meaning}
          <button type="button" className="word-retry" onClick={onRetry}>Retry dictionary lookup</button></p>}
        {tab === 'definition' && lookup && <>
          <div className="word-definition-lead"><span>{primary?.meaning || token.meaning || 'No definition yet'}</span>
            {primary?.partOfSpeech.length ? <small>{primary.partOfSpeech.join(', ')}</small> : null}</div>
          {lookup.hskLevel != null && <span className="word-hsk">HSK {lookup.hskLevel}</span>}
          {lookup.dictionaries.map((dictionary, index) => <section className="word-dictionary" key={index}>
            <h3>{dictionary.name}</h3>
            <p><strong>{dictionary.headword}</strong> <span>{dictionary.reading}</span></p>
            <ul>{dictionary.definitions.map((meaning, item) => <li key={item}>{meaning}</li>)}</ul>
          </section>)}
          {lookup.rank != null && <div className="word-frequency"><span>Frequency</span>
            {lookup.frequencyScore != null && <span className="word-frequency-bars" aria-label={`Frequency score ${Math.round(lookup.frequencyScore * 100)} percent`}>
              {Array.from({ length: 4 }, (_, index) => <i key={index} className={lookup.frequencyScore! >= (index + 1) / 4 ? 'on' : ''} />)}
            </span>}
            <span>{lookup.rank <= 100 ? 'Very common' : lookup.rank <= 1000 ? 'Common' : `Rank #${lookup.rank}`}</span>
            <span>#{lookup.rank}</span></div>}
        </>}
        {tab === 'translation' && lookup && <div className="word-translations">
          {lookup.translations.length ? lookup.translations.map((entry, index) => <section key={index}>
            <div><strong>{entry.meaning}</strong> {entry.partOfSpeech.length > 0 && <small>{entry.partOfSpeech.join(', ')}</small>}</div>
            {entry.examples.map((example, exampleIndex) => <p key={exampleIndex} lang="zh-Hans">{example.text}<small>{example.translation}</small></p>)}
          </section>) : <p>{token.meaning || 'No English translation available yet.'}</p>}
        </div>}
        {tab === 'context' && <div className="word-context">
          <p lang="zh-Hans">{text}</p>
          {context ? <><strong>{context.conciseMeaning || token.meaning}</strong><p>{context.meaning}</p>
            {context.reading && <small>In this line: {context.reading}</small>}</> :
            <p>{contextError ? <>Context explanation unavailable.
              <button type="button" className="word-retry" onClick={() => setContextError(false)}>Retry context</button></> :
              'Explaining this word in the line…'}</p>}
        </div>}
        {tab === 'components' && <div className="word-components">
          {token.word.length > 1 ? characters ? characters.characters.map((character, charIndex) => <section className="word-character" key={charIndex}>
            <h3>{character.character} {character.strokeCount != null && <small>{character.strokeCount} strokes</small>}</h3>
            {character.hint && <p>{character.hint}</p>}
            {character.unavailable && <p>Character details unavailable right now.</p>}
            {character.components.map((part, index) => <div key={index} className="word-component">
              <strong>{part.character}</strong><span>{part.type.join(', ') || 'Component'}{part.hint && <small>{part.hint}</small>}</span>
            </div>)}
          </section>) : <p>{charactersError ? <>Character details are unavailable.
            <button type="button" className="word-retry" onClick={() => setCharactersError(false)}>Retry components</button></> :
            'Loading character components…'}</p> : lookup && <>
            {lookup.characterHint && <p>{lookup.characterHint}</p>}
            {lookup.strokeCount != null && <small>{lookup.strokeCount} strokes</small>}
            {lookup.components.length ? lookup.components.map((part, index) => <div key={index} className="word-component">
              <strong>{part.character}</strong><span>{part.type.join(', ') || 'Component'}{part.hint && <small>{part.hint}</small>}</span>
            </div>) : <p>Lexirise has no character components for this word.</p>}
          </>}
          {token.word.length > 1 && characters?.partial && <button type="button" className="word-retry"
            onClick={() => setCharacters(null)}>Retry missing characters</button>}
        </div>}
      </div>
    </DialogContent>
  </Dialog>;
}

export const ReadingText = memo(function ReadingText({ id, text, options, current = false }: {
  id: number; text: string; options: ReadingOptions; current?: boolean;
}) {
  const [reading, setReading] = useState<Reading | null>(cachedReading(id, text));
  const [open, setOpen] = useState<number | null>(null);
  const [lookup, setLookup] = useState<{ index: number; value?: Lookup; error?: boolean } | null>(null);
  const [lookupAttempt, setLookupAttempt] = useState(0);
  const [error, setError] = useState(false);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let refreshCount = 0;
    const refreshDelays = [800, 1200, 1800, 2600, 3800, 5600, 8000];
    setOpen(null);
    const saved = cachedReading(id, text);
    setReading(saved);
    async function refresh() {
      try {
        const response = await fetch(`${API_URL}/api/lines/${id}/reading`, { cache: 'no-store' });
        if (!response.ok) throw new Error('Analysis unavailable');
        const result = applyOverrides(await response.json() as Reading);
        if (!active) return;
        cache.set(id, { reading: result, at: Date.now() });
        setReading(result);
        setError(false);
        if (result.pendingMeanings && refreshCount < refreshDelays.length) {
          timer = setTimeout(refresh, refreshDelays[refreshCount++]);
        }
      } catch {
        if (active) setError(true);
      }
    }
    if (!saved || saved.pendingMeanings) void refresh();
    const onChange = () => setReading(previous => previous ? applyOverrides(previous) : previous);
    window.addEventListener('lexirise-word-state', onChange);
    return () => { active = false; if (timer) clearTimeout(timer); window.removeEventListener('lexirise-word-state', onChange); };
  }, [id, text]);
  useEffect(() => {
    if (open === null || !reading || reading.text !== text) return;
    const token = reading.tokens[open];
    if (!token) return;
    const key = `${id}:${token.start}`;
    const saved = lookupCache.get(key);
    if (saved) { setLookup({ index: open, value: saved }); return; }
    let active = true;
    setLookup({ index: open });
    fetch(`${API_URL}/api/lines/${id}/reading/lookup?start=${token.start}`, { cache: 'no-store' })
      .then(response => { if (!response.ok) throw new Error('Lookup unavailable'); return response.json() as Promise<Lookup>; })
      .then(value => { lookupCache.set(key, value); if (active) setLookup({ index: open, value }); })
      .catch(() => { if (active) setLookup({ index: open, error: true }); });
    return () => { active = false; };
  }, [id, open, reading, text, lookupAttempt]);

  function onProficiency(level: number) {
    if (!reading || open === null) return;
    const entryId = reading.tokens[open]?.entryId;
    if (entryId == null) return;
    proficiencyOverrides.set(entryId, level);
    for (const [lineId, saved] of cache) cache.set(lineId, { ...saved, reading: applyOverrides(saved.reading) });
    window.dispatchEvent(new Event('lexirise-word-state'));
  }

  if (!reading || reading.text !== text) return <p className={current ? 'current-chinese' : undefined} lang="zh-Hans" title={error ? 'Lexirise analysis unavailable' : 'Analyzing with Lexirise'}>{text}</p>;
  const parts: React.ReactNode[] = [];
  let cursor = 0;
  for (const [index, token] of reading.tokens.entries()) {
    if (token.start < cursor || token.end > text.length) continue;
    if (token.start > cursor) parts.push(text.slice(cursor, token.start));
    const unknown = token.proficiency < 4;
    const wordText = text.slice(token.start, token.end);
    const colorStyle = enabled(options.toneColors, unknown)
      ? toneStyle(token.tones || [], wordText, options.palette) : undefined;
    const toneMarks = token.tones?.map(value => TONE_MARKS[value] || '').filter(Boolean).join(' ');
    parts.push(<span key={`${token.start}-${index}`} className="reading-token">
      {enabled(options.toneMarks, unknown) && !!toneMarks && <span className="reading-tone-marks" aria-hidden="true">{toneMarks}</span>}
      {enabled(options.pinyin, unknown) && !!token.pinyin && <span className="reading-pinyin" aria-hidden="true">{token.pinyin}</span>}
      {enabled(options.zhuyin, unknown) && !!token.zhuyin && <span className="reading-zhuyin" aria-hidden="true">{token.zhuyin}</span>}
      <span className="reading-hanzi" role="button" tabIndex={0}
        onClick={() => setOpen(index)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setOpen(index); } }}
        style={colorStyle} title={token.meaning || 'Tap for word details'}>{wordText}</span>
      {enabled(options.meanings, unknown) && !!token.meaning && <span className="reading-meaning">{shortGloss(token.meaning)}</span>}
    </span>);
    cursor = token.end;
  }
  if (cursor < text.length) parts.push(text.slice(cursor));
  const selected = open === null ? null : reading.tokens[open];
  return <><p className={`reading-text ${current ? 'current-chinese' : ''}`} lang="zh-Hans">{parts}</p>
    {selected && <WordSheet key={`${id}:${selected.start}`} id={id} text={text} token={selected}
      lookup={lookup?.index === open ? lookup.value : undefined} lookupError={lookup?.index === open && !!lookup.error}
      onClose={() => setOpen(null)} onProficiency={onProficiency}
      onRetry={() => { setLookup(null); setLookupAttempt(value => value + 1); }} />}</>;
});
