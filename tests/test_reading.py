from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

import httpx

from backend.lexirise import LexiriseService
from backend.reading import LexiriseReadingService, word_zhuyin


class ReadingTests(unittest.TestCase):
    def test_lexirise_gloss_and_tones_cover_known_words_without_dictionary_calls(self):
        calls = []

        def reply(request):
            calls.append(request.url.path)
            self.assertEqual(request.url.path, "/v1/analyze/text")
            return httpx.Response(200, json={
                "occurrences": [
                    {"word": "朋友", "entryId": 7, "isWordLike": True,
                     "charStart": 0, "charEnd": 2, "transliteration": "péngyou", "tones": [2, 5]},
                ],
                "entryMetaById": {"7": {"gloss": "friend; companion", "tones": [2, 5]}},
                "stateByEntryId": {"7": {"proficiency": 4}},
            })

        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            export = LexiriseService(directory, api_key="test", transport=httpx.MockTransport(reply))
            reader = LexiriseReadingService(directory, export)
            token = reader.analyze("朋友")["tokens"][0]
            self.assertEqual(token["pinyin"], "péngyou")
            self.assertEqual(token["tones"], [2, 5])
            self.assertEqual(token["zhuyin"], "ㄆㄥˊ ㄧㄡ˙")
            self.assertEqual(token["meaning"], "friend; companion")
            self.assertEqual(calls, ["/v1/analyze/text"])
            reader.pool.shutdown(wait=True)

    def test_zhuyin_uses_lexirise_tones_for_neutral_syllables(self):
        self.assertEqual(word_zhuyin("朋友", [2, 5]), "ㄆㄥˊ ㄧㄡ˙")

    def test_pressed_word_gets_dictionary_examples_once(self):
        calls = []

        def reply(request):
            calls.append(request.url.path)
            if request.url.path == "/v1/analyze/text":
                return httpx.Response(200, json={
                    "occurrences": [{"word": "朋友", "entryId": 7, "isWordLike": True,
                                     "charStart": 0, "charEnd": 2, "transliteration": "péngyou", "tones": [2, 5]}],
                    "entryMetaById": {"7": {"gloss": "friend"}},
                    "stateByEntryId": {},
                })
            if request.url.path == "/v1/dictionary/lookup":
                return httpx.Response(200, json={"translations": [{
                    "target_lang": "en", "translation": "friend",
                    "examples": [{"text": "我的朋友", "translation": "my friend"}],
                }]})
            raise AssertionError(request.url.path)

        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            export = LexiriseService(directory, api_key="test", transport=httpx.MockTransport(reply))
            reader = LexiriseReadingService(directory, export)
            self.assertIsNone(reader.lookup("朋友", 1))
            first = reader.lookup("朋友", 0)
            second = reader.lookup("朋友", 0)
            self.assertEqual(first, second)
            self.assertEqual(first["translations"][0]["examples"][0]["translation"], "my friend")
            self.assertEqual(calls, ["/v1/analyze/text", "/v1/dictionary/lookup"])
            reader.pool.shutdown(wait=True)

    def test_word_sheet_metadata_context_and_state_updates(self):
        calls = []

        def reply(request):
            calls.append((request.method, request.url.path))
            if request.url.path == "/v1/analyze/text":
                return httpx.Response(200, json={
                    "occurrences": [{"word": "是", "entryId": 7, "isWordLike": True,
                                     "charStart": 0, "charEnd": 1, "transliteration": "shì", "tones": [4]}],
                    "stateByEntryId": {"7": {"proficiency": 2, "saved_expression_id": 90}},
                })
            if request.url.path == "/v1/dictionary/lookup":
                return httpx.Response(200, json={
                    "translations": [{"target_lang": "en", "translation": "be, is, are, am",
                                      "part_of_speech": ["verb"]}],
                    "supplementalEntries": [{"dictionary_name": "CC-CEDICT", "headword": "是",
                                             "reading": "shì", "html": "<ul><li>to be</li><li>correct; right</li></ul>"}],
                    "characterInfo": {"char": "是", "hint": "Sound component",
                                      "statistics": {"hskLevel": 1},
                                      "components": [{"character": "止", "type": ["sound"], "hint": "sound"}]},
                    "multipleReadings": {"alternatives": ["shi"]},
                    "rank": 2, "frequency_score": 0.945,
                })
            if request.url.path == "/v1/analyze/context":
                self.assertEqual(request.read().decode().count('"charStart":0'), 1)
                return httpx.Response(200, json={"meaning": "is in this sentence", "conciseMeaning": "is", "reading": "shì"})
            if request.url.path == "/v1/vocabulary/90":
                self.assertEqual(request.method, "PATCH")
                return httpx.Response(200, json={"id": 90, "proficiency": 4})
            raise AssertionError(request.url.path)

        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            export = LexiriseService(directory, api_key="test", transport=httpx.MockTransport(reply))
            reader = LexiriseReadingService(directory, export)
            try:
                details = reader.lookup("是", 0)
                self.assertEqual(details["hskLevel"], 1)
                self.assertEqual(details["rank"], 2)
                self.assertEqual(details["dictionaries"][0]["definitions"], ["to be", "correct; right"])
                self.assertEqual(details["components"][0]["character"], "止")
                self.assertEqual(details["alternateReadings"], ["shi"])
                self.assertEqual(reader.context("是", 0)["conciseMeaning"], "is")
                self.assertEqual(reader.set_proficiency("是", 0, 4)["proficiency"], 4)
                self.assertEqual(reader.analyze("是")["tokens"][0]["proficiency"], 4)
                self.assertEqual(reader.lookup("是", 0)["proficiency"], 4)
                self.assertEqual(calls.count(("POST", "/v1/analyze/text")), 1)
                self.assertEqual(calls.count(("PATCH", "/v1/vocabulary/90")), 1)
            finally:
                reader.pool.shutdown(wait=True)

    def test_new_vocabulary_state_uses_create_endpoint(self):
        def reply(request):
            if request.url.path == "/v1/analyze/text":
                return httpx.Response(200, json={"occurrences": [{"word": "好", "entryId": 8,
                    "isWordLike": True, "charStart": 0, "charEnd": 1}], "stateByEntryId": {}})
            if request.url.path == "/v1/vocabulary":
                self.assertEqual(request.method, "POST")
                return httpx.Response(200, json={"item": {"id": 91, "proficiency": 1}})
            raise AssertionError(request.url.path)

        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            export = LexiriseService(directory, api_key="test", transport=httpx.MockTransport(reply))
            reader = LexiriseReadingService(directory, export)
            try:
                result = reader.set_proficiency("好", 0, 1)
                self.assertEqual(result["savedExpressionId"], 91)
                self.assertEqual(reader.analyze("好")["tokens"][0]["proficiency"], 1)
            finally:
                reader.pool.shutdown(wait=True)

    def test_utf16_ranges_unknown_meanings_and_cache(self):
        calls = []
        lookup_started = threading.Event()
        allow_lookup = threading.Event()

        def reply(request):
            calls.append(request.url.path)
            if request.url.path == "/v1/analyze/text":
                return httpx.Response(200, json={
                    "occurrences": [
                        {"word": "你", "entryId": 1, "isWordLike": True, "charStart": 0, "charEnd": 1, "transliteration": "nǐ"},
                        {"word": "🙂", "isWordLike": False, "charStart": 1, "charEnd": 3},
                        {"word": "朋友", "entryId": 2, "isWordLike": True, "charStart": 3, "charEnd": 5, "transliteration": "péngyou"},
                        {"word": "朋友", "entryId": 2, "isWordLike": True, "charStart": 5, "charEnd": 7, "transliteration": "péngyou"},
                        {"word": "bad", "entryId": 3, "isWordLike": True, "charStart": 7, "charEnd": 99},
                    ],
                    "stateByEntryId": {"1": {"proficiency": 4}},
                })
            if request.url.path == "/v1/dictionary/lookup":
                lookup_started.set()
                if not allow_lookup.wait(3):
                    raise AssertionError("Dictionary lookup was not released")
                return httpx.Response(200, json={"translations": [{"target_lang": "en", "translation": "friend"}]})
            raise AssertionError(request.url.path)

        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            transport = httpx.MockTransport(reply)
            export = LexiriseService(directory, api_key="test", transport=transport)
            reader = LexiriseReadingService(directory, export)
            try:
                first = reader.analyze("你🙂朋友朋友")
                self.assertTrue(lookup_started.wait(1))
                self.assertTrue(first["pendingMeanings"])
                self.assertEqual([token["meaning"] for token in first["tokens"]], ["", "", ""])
                allow_lookup.set()
                reader.pool.shutdown(wait=True)
                second = reader.analyze("你🙂朋友朋友")
            finally:
                allow_lookup.set()
                reader.pool.shutdown(wait=True)
            self.assertFalse(second["pendingMeanings"])
            self.assertEqual([(token["start"], token["end"]) for token in first["tokens"]], [(0, 1), (3, 5), (5, 7)])
            self.assertEqual([token["meaning"] for token in second["tokens"]], ["", "friend", "friend"])
            self.assertEqual(calls.count("/v1/analyze/text"), 1)
            self.assertEqual(calls.count("/v1/dictionary/lookup"), 1)


if __name__ == "__main__":
    unittest.main()
