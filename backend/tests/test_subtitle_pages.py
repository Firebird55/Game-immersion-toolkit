"""Authored page boundaries do not imply translation or recording alignment."""
import re

from backend.subtitle_pages import aligned_texts, anonymous_pages, keyed_pages


def test_unique_cue_ids_align_across_order_and_missing_translation_cues():
    marker = re.compile(r'\{(\d+)\}')
    source = keyed_pages('{1}First.{2}Second.', marker, str.strip)
    target = keyed_pages('{2}Tweede.{1}Eerste.', marker, str.strip)
    assert aligned_texts(source[0], 'en', {'nl': target}) == {'en': 'First.', 'nl': 'Eerste.'}
    assert aligned_texts(source[1], 'en', {'nl': target[1:]}) == {'en': 'Second.'}


def test_repeated_keys_and_unmarked_prefix_preserve_text_but_do_not_align():
    marker = re.compile(r'\{(\d+)\}')
    source = keyed_pages('Intro.{1}First.{1}First.{2}Last.', marker, str.strip)
    assert [p.text for p in source] == ['Intro.', 'First.', 'First.', 'Last.']
    assert len({p.identity for p in source}) == 4
    assert [p.alignment_key for p in source] == [None, None, None, '2']
    assert aligned_texts(source[1], 'en', {'nl': source}) == {'en': 'First.'}
    unique = keyed_pages('{1}Only.', marker, str.strip)[0]
    assert aligned_texts(unique, 'en', {'nl': source}) == {'en': 'Only.'}


def test_anonymous_boundaries_keep_repeats_and_empty_slots_without_guessing():
    pages = anonymous_pages('One.||One.', '|', str.strip)
    assert [p.identity for p in pages] == ['page:1', 'page:3']
    assert [p.text for p in pages] == ['One.', 'One.']
    assert aligned_texts(pages[0], 'en', {'nl': pages}) == {'en': 'One.'}
    whole = anonymous_pages('Single.', '|', str.strip)[0]
    assert aligned_texts(whole, 'en', {'nl': anonymous_pages('Enkel.', '|', str.strip)}) == {'en': 'Single.', 'nl': 'Enkel.'}
    assert aligned_texts(whole, 'en', {'nl': pages}) == {'en': 'Single.'}
