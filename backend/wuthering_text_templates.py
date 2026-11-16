"""Exact original PlotTextReplacer PlayerName slots with substantial fixed text."""
import re

from .languages import normalize_text
from .textmaps import display_text

_SLOT = '{PlayerName}'
_MAX_NAME = 32  # Conservative OCR admission bound, not a claim about account policy.


class PlayerNameTemplates:
    def __init__(self, records):
        found = {}
        for row in records:
            for locale, text in row['texts'].items():
                for value in [text, *row.get('ocr_texts', {}).get(locale, [])]:
                    if not isinstance(value, str) or value.count(_SLOT) != 1:
                        continue
                    first, last = display_text(value).split(_SLOT)
                    # Other native replacement grammars need their own proof.
                    if any(char in first + last for char in '{}'):
                        continue
                    fixed = normalize_text(first + last, locale)
                    minimum = 6 if re.search(r'[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]', fixed) else 12
                    if len(fixed) < minimum:
                        continue
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
