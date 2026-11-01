"""Keep authored display pages separate from translation and audio alignment.

A page's local identity is not necessarily a cross-language cue key. Anonymous
separators and repeated cue keys preserve the visible text without pretending
that ordinal position establishes a translated page or a recording interval.
"""
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class SubtitlePage:
    identity: str
    text: str
    alignment_key: str | None = None


def anonymous_pages(text, separator, clean):
    parts = text.split(separator)
    if len(parts) == 1:
        value = clean(text)
        return [SubtitlePage('complete', value, 'complete')] if value else []
    return [SubtitlePage(f'page:{index + 1}', value)
            for index, part in enumerate(parts) if (value := clean(part))]


def keyed_pages(text, marker, clean):
    matches = list(marker.finditer(text))
    if not matches:
        value = clean(text)
        return [SubtitlePage('complete', value, 'complete')] if value else []
    counts = Counter(match[1] for match in matches)
    occurrences = Counter()
    result = []
    if value := clean(text[:matches[0].start()]):
        result.append(SubtitlePage('prefix', value))
    for index, match in enumerate(matches):
        key = match[1]
        occurrences[key] += 1
        value = clean(text[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(text)])
        if value:
            unique = counts[key] == 1
            result.append(SubtitlePage(key if unique else f'{key}:page:{occurrences[key]}',
                                       value, key if unique else None))
    return result


def aligned_texts(page, source_locale, localized_pages):
    """Join only unique authored cue keys; always retain this exact source page."""
    texts = {source_locale: page.text}
    if page.alignment_key is not None:
        for locale, pages in localized_pages.items():
            candidates = [value.text for value in pages if value.alignment_key == page.alignment_key]
            if locale != source_locale and len(candidates) == 1:
                texts[locale] = candidates[0]
    return texts
