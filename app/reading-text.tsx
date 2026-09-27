'use client';

import { memo, useEffect, useState } from 'react';

export type PinyinMode = 'unknown' | 'all' | 'off';
type Token = { start: number; end: number; word: string; pinyin: string; proficiency: number; meaning: string };
type Reading = { text: string; tokens: Token[] };
const API_URL = 'http://127.0.0.1:8766';
const cache = new Map<number, { reading: Reading; at: number }>();
function cachedReading(id: number, text: string): Reading | null {
  const saved = cache.get(id);
  return saved && saved.reading.text === text && Date.now() - saved.at < 10 * 60_000 ? saved.reading : null;
}
function shortGloss(meaning: string) {
  const first = meaning.split(/[,;]/, 1)[0].trim();
  return first.length > 32 ? `${first.slice(0, 29)}…` : first;
}

export const ReadingText = memo(function ReadingText({ id, text, pinyin, current = false }: {
  id: number; text: string; pinyin: PinyinMode; current?: boolean;
}) {
  const [reading, setReading] = useState<Reading | null>(cachedReading(id, text));
  const [open, setOpen] = useState<number | null>(null);
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

  if (!reading || reading.text !== text) return <p className={current ? 'current-chinese' : undefined} lang="zh-Hans" title={error ? 'Lexirise analysis unavailable' : 'Analyzing with Lexirise'}>{text}</p>;
  const parts: React.ReactNode[] = [];
  let cursor = 0;
  for (const [index, token] of reading.tokens.entries()) {
    if (token.start < cursor || token.end > text.length) continue;
    if (token.start > cursor) parts.push(text.slice(cursor, token.start));
    const unknown = token.proficiency < 4;
    const showPinyin = pinyin === 'all' || (pinyin === 'unknown' && unknown);
    parts.push(<span key={`${token.start}-${index}`} className={`reading-token level-${token.proficiency}`}>
      {showPinyin && !!token.pinyin && <span className="reading-pinyin" aria-hidden="true">{token.pinyin}</span>}
      <span className="reading-hanzi" onClick={() => setOpen(open === index ? null : index)}
        title={token.meaning || 'Tap for word details'}>{text.slice(token.start, token.end)}</span>
      {unknown && !!token.meaning && <span className="reading-meaning">{shortGloss(token.meaning)}</span>}
      {open === index && <span className="reading-popover" role="status">
        <strong>{token.word}</strong>{token.pinyin && <span>{token.pinyin}</span>}
        <span>{token.meaning || 'No dictionary meaning available yet'}</span>
        <small>Level {token.proficiency} · Select text for Yomitan</small>
      </span>}
    </span>);
    cursor = token.end;
  }
  if (cursor < text.length) parts.push(text.slice(cursor));
  return <p className={`reading-text ${current ? 'current-chinese' : ''}`} lang="zh-Hans">{parts}</p>;
});
