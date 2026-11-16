"""Render NTE's authored protagonist text before removing display markup."""
import html
import re

from .textmaps import display_text


BRANCH = re.compile(r'<(male|female)=>(.*?)<\1>', re.S)
FUNCTION = re.compile(r'\{Gender\}\|gender\(([^()]*)\)')


def player_variants(value):
    raw = html.unescape(value)
    conditional = any(token in raw.lower() for token in ('<male', '<female', '|gender(', '{gender}'))
    if not conditional:
        return {None: display_text(raw)}
    result = {}
    for gender, position in [('female', 1), ('male', 0)]:
        def branch(match):
            if any(token in match[2].lower() for token in ('<male', '<female')):
                raise ValueError('Unsupported nested NTE protagonist text')
            return match[2] if match[1] == gender else ''
        def function(match):
            choices = match[1].split(',')
            if len(choices) != 2:
                raise ValueError('Unsupported NTE protagonist text arguments')
            return choices[position]
        text = FUNCTION.sub(function, BRANCH.sub(branch, raw))
        if any(token in text.lower() for token in ('<male', '<female', '|gender(', '{gender}')):
            raise ValueError('Unsupported NTE protagonist text')
        result[gender] = display_text(text)
    return result


def localized_records(records, tables, source_locale):
    """Keep voice conditions and text conditions independent, then join them."""
    result = []
    for record in records:
        namespace, key = record['text_id'].split(':', 2)[1:]
        selected = record.get('player_voice')
        if selected:
            key = key.removesuffix(':' + selected)
        variants, raw = {}, {}
        for locale, table in tables.items():
            if (namespace, key) not in table:
                continue
            raw[locale] = table[namespace, key]
            try:
                variants[locale] = player_variants(raw[locale])
            except ValueError:
                # An unsupported target is omitted, never borrowed from another
                # gender or language. A source failure disables its recording.
                pass
        conditional = any(len(set(values.values())) > 1 for values in variants.values())
        branches = [selected] if selected else ['female', 'male'] if conditional else [None]
        for gender in branches:
            texts = {}
            for locale, values in variants.items():
                text = values.get(gender, values.get(None))
                if gender is None and text is None and len(set(values.values())) == 1:
                    text = next(iter(values.values()))
                if text:
                    texts[locale] = text
            row = {**record}
            unresolved = sorted(locale for locale in raw if locale not in texts)
            if unresolved:
                row['unresolved_text_locales'] = unresolved
            if gender and not selected:
                row.update(text_id=record['text_id'] + ':' + gender, player_voice=gender)
            required = [source_locale] if source_locale else ['en', 'zh-Hans']
            if any(locale not in texts for locale in required):
                row.update(audio=None, voice_status='unavailable' if record['voice_status'] == 'voiced'
                           else record['voice_status'], text_binding_unresolved=True)
                # Retain the unsupported source as diagnostic text, without
                # manufacturing a spoken variant or dropping the inventory row.
                for locale in required:
                    if locale not in texts:
                        texts[locale] = display_text(raw.get(locale, ''))
            row.update(english=texts.get('en', ''), chinese=texts.get('zh-Hans', ''))
            if source_locale:
                row.update(source_text=texts[source_locale], source_locale=source_locale, texts=texts)
            result.append(row)
    return result
