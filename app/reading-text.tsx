'use client';

import { memo, useEffect, useState } from 'react';

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
type Token = { start: number; end: number; word: string; pinyin: string; zhuyin: string; tones: number[]; proficiency: number; meaning: string };
type Reading = { text: string; tokens: Token[] };
type Lookup = { translations: { meaning: string; examples: { text: string; translation: string }[] }[] };
const API_URL = 'http://127.0.0.1:8766';
const cache = new Map<number, { reading: Reading; at: number }>();
const lookupCache = new Map<string, Lookup>();
function cachedReading(id: number, text: string): Reading | null {
  const saved = cache.get(id);
  return saved && saved.reading.text === text && Date.now() - saved.at < 10 * 60_000 ? saved.reading : null;
}
function shortGloss(meaning: string) {
  const first = meaning.split(/[,;]/, 1)[0].trim();
  return first.length > 32 ? `${first.slice(0, 29)}…` : first;
}
function enabled(scope: ReadingScope, unknown: boolean) {
  return scope === 'all' || (scope === 'unknown' && unknown);
}
const TONE_MARKS: Record<number, string> = { 1: '¯', 2: 'ˊ', 3: 'ˇ', 4: 'ˋ', 5: '˙' };

export const ReadingText = memo(function ReadingText({ id, text, options, current = false }: {
  id: number; text: string; options: ReadingOptions; current?: boolean;
}) {
  const [reading, setReading] = useState<Reading | null>(cachedReading(id, text));
  const [open, setOpen] = useState<number | null>(null);
  const [lookup, setLookup] = useState<{ index: number; value?: Lookup; error?: boolean } | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let active = true;
    setOpen(null);
    const saved = cachedReading(id, text);
    setReading(saved);
    if (saved) return;
    fetch(`${API_URL}/api/lines/${id}/reading`, { cache: 'no-store' })
      .then(response => { if (!response.ok) throw new Error('Analysis unavailable'); return response.json() as Promise<Reading>; })
      .then(result => { cache.set(id, { reading: result, at: Date.now() }); if (active) { setReading(result); setError(false); } })
      .catch(() => { if (active) setError(true); });
    return () => { active = false; };
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
  }, [id, open, reading, text]);

  if (!reading || reading.text !== text) return <p className={current ? 'current-chinese' : undefined} lang="zh-Hans" title={error ? 'Lexirise analysis unavailable' : 'Analyzing with Lexirise'}>{text}</p>;
  const parts: React.ReactNode[] = [];
  let cursor = 0;
  for (const [index, token] of reading.tokens.entries()) {
    if (token.start < cursor || token.end > text.length) continue;
    if (token.start > cursor) parts.push(text.slice(cursor, token.start));
    const unknown = token.proficiency < 4;
    const tone = token.tones?.find(value => value >= 1 && value <= 5);
    const color = enabled(options.toneColors, unknown) && tone ? options.palette[tone - 1] : undefined;
    const toneMarks = token.tones?.map(value => TONE_MARKS[value] || '').filter(Boolean).join(' ');
    parts.push(<span key={`${token.start}-${index}`} className="reading-token">
      {enabled(options.toneMarks, unknown) && !!toneMarks && <span className="reading-tone-marks" aria-hidden="true">{toneMarks}</span>}
      {enabled(options.pinyin, unknown) && !!token.pinyin && <span className="reading-pinyin" aria-hidden="true">{token.pinyin}</span>}
      {enabled(options.zhuyin, unknown) && !!token.zhuyin && <span className="reading-zhuyin" aria-hidden="true">{token.zhuyin}</span>}
      <span className="reading-hanzi" onClick={() => setOpen(open === index ? null : index)}
        style={color ? { color } : undefined} title={token.meaning || 'Tap for word details'}>{text.slice(token.start, token.end)}</span>
      {enabled(options.meanings, unknown) && !!token.meaning && <span className="reading-meaning">{shortGloss(token.meaning)}</span>}
      {open === index && <span className="reading-popover" role="status">
        <strong>{token.word}</strong>{token.pinyin && <span>{token.pinyin}</span>}
        {token.zhuyin && <span>{token.zhuyin}</span>}
        {lookup?.index === index && lookup.value?.translations.length ? lookup.value.translations.map((entry, entryIndex) =>
          <span key={entryIndex} className="reading-lookup-entry">
            <span>{entry.meaning}</span>
            {entry.examples.map((example, exampleIndex) => <small key={exampleIndex}>
              {example.text}{example.translation && <> · {example.translation}</>}
            </small>)}
          </span>) : <span>{token.meaning || (lookup?.index === index && !lookup.error ? 'Looking up…' : 'No dictionary meaning available yet')}</span>}
        {lookup?.index === index && lookup.error && <small>Dictionary details unavailable; showing the analysis gloss.</small>}
        <small>Level {token.proficiency} · Select text for Yomitan</small>
      </span>}
    </span>);
    cursor = token.end;
  }
  if (cursor < text.length) parts.push(text.slice(cursor));
  return <p className={`reading-text ${current ? 'current-chinese' : ''}`} lang="zh-Hans">{parts}</p>;
});
