"""Game locales and Lexirise language contexts; never infer a different target."""
from __future__ import annotations

import unicodedata

from .lexirise_settings import STUDY_LANGUAGES

ASIAN = ('en', 'zh-Hans', 'zh-Hant', 'ja', 'ko')
GAME_LOCALES = {
    'portal': ('en', 'fr', 'de', 'ru', 'es-ES', 'zh-Hant'),
    'portal2': ('en', 'fr', 'de', 'es-ES', 'ru'),
    'halflife': ('en', 'fr', 'de', 'it', 'es-ES', 'zh-Hans', 'zh-Hant', 'ko'),
    'plaguetaleinnocence': ('en', 'fr', 'de'),
    'deathstranding': ('en', 'fr', 'es-ES', 'de', 'it', 'pt-PT', 'ru', 'pl', 'ja', 'es-419', 'pt-BR', 'el'),
    'mgsvtpp': ('en', 'ja'),
    'mgsvgz': ('en', 'ja'),
    'persona5royal': ('en', 'ja'),
    'spyro': ('en', 'fr', 'it', 'de', 'es-ES', 'ar', 'da', 'nl', 'fi', 'no', 'pl', 'pt-BR', 'es-419', 'sv'),
    'detroit': ('en', 'fr', 'it', 'de', 'es-ES', 'ar', 'ja', 'pl', 'pt-PT', 'pt-BR', 'es-419', 'ru'),
    'starrail': ASIAN, 'genshin': ASIAN, 'endfield': ASIAN, 'zzz': ASIAN, 'wuwa': ASIAN, 'nte': ASIAN,
    'pragmata': ('en', 'fr', 'it', 'de', 'es-ES', 'es-419', 'pt-BR', 'ru', 'zh-Hans', 'ja', 'ko'),
    'cyberpunk': ('en', 'fr', 'it', 'de', 'es-ES', 'ja', 'ko', 'pl', 'pt-BR', 'ru', 'zh-Hans'),
    'witcher3': ('en', 'fr', 'de', 'ja', 'ko', 'pl', 'pt-BR', 'ru', 'zh-Hans'),
    'beyond': ('en', 'fr', 'it', 'de', 'es-ES', 'nl', 'ja', 'pl', 'pt-PT', 'pt-BR', 'ru', 'es-419'),
    'heavyrain': ('en', 'fr', 'it', 'de', 'es-ES', 'nl', 'ja', 'pl', 'pt-PT', 'ru'),
    'riseofthetombraider': ('en', 'fr', 'de', 'it', 'es-419', 'es-ES', 'ja', 'pt-BR', 'pl', 'ru', 'ko', 'zh-Hant', 'zh-Hans', 'ar'),
    'shadowofthetombraider': ('en', 'fr', 'de', 'it', 'es-419', 'es-ES', 'ja', 'pt-BR', 'pl', 'ru', 'zh-Hant', 'zh-Hans', 'ar'),
}
LOCALE_NAMES = {'en': 'English', 'zh-Hans': 'Simplified Chinese', 'zh-Hant': 'Traditional Chinese',
    'ja': 'Japanese', 'ko': 'Korean', 'fr': 'French', 'it': 'Italian', 'de': 'German',
    'es-ES': 'Spanish — Spain', 'es-419': 'Spanish — Latin America', 'pt-BR': 'Portuguese — Brazil',
    'pt-PT': 'Portuguese — Portugal', 'ru': 'Russian', 'pl': 'Polish', 'nl': 'Dutch',
    'ar': 'Arabic', 'cs': 'Czech', 'hu': 'Hungarian', 'th': 'Thai', 'tr': 'Turkish', 'uk': 'Ukrainian',
    'da': 'Danish', 'fi': 'Finnish', 'el': 'Greek', 'no': 'Norwegian', 'sv': 'Swedish', 'id': 'Indonesian', 'vi': 'Vietnamese',
    'bg': 'Bulgarian', 'ro': 'Romanian'}


def study_language(locale: str) -> str:
    code = locale.split('-')[0].lower()
    # Original game languages do not depend on an optional account provider's
    # learning-language list (for example DEATH STRANDING's Greek dub).
    game_codes = {value.split('-')[0].lower() for locales in GAME_LOCALES.values() for value in locales}
    if code not in STUDY_LANGUAGES and code not in game_codes:
        raise ValueError('Unsupported game study language')
    return code


def audio_locale(locale: str, game: str | None = None) -> str:
    # Distinct official voice packs must retain their selected identity even
    # when both use Mandarin. Other readers explicitly share one Chinese pack.
    from .steam_games import STEAM_GAMES
    if game in {'riseofthetombraider', 'shadowofthetombraider'} or game in STEAM_GAMES:
        return locale
    return 'zh-Hans' if locale == 'zh-Hant' else locale


def translation_language(settings: dict, source: str) -> str:
    language = settings.get('languageSettings', {}).get(source, {})
    value = language.get('effectiveTranslationLanguage')
    if not isinstance(value, str) or not value:
        value = settings.get('global', {}).get('effectiveTranslationLanguage')
    if not isinstance(value, str) or not value:
        raise ValueError('Reload Lexirise settings to determine this learning language’s translation language.')
    return value


def resolve_locale(language: str, available) -> str | None:
    choices = tuple(available)
    exact = next((code for code in choices if code.casefold() == language.casefold()), None)
    if exact:
        return exact
    canonical = {'zh-hans': 'zh-Hans', 'zh-hant': 'zh-Hant', 'zh': 'zh-Hans', 'es': 'es-ES', 'pt': 'pt-BR'}.get(language.casefold())
    if canonical in choices:
        return canonical
    if language in {'es', 'pt'}:
        return next((code for code in choices if code.startswith(language + '-')), None)
    return None


def normalize_text(text: str, locale: str = '') -> str:
    value = unicodedata.normalize('NFKC', text).casefold()
    if locale.startswith('zh'):
        from .bilingual import simplify_chinese
        value = simplify_chinese(value)
    return ''.join(char for char in value if char.isalnum())
