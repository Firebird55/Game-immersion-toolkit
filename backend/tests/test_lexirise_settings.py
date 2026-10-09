
import json
from types import SimpleNamespace
import httpx
import pytest
from fastapi import HTTPException
from backend.lexirise import LexiriseService, LexiriseError
from backend.lexirise_settings import account_settings, validate_patch, STUDY_LANGUAGES
from backend.reading import LexiriseReadingService

def test_dictionary_translation_fallback_and_cache_scope_on_settings_reload(tmp_path):
    calls=[]
    def reply(request):
        body=json.loads(request.content) if request.content else {}
        calls.append(request.url.path)
        if request.url.path=="/v1/settings":
            data=settings();data["global"]["translationLanguage"]="fr"
            return httpx.Response(200,json=data)
        if request.url.path=="/v1/analyze/text":
            return httpx.Response(200,json={"occurrences":[{"isWordLike":True,"word":"你好","charStart":0,"charEnd":2,"entryId":1}],"entryMetaById":{"1":{"gloss":"greeting"}}})
        return httpx.Response(200,json={"translations":[{"target_lang":"fr","translation":"bonjour"}],"translation_target":"fr"})
    service=LexiriseService(tmp_path,api_key="fixture",transport=httpx.MockTransport(reply))
    reader=LexiriseReadingService(tmp_path,service)
    try:
        result=reader.lookup("你好",0);assert result["translations"][0]["meaning"]=="bonjour"
        assert result["translationLanguage"]=="fr" and result["sourceLanguage"]=="zh"
        count=calls.count("/v1/analyze/text")
        account_settings(service)
        reader.analyze("你好")
        assert calls.count("/v1/analyze/text")==count+1
    finally:reader.pool.shutdown(wait=True)

def settings():
    return {"languages":["zh"], "native_lang":"en", "global":{"translationLanguage":None}, "languageSettings":{"zh":{"readingAid":"pinyin"},"nl":{"fontSize":"md"}}}

def test_read_and_minimal_patch_with_protected_host_credentials(tmp_path):
    calls=[]
    def reply(request):
        calls.append((request.method,request.url.path,json.loads(request.content) if request.content else None))
        assert request.headers["Authorization"] == "Bearer fixture-key"
        return httpx.Response(200,json=settings())
    service=LexiriseService(tmp_path,api_key="fixture-key",transport=httpx.MockTransport(reply))
    assert account_settings(service)==settings()
    assert calls==[("GET","/v1/settings",None)]
    payload={"languageSettings":{"zh":{"readingAid":"zhuyin"}}}
    assert account_settings(service,payload)["languageSettings"]["nl"]=={"fontSize":"md"}
    assert calls[-1]==("PATCH","/v1/settings",payload)

@pytest.mark.parametrize("payload",[
    {"native_lang":"fr"}, {"global":{"effectiveTranslationLanguage":"fr"}},
    {"languageSettings":{"zh":{"toneColors":{}}}},{"languages":[]},{"languages":["xx"]}
])
def test_derived_fields_and_invalid_study_languages_rejected(payload):
    with pytest.raises(LexiriseError):validate_patch(payload)

def test_all_languages_and_safe_failures(tmp_path):
    assert len(STUDY_LANGUAGES)==31
    for code in STUDY_LANGUAGES:assert validate_patch({"languageSettings":{code:{"fontSize":"lg"}}})
    service=LexiriseService(tmp_path,api_key="fixture-key",transport=httpx.MockTransport(lambda r:httpx.Response(400,json={"secret":"do not expose"})))
    with pytest.raises(LexiriseError,match="HTTP 400"):account_settings(service,{"global":{"translationLanguage":"fr"}})

def test_api_write_requires_explicit_header(tmp_path,monkeypatch):
    from backend import api
    calls=[]
    service=LexiriseService(tmp_path,api_key="fixture-key",transport=httpx.MockTransport(lambda r:(calls.append(r.method) or httpx.Response(200,json=settings()))))
    monkeypatch.setattr(api,"runtime",SimpleNamespace(lexirise=service),raising=False)
    with pytest.raises(HTTPException) as error:api.lexirise_patch_settings({}, "")
    assert error.value.status_code==403 and calls==[]
    assert api.lexirise_get_settings()==settings()
    assert api.lexirise_patch_settings({"global":{"translationLanguage":"fr"}},"lexirise")==settings()
    assert calls==["GET","PATCH"]

def test_reading_language_translation_and_account_cache_isolation(tmp_path):
    calls=[]
    def reply(request):
        body=json.loads(request.content);calls.append(body)
        return httpx.Response(200,json={"occurrences":[{"isWordLike":True,"charStart":2,"charEnd":7,"word":"hello","entryId":1}],"entryMetaById":{"1":{"gloss":"word"}}})
    service=LexiriseService(tmp_path,api_key="fixture-A",transport=httpx.MockTransport(reply))
    readers=[LexiriseReadingService(tmp_path,service,source_language=lang,translation_language=translation) for lang,translation in [("en","fr"),("nl","en"),("en","de")]]
    try:
        for reader in readers:
            assert reader.analyze("😀hello")["tokens"][0]["start"]==2
            reader.analyze("😀hello")
        assert len(calls)==3
        service._api_key="fixture-B";readers[0].analyze("😀hello");assert len(calls)==4
        assert readers[0].analyze("😀hello")["tokens"][0]["zhuyin"]==""
    finally:
        for reader in readers:reader.pool.shutdown(wait=True)
