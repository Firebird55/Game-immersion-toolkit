from __future__ import annotations

import tempfile
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

    def test_utf16_ranges_unknown_meanings_and_cache(self):
        calls = []

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
                return httpx.Response(200, json={"translations": [{"target_lang": "en", "translation": "friend"}]})
            raise AssertionError(request.url.path)

        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            transport = httpx.MockTransport(reply)
            export = LexiriseService(directory, api_key="test", transport=transport)
            reader = LexiriseReadingService(directory, export)
            first = reader.analyze("你🙂朋友朋友")
            second = reader.analyze("你🙂朋友朋友")
            self.assertEqual(first, second)
            self.assertEqual([(token["start"], token["end"]) for token in first["tokens"]], [(0, 1), (3, 5), (5, 7)])
            self.assertEqual([token["meaning"] for token in first["tokens"]], ["", "friend", "friend"])
            self.assertEqual(calls.count("/v1/analyze/text"), 1)
            self.assertEqual(calls.count("/v1/dictionary/lookup"), 1)
            reader.pool.shutdown(wait=True)


if __name__ == "__main__":
    unittest.main()
