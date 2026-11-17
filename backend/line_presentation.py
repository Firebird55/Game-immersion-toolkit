"""Project an official prepared translation without changing source identity."""
from .languages import resolve_locale


def translation_fields(texts, english, chinese, target, *, prepared_targets=None):
    texts = texts or {'en': english, 'zh-Hans': chinese}
    locale = resolve_locale(target, texts)
    if prepared_targets is not None and target not in prepared_targets:
        locale = None
    return {'translation_locale': locale or target,
        'translation_text': texts.get(locale, '') if locale else ''}
