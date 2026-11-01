"""Authored Source caption boundaries, independently of display line wrapping."""
import pytest

from backend.preparation_errors import PreparationFailure
from backend.source_dialogue import caption_pages, localized_caption_pages


def test_identical_delays_align_pages_without_revealing_later_text():
    pages = localized_caption_pages({
        'en': 'First page.<delay:2>Second page.',
        'fr': 'Première page.<delay:2.0>Deuxième page.',
        'de': 'Erste Seite.<delay:3>Zweite Seite.',
        'it': 'One complete differently paged translation.',
    }, 'en')
    assert pages == [(0, {'en': 'First page.', 'fr': 'Première page.'}),
                     (1, {'en': 'Second page.', 'fr': 'Deuxième page.'})]


def test_blank_and_repeated_pages_preserve_authored_ordinals():
    text = '<delay:1>Repeated.<delay:2>Repeated.'
    assert caption_pages(text) == ['Repeated.', 'Repeated.']
    assert localized_caption_pages({'en': text, 'fr': '<delay:1>Répété.<delay:2>Répété.'}, 'en') == [
        (1, {'en': 'Repeated.', 'fr': 'Répété.'}),
        (2, {'en': 'Repeated.', 'fr': 'Répété.'})]


@pytest.mark.parametrize('delay', ['NaN', 'Infinity', '-1', '1801', 'not-a-number'])
def test_invalid_delays_are_not_unverified_translation_boundaries(delay):
    with pytest.raises(PreparationFailure):
        localized_caption_pages({'en': 'First.<delay:' + delay + '>Second.'}, 'en')


def test_visual_newlines_are_not_assumed_to_be_future_pages():
    assert localized_caption_pages({'en': 'Wrapped\\ncaption\ncontinues.'}, 'en') == [
        (0, {'en': 'Wrapped caption continues.'})]
