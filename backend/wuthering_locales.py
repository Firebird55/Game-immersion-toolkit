"""Original Wuthering locale/voice-field identities without reader imports."""

SUPPORTED_LOCALES = ('en', 'zh-Hans', 'zh-Hant', 'ja', 'ko')
VOICE_LOCALES = {'en': ('en', 4), 'zh-Hans': ('zh', 7), 'zh-Hant': ('zh', 7), 'ja': ('ja', 5), 'ko': ('ko', 6)}
TEXT_LOCALES = {locale: locale for locale in ('en', 'zh-Hans', 'zh-Hant', 'ja', 'ko', 'fr', 'de', 'ru', 'th', 'vi', 'id')}
TEXT_LOCALES.update({'es-ES': 'es', 'pt-BR': 'pt'})
