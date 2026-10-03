from contextlib import closing
from pathlib import Path
import sqlite3

import httpx

from backend.grammar import normalize_grammar
from backend.lexirise import LexiriseService
from backend.reading import LexiriseReadingService


def analysis():
    return {"occurrences": [
        {"charStart": 0, "charEnd": 2, "word": "😀", "isWordLike": False},
        {"charStart": 2, "charEnd": 3, "word": "说", "isWordLike": True},
        {"charStart": 3, "charEnd": 4, "word": "了", "isWordLike": True},
        {"charStart": 4, "charEnd": 5, "word": "了", "isWordLike": True}],
        "grammar": [{"slug": "le-completion", "title": "...了", "subtitle": "Completed action",
                     "level": "HSK 1", "indices": [2], "anchors": [{"token": 2}]},
                    {"slug": "le-completion", "indices": [3]}],
        "grammarStates": {"le-completion": 4}, "morphoPending": False}


def test_raw_token_indices_utf16_duplicates_and_known_states():
    rules = normalize_grammar("😀说了了", analysis(), {})
    assert len(rules) == 1
    assert rules[0]["spans"] == [{"start": 3, "end": 4}, {"start": 4, "end": 5}]
    assert rules[0]["examples"] == ["了"]
    assert rules[0]["proficiency"] == 4
    assert rules[0]["localOverride"] is False
    assert normalize_grammar("😀说了了", analysis(), {"le-completion": 0})[0]["proficiency"] == 0


def test_unknown_and_malformed_matches_are_not_invented():
    result = analysis()
    result["grammarStates"] = {}
    result["grammar"] += [{"slug": "bad/url", "indices": [2]},
                          {"slug": "invalid", "indices": [False, 999, -1]}, None]
    rules = normalize_grammar("😀说了了", result, {})
    assert len(rules) == 1
    assert rules[0]["proficiency"] == 0


def test_local_known_choices_survive_restarting_and_do_not_write_to_lexirise(tmp_path):
    requests = []
    def reply(request):
        requests.append((request.method, request.url.path))
        result = analysis()
        result["grammarStates"] = {}
        return httpx.Response(200, json=result)
    export = LexiriseService(tmp_path, api_key="test", transport=httpx.MockTransport(reply))
    reader = LexiriseReadingService(tmp_path, export)
    reader._schedule_meaning = lambda word: False
    try:
        assert reader.set_grammar_known("😀说了了", "not-in-line", True) is None
        assert reader.set_grammar_known("😀说了了", "le-completion", True)["proficiency"] == 4
    finally:
        reader.pool.shutdown(wait=True)
    reader = LexiriseReadingService(tmp_path, export)
    reader._schedule_meaning = lambda word: False
    try:
        rule = reader.analyze("😀说了了")["grammar"][0]
        assert rule["proficiency"] == 4 and rule["localOverride"] is True
        assert reader.set_grammar_known("😀说了了", "le-completion", False)["proficiency"] == 0
        assert reader.analyze("😀说了了")["grammar"][0]["proficiency"] == 0
        assert requests == [("POST", "/v1/analyze/text")]
    finally:
        reader.pool.shutdown(wait=True)


def test_pending_full_analysis_retries_instead_of_caching_fast_only_for_ten_minutes(tmp_path):
    requests = []
    def reply(request):
        requests.append(request)
        result = analysis()
        result["morphoPending"] = len(requests) == 1
        if result["morphoPending"]:
            result["grammar"] = []
        return httpx.Response(200, json=result)
    reader = LexiriseReadingService(tmp_path,
        LexiriseService(tmp_path, api_key="test", transport=httpx.MockTransport(reply)))
    reader._schedule_meaning = lambda word: False
    try:
        assert reader.analyze("😀说了了")["analysisPending"] is True
        with closing(sqlite3.connect(reader.path)) as db, db:
            db.execute("UPDATE cache SET at=at-2 WHERE kind='analysis-full'")
        result = reader.analyze("😀说了了")
        assert result["analysisPending"] is False and len(result["grammar"]) == 1
        assert len(requests) == 2
    finally:
        reader.pool.shutdown(wait=True)
