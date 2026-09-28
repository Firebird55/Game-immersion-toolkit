from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import httpx

from backend.lexirise import LexiriseService


class LexiriseVoiceTests(unittest.TestCase):
    def test_saved_sentence_includes_uploaded_game_voice(self):
        calls = []

        def reply(request):
            calls.append((request.method, request.url.path))
            if request.method == "GET" and request.url.path == "/v1/decks/1950":
                if request.url.params.get("limit") == "1":
                    return httpx.Response(200, json={"deck": {"lang": "zh", "unit_type": "sentence",
                                                              "deck_type": "snapshot"}})
                return httpx.Response(200, json={"items": [], "hasMore": False})
            if request.url.path == "/v1/vocabulary/audio":
                self.assertIn(b"sample game voice", request.read())
                return httpx.Response(200, json={"publicUrl": "https://pub.example/voice.mp3"})
            if request.method == "GET" and request.url.path == "/v1/vocabulary":
                return httpx.Response(200, json={"items": [], "hasMore": False})
            if request.method == "POST" and request.url.path == "/v1/vocabulary":
                payload = json.loads(request.read())
                self.assertEqual(payload["mode"], "sentence")
                self.assertEqual(payload["audioUrls"], ["https://pub.example/voice.mp3"])
                self.assertEqual(payload["translation"], "Hello")
                return httpx.Response(200, json={"item": {"id": 42}})
            if request.method == "POST" and request.url.path == "/v1/decks/1950/items":
                return httpx.Response(200, json={"added_count": 1})
            raise AssertionError((request.method, request.url.path))

        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            clip = directory / "voice.wav"
            clip.write_bytes(b"RIFF sample game voice")
            service = LexiriseService(directory, api_key="test", transport=httpx.MockTransport(reply))
            first = service.send(ref="line:1", game="zzz", chinese="你好", english="Hello",
                                 speaker="Anby", audio=clip)
            second = service.send(ref="line:1", game="zzz", chinese="你好", english="Hello",
                                  speaker="Anby", audio=clip)
            self.assertTrue(first["sent"])
            self.assertFalse(first["already_sent"])
            self.assertTrue(second["already_sent"])
            self.assertEqual(calls.count(("POST", "/v1/vocabulary/audio")), 1)


if __name__ == "__main__":
    unittest.main()
