
"""Account settings transport; explicit writes only, using the host's protected key."""
import httpx
from .lexirise import API_BASE, LexiriseService, LexiriseError

STUDY_LANGUAGES = frozenset("zh yue nan ja ko en es fr de it pt ru id ar hi ta th vi tr nl pl cs ro hu sv no da fi la grc lzh".split())
GLOBAL_FIELDS = frozenset("translationLanguage interfaceLanguage disableWordPopups wordPopupOpenMode useCustomProficiencyColors customProficiencyColors".split())
LANGUAGE_FIELDS = frozenset("readingAid readingAboveWords script inlineGlossMode coloringMode toneColorPreset customToneColors colorKnownWordsToo emphasizeFrequencyLevel wordSpacing ttsOnWordClick automaticGrammarHighlighting highlightProperNouns customFont fontSize segmentByCharacter dictionariesEnabled dictionaries wordPopup".split())

def validate_patch(payload: dict) -> dict:
    if not isinstance(payload, dict) or set(payload) - {"languages", "global", "languageSettings"}:
        raise LexiriseError("Only writable Lexirise settings can be changed.")
    if "languages" in payload:
        languages = payload["languages"]
        if not isinstance(languages, list) or not languages or any(not isinstance(code, str) or code not in STUDY_LANGUAGES for code in languages):
            raise LexiriseError("Select at least one supported study language.")
    if "global" in payload:
        if not isinstance(payload["global"], dict) or set(payload["global"]) - GLOBAL_FIELDS:
            raise LexiriseError("Read-only or unknown global setting.")
    if "languageSettings" in payload:
        if not isinstance(payload["languageSettings"], dict):
            raise LexiriseError("Invalid per-language settings.")
        for code, settings in payload["languageSettings"].items():
            if code not in STUDY_LANGUAGES or not isinstance(settings, dict) or set(settings) - LANGUAGE_FIELDS:
                raise LexiriseError("Read-only or unknown per-language setting.")
    return payload

def account_settings(service: LexiriseService, payload: dict | None = None) -> dict:
    if payload is not None:
        validate_patch(payload)
    with httpx.Client(base_url=API_BASE, headers={"Authorization": f"Bearer {service._key()}"},
                      timeout=25, follow_redirects=False, transport=service.transport) as client:
        kwargs = {} if payload is None else {"json": payload}
        result = service._request(client, "GET" if payload is None else "PATCH", "/v1/settings", **kwargs)
    if not isinstance(result.get("languages"), list) or not isinstance(result.get("global"), dict) or not isinstance(result.get("languageSettings"), dict):
        raise LexiriseError("Lexirise returned invalid account settings.")
    return result
