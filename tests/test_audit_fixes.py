"""Regression tests for the October 2026 installer audit (findings H1, H3, H4, M4, M5, M6, M7, L1, L3, L9)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from _library.boolean_parser import parse_boolean_query
from _library.boolean_executor import execute_boolean_query

CORPUS = {'1/1': 'cyber attack on grid', '1/2': 'cyber policy', '1/3': 'terrorism and cyber'}


def _search(query):
    def kw(term, model_dict):
        return [(sid, 100.0) for sid, text in CORPUS.items() if term.lower() in text]
    return dict(execute_boolean_query(parse_boolean_query(query), {}, kw))


def test_and_not_subtracts_matches():
    assert set(_search('cyber AND NOT terrorism')) == {'1/1', '1/2'}


def test_and_not_with_an_unmatched_term_keeps_everything():
    assert set(_search('cyber AND NOT xyzzy')) == {'1/1', '1/2', '1/3'}
    assert set(_search('NOT xyzzy AND cyber')) == {'1/1', '1/2', '1/3'}


def test_several_exclusions_and_nested_not():
    assert set(_search('cyber AND NOT terrorism AND NOT grid')) == {'1/2'}
    assert set(_search('NOT terrorism AND NOT grid AND cyber')) == {'1/2'}
    assert set(_search('cyber AND NOT (terrorism AND NOT xyzzy)')) == {'1/1', '1/2'}


def test_scores_are_finite():
    assert all(score == 100.0 for score in _search('cyber AND NOT xyzzy').values())


@pytest.mark.parametrize('query', ['NOT terrorism', 'cyber OR NOT terrorism', 'NOT a AND NOT b', 'cyber AND NOT NOT x'])
def test_not_without_something_to_exclude_from_is_rejected(query):
    with pytest.raises(ValueError, match='NOT can only exclude'):
        parse_boolean_query(query)
