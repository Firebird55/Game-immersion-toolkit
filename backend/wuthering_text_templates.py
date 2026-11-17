"""Exact original PlotTextReplacer PlayerName slots with substantial fixed text."""
import re

from .languages import normalize_text
from .textmaps import display_text

_SLOT = '{PlayerName}'
_MAX_NAME = 32  # Conservative OCR admission bound, not a claim about account policy.


def _parts(value, locale):
    if not isinstance(value, str) or value.count(_SLOT) != 1:
        return None
    first, last = display_text(value).split(_SLOT)
    # Other native replacement grammars need their own proof.
    if any(char in first + last for char in '{}'):
        return None
    fixed = normalize_text(first + last, locale)
    minimum = 6 if re.search(r'[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]', fixed) else 12
    return (first, last) if len(fixed) >= minimum else None


class PlayerNameTemplates:
    def __init__(self, records):
        found = {}
        for row in records:
            for locale, text in row['texts'].items():
                for value in [text, *row.get('ocr_texts', {}).get(locale, [])]:
                    parts = _parts(value, locale)
                    if parts is None:
                        continue
                    first, last = parts
                    item = (normalize_text(first, locale), normalize_text(last, locale),
                            normalize_text(display_text(value), locale))
                    found.setdefault(locale, set()).add(item)
        self.locales = {locale: tuple(items) for locale, items in found.items()}

    def keys(self, normalized, locale):
        result = set()
        for first, last, canonical in self.locales.get(locale, ()):
            if (normalized.startswith(first) and normalized.endswith(last)
                    and 1 <= len(normalized) - len(first) - len(last) <= _MAX_NAME):
                result.add(canonical)
        return result


def present_player_name(line):
    """Render one owned raw nickname on a DTO, never on canonical stored rows.

    Matching may discard punctuation or normalize Unicode. Presentation cannot
    reverse that operation to invent a name. Require a unique raw word span and
    the exact official surrounding characters, allowing only OCR space gaps.
    More complex names/folds keep the original token rather than a guessed name.
    """
    if line.game != 'wuwa' or line.match_kind != 'exact' or line.ambiguous or _SLOT in line.source_ocr:
        return line
    spans = set()
    templates = [*line.texts.items(), (line.source_locale, line.source_text)]
    for locale, text in templates:
        parts = _parts(text, locale)
        if parts is None:
            continue
        # Do not strip observed punctuation, markup, or expand Unicode folds.
        first, last = (r'\s*'.join(re.escape(char) for char in part if not char.isspace())
                       for part in parts)
        matched = re.fullmatch(r'\s*' + first + r'\s*(\w{1,32})\s*' + last + r'\s*', line.source_ocr)
        if matched and 1 <= len(normalize_text(matched[1], locale)) <= _MAX_NAME:
            spans.add((matched.start(1), matched.end(1)))
    if len(spans) != 1:
        return line
    start, end = next(iter(spans))
    name = line.source_ocr[start:end]

    def render(text):
        if not isinstance(text, str) or text.count(_SLOT) != 1:
            return text
        first, last = text.split(_SLOT)
        return text if any(char in first + last for char in '{}') else first + name + last

    fields = ('source_text', 'translation_text', 'english', 'chinese')
    return line.model_copy(update={**{key: render(getattr(line, key)) for key in fields},
        'texts': {locale: render(text) for locale, text in line.texts.items()}})
