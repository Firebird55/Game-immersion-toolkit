from datetime import datetime, timedelta, timezone

from backend.models import TextMatch
from backend.storage import TranscriptStore


def match(key='receive-money', amount=10):
    return TextMatch(game='hito', text_id=f'hito:{key}', chinese=f'我 收到 {amount}元',
                     english=f'I receive {amount} yuan', source_ocr='ocr', score=100, kind='exact')


def test_hito_repeat_moves_same_row_to_top_and_preserves_favorite(tmp_path):
    store = TranscriptStore(tmp_path / 'db.sqlite')
    now = datetime.now(timezone.utc)
    first = store.add_or_touch_hito(match(), 'old', now)
    store.set_favorite(first.id, True)
    second = store.add_or_touch_hito(match('other'), 'old', now + timedelta(seconds=1))
    repeated = store.add_or_touch_hito(match(amount=30), 'new', now + timedelta(days=1))
    assert repeated.id == first.id
    assert repeated.favorite
    assert repeated.session_id == 'new'
    assert repeated.english == 'I receive 30 yuan'
    assert store.count(game='hito') == 2
    assert [line.id for line in store.list(game='hito')] == [first.id, second.id]
    assert store.list_favorites(game='hito')[0].id == first.id


def test_hito_unvoiced_history_and_identity_survive_restart_cleanup(tmp_path):
    store = TranscriptStore(tmp_path / 'db.sqlite')
    line = store.add_or_touch_hito(match(), 'session')
    store.purge_unvoiced()
    store.prune(keep_nonfavorite=0)
    reopened = TranscriptStore(store.path)
    assert reopened.get(line.id) is not None
    assert reopened.add_or_touch_hito(match(amount=50), 'next').id == line.id
