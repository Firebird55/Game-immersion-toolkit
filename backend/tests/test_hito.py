from backend.hito import HitoTextIndex, sentence_identity


def test_hito_exact_pair_ignores_spacing_and_separate_pinyin(tmp_path):
    index = HitoTextIndex(tmp_path)
    index._records = [dict(chinese='我 收到 10元', english='I receive 10 yuan')]
    match = index.match_lines(['wo shoudao 10yuan', '我收到 10元'])
    assert match.game == 'hito'
    assert match.chinese == '我 收到 10元'
    assert match.english == 'I receive 10 yuan'


def test_hito_rejects_unverified_ocr_and_partial_typewriter(tmp_path):
    index = HitoTextIndex(tmp_path)
    index._records = [dict(chinese='我 收到 10元', english='I receive 10 yuan')]
    assert index.match_lines(['我 收到']) is None
    assert index.match_lines(['我 收列 10元']) is None
    assert index.match_lines(['任意的菜单文本']) is None


def test_hito_keeps_valid_text_but_shows_multiple_game_counterparts():
    match = HitoTextIndex._choose('看到', [
        dict(chinese='看到', english='See'), dict(chinese='看到', english='Look')
    ])
    assert match.ambiguous
    assert match.english == 'Look / See'


def test_hito_generated_pair_uses_grammar_identity(tmp_path):
    index = HitoTextIndex(tmp_path)
    index._generated = lambda text: [dict(chinese=text, english='I receive 30 yuan',
                                         identity='I receive 2 yuan')]
    match = index.match_lines(['我 收到 30元'])
    other = HitoTextIndex._choose('我 收到 10元', [
        dict(chinese='我 收到 10元', english='I receive 10 yuan', identity='I receive 2 yuan')])
    assert match.text_id == other.text_id
    assert sentence_identity('I receive 10 yuan') == sentence_identity('I receive 30 yuan')


def test_hito_long_ocr_error_is_corrected_only_to_unambiguous_game_text():
    row = dict(chinese='也许 我 应该 写 这个', english='Maybe I should write this')
    assert HitoTextIndex._choose('也许 我 应该 写 这个', [row]).english == row['english']


def test_hito_preserves_wrapped_english_narrative_and_removes_game_pinyin(tmp_path):
    index = HitoTextIndex(tmp_path)
    index._records = [dict(chinese='Ok, then 面向 and 转 stand for...',
                           english='Ok, then to face and to turn stand for...')]
    index._load_pinyin({'vocabulary': [{'pinyin': 'mianxiang'}, {'pinyin': 'zhuan'}]})
    match = index.match_lines(['mianxiang', 'zhuan', 'Ok, then 面向 and 转', 'stand for...'])
    assert match.english == index._records[0]['english']
    assert index.match_lines(['mianxiang', 'zhuan', 'Ok, then 面向 and 45', 'stand for...']) is None


def test_hito_pinyin_noise_does_not_hide_complete_hanzi(tmp_path):
    index = HitoTextIndex(tmp_path)
    index._records = [dict(chinese='我 看到 一个 大门', english='I see a gate')]
    index._load_pinyin({'vocabulary': [{'pinyin': 'wo kandao yige damen'}]})
    assert index.match_lines(['wo kandao yige darnen', '我 看到 一个 大门']).english == 'I see a gate'


def test_hito_grammar_generated_line_survives_unknown_article_pinyin(tmp_path):
    index = HitoTextIndex(tmp_path)
    index._load_pinyin({'vocabulary': [{'pinyin': 'wo shoudao riji'}]})
    requests = []

    def generate(text):
        requests.append(text)
        if text != '我 收到 一个 日记':
            return []
        return [dict(chinese=text, english='I receive a diary', identity='I receive quantity diary')]

    index._generated = generate
    match = index.match_lines(['WO shoudao', '我 收到 一个 日记', 'yige riji'])
    assert match.english == 'I receive a diary'
    assert match.chinese == '我 收到 一个 日记'
    assert requests[-1] == match.chinese


def test_hito_does_not_generate_from_fragments_of_mixed_narrative(tmp_path):
    index = HitoTextIndex(tmp_path)
    index._load_pinyin({'vocabulary': [{'pinyin': 'wo'}]})
    requests = []
    index._generated = lambda text: requests.append(text) or []
    assert index.match_lines(['Ok, then', '面向 and 转', 'stand for...']) is None
    assert requests == ['Ok, then 面向 and 转 stand for...']


def test_cached_catalog_stays_ready_when_new_game_grammar_is_unsupported(tmp_path, monkeypatch):
    index = HitoTextIndex(tmp_path)
    index._records = [{'chinese': '你好', 'english': 'Hello'}]
    index.ready = True
    monkeypatch.setattr(
        'backend.hito.subprocess.Popen',
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('new format')),
    )

    index._prepare(tmp_path / 'app.asar')

    assert index.ready
    assert index.status()['entry_count'] == 1
    assert index.message.startswith('Cached Hito text ready')


def test_manual_refresh_reuses_last_detected_game_archive(tmp_path, monkeypatch):
    index = HitoTextIndex(tmp_path)
    archive = tmp_path / 'game' / 'resources' / 'app.asar'
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b'game')
    index._archive = archive
    index._signature = ('old',)
    index._retry_at = 999999
    calls = []

    monkeypatch.setattr(index, '_ensure_archive', lambda path, force=False: calls.append((path, force)) or True)

    assert index.refresh() is True
    assert calls == [(archive, True)]
    assert index._signature is None
    assert index._retry_at == 0
