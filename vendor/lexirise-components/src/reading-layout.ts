/** Source word boundaries only affect line wrapping, never token lookup offsets. */
export function readingWordRanges(text: string): { start: number; end: number }[] {
  // These scripts use spaces between words. CJK/Thai keep their existing token
  // wrap opportunities, including mixed sentences with embedded Latin words.
  const letter = '(?=[\\p{L}\\p{N}])[\\p{Script=Latin}\\p{Script=Cyrillic}\\p{Script=Greek}\\p{Script=Arabic}\\p{Script=Devanagari}\\p{Script=Tamil}\\p{Script=Hangul}\\p{N}]\\p{M}*';
  const words = new RegExp(`(?:${letter})+(?:['’‐‑-](?:${letter})+)*[.,!?;:…。，！？、；：”’»）)\\]}]*`, 'gu');
  return [...text.matchAll(words)].map(match => ({ start: match.index!, end: match.index! + match[0].length }));
}

/** Keep original provider spans intact and attach closing punctuation to them. */
export function readingWrapRanges(text: string, tokens: readonly { start: number; end: number }[]) {
  const ranges = readingWordRanges(text);
  for (const token of tokens) {
    const punctuation = text.slice(token.end).match(/^[\p{Pe}\p{Pf}.,!?;:…。，！？、；："']+/u)?.[0].length ?? 0;
    const end = token.end + punctuation;
    const overlaps = ranges.filter(range => range.start < end && range.end > token.start);
    if (overlaps.length) {
      overlaps[0].start = Math.min(overlaps[0].start, token.start);
      overlaps[0].end = Math.max(end, overlaps.at(-1)!.end);
      for (const extra of overlaps.slice(1)) ranges.splice(ranges.indexOf(extra), 1);
    } else if (punctuation) ranges.push({ start: token.start, end });
    ranges.sort((a, b) => a.start - b.start);
  }
  return ranges;
}
