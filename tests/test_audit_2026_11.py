"""Regression tests for the defects found in the 2026-11-03 audit."""
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from _library import country_context as C  # noqa: E402


@pytest.fixture(scope='module')
def ns(tmp_path_factory):
    """The notebook's engine namespace over the repository's own document metadata (no model, no index)."""
    base = tmp_path_factory.mktemp('install')
    (base / 'metadata').mkdir()
    (base / 'metadata' / 'document_metadata.csv').write_bytes((ROOT / 'document_metadata_4.0.csv').read_bytes())
    old = {k: os.environ.get(k) for k in ('NSDDD_INSTALL_PATH', 'NSDDD_AUTO_UPDATE')}
    os.environ.update(NSDDD_INSTALL_PATH=str(base), NSDDD_AUTO_UPDATE='0')
    from mcp_server_local import engine
    sys.modules.pop('nsddd_notebook_engine', None)
    engine._ns = None
    try:
        yield engine.load_namespace(), engine
    finally:
        for k, v in old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        engine._ns = None


def test_unusable_document_numbers():
    assert C.unusable_document_numbers('12, 100-110; 7') == []
    assert C.unusable_document_numbers('abc 12 1-5000') == ['abc', '1-5000']


def test_bad_doc_numbers_are_refused_not_ignored(ns):
    n, engine = ns
    with pytest.raises(ValueError, match='abc'):
        engine._make_filters(n, {'doc_numbers': ['abc']})
    assert engine._make_filters(n, {'doc_numbers': ['100-102', 7]}).doc_numbers == ['100', '101', '102', '7']


def test_string_and_year_filters_are_coerced(ns):
    n, engine = ns
    assert engine._make_filters(n, {'countries': 'FRA'}).countries == ['FRA']
    assert engine._make_filters(n, {'year_min': '2000'}).year_min == 2000
    with pytest.raises(ValueError):
        engine._make_filters(n, {'year_min': 'soon'})


def test_most_recent_only_keeps_every_document_of_the_latest_year(ns):
    n, _ = ns
    df = n['METADATA']['documents']
    ids = df['File prefix'].tolist()
    first = None
    for seed in range(5):
        n['METADATA']['documents'] = df.sample(frac=1, random_state=seed).reset_index(drop=True)
        got = sorted(n['apply_metadata_filters'](ids, n['MetadataFilters'](most_recent_only=True)))
        first = first or got
        assert got == first                              # no dependence on row order
    n['METADATA']['documents'] = df
    latest = df.groupby('ISO Alpha-3 Code').Year.transform('max')
    assert sorted(df[df.Year == latest]['File prefix']) == first
    assert {'865', '868', '891'} <= set(first)           # Sweden's three 2026 documents are all kept


class _Hit:
    def __init__(self, doc, country):
        self.country, self.document_id, self.score, self.year = country, str(doc), 0.8, 2020


def test_hits_per_1k_words_uses_all_eligible_words(ns):
    n, _ = ns
    df = n['METADATA']['documents']
    jp = df[df.Country == 'Japan']
    total_k = jp.word_count.astype(int).sum() / 1000
    for doc in (jp.iloc[0], jp.assign(w=jp.word_count.astype(int)).sort_values('w').iloc[-1]):
        row = n['_compute_norm_context_rows']([_Hit(doc['File prefix'], 'Japan')] * 10)[0]
        assert row['hits_per_1k'] == pytest.approx(round(10 / total_k, 4), abs=1e-4)      # same whichever document matched


def test_catalogue_source_link_only_for_web_addresses():
    nb = json.loads((ROOT / 'document_metadata_search_voila.ipynb').read_text(encoding='utf-8'))
    src = '\n'.join(''.join(c['source']) for c in nb['cells'] if c['cell_type'] == 'code')
    assert "if src and src != 'nan':" not in src and "re.match(r'https?://', src)" in src


# --- keyword and Boolean search through the notebook functions, over a small SQLite store -------------------------------

def _model(ns_, tmp_path):
    import sqlite3
    import numpy as np
    from _library.segment_store import SegmentStore, build_fts
    texts = {'2/1': 'Cybersecurity is a priority', '2/2': 'Our cyber security posture', '2/3': 'Our cyber-security posture',
             '2/4': 'Die Führung der Streitkräfte', '2/5': 'Hrung ist kein Wort', '3/1': 'The cyber/security link',
             '3/2': 'Оборона страны', '3/3': 'Counter-terrorism and counterterrorism'}
    import tempfile
    db = Path(tempfile.mkdtemp(dir=tmp_path)) / 'segments.sqlite'      # a fresh store on every call
    con = sqlite3.connect(db)
    con.execute('CREATE TABLE seg(id TEXT PRIMARY KEY, doc TEXT, row INTEGER, text TEXT, lang TEXT)')
    con.executemany('INSERT INTO seg VALUES (?,?,?,?,?)', [(k, k.split('/')[0], i, t, 'en') for i, (k, t) in enumerate(texts.items())])
    con.commit()
    con.close()
    build_fts(db)
    ids = list(texts)
    emb = np.random.default_rng(0).normal(size=(len(ids), 8)).astype('float32')
    emb /= np.linalg.norm(emb, axis=1, keepdims=True)
    return {'segments_dict': SegmentStore(db), 'encoded_segments': ids, 'segment_encodings': emb, 'alignment_dict': {}, 'alignment_anchor': {},
            'documents_dict': {'2': {'iso': 'ALB', 'year': 2004, 'type': 'NSS', 'name': '2 Albania'}, '3': {'iso': 'ALB', 'year': 2005, 'type': 'DD', 'name': '3 Albania'}},
            'countries_dict': {'ALB': {'country': 'Albania'}}}


def _found(ns_, tmp_path, mode, query, **kw):
    md = _model(ns_, tmp_path)
    ns_['MODEL_DICT'] = md
    cfg = ns_['SearchConfig'](topics=[query], keyword_search=(mode == 'keyword'), boolean_mode=(mode == 'boolean'), context_window=0, **kw)
    fn = ns_['run_keyword_search'] if mode == 'keyword' else ns_['run_boolean_search']
    results, _ = fn(query, cfg, md)
    return sorted(r.segment_id for r in results)


@pytest.mark.parametrize('mode', ['keyword', 'boolean'])
def test_both_modes_find_the_same_things(ns, tmp_path, mode):
    n, _ = ns
    f = lambda q, **kw: _found(n, tmp_path, mode, q, **kw)
    assert f('cyber security') == ['2/2', '2/3', '3/1']              # separated forms, not 'Cybersecurity'
    assert f('cybersecurity') == ['2/1']                               # one word is one word
    assert f('cyber*') == ['2/1', '2/2', '2/3', '3/1']                 # a wildcard reaches the compound
    assert f('counter terrorism') == ['3/3']                           # 'counterterrorism' is not two words
    assert f('hrung') == ['2/5']                                       # not inside 'Führung'
    assert f('FÜHRUNG') == ['2/4']
    assert f('оборон') == []              # a stem is not a word; use оборон*
    assert f('оборон*') == ['3/2']


def test_exact_mode_uses_white_space_only(ns, tmp_path):
    n, _ = ns
    assert _found(n, tmp_path, 'keyword', 'cyber security', smart_boundaries=False) == ['2/2']


def test_wildcard_only_term_is_refused(ns, tmp_path):
    n, _ = ns
    with pytest.raises(ValueError):
        _found(n, tmp_path, 'keyword', '*')


@pytest.mark.parametrize('call', [dict(context_window=999999), dict(context_window=-1), dict(result_limit=0), dict(result_limit=-5), dict(max_results=0)])
def test_engine_refuses_out_of_range_limits(call):
    from mcp_server_local import engine
    with pytest.raises(ValueError):
        engine.semantic_search('x', **call)
    with pytest.raises(ValueError):
        engine.keyword_search('x', **{k: v for k, v in call.items() if k != 'max_results'} or {'result_limit': 0})


def test_slovenian_is_one_label():
    import pandas as pd
    df = pd.read_csv(ROOT / 'document_metadata_4.0.csv', dtype=str, keep_default_na=False)
    assert not df.apply(lambda c: c.str.contains('Slovene', regex=False)).any().any()


@pytest.mark.parametrize('mode', ['keyword', 'boolean'])
def test_match_inside_words_option(ns, tmp_path, mode):
    n, _ = ns
    f = lambda q, **kw: _found(n, tmp_path, mode, q, **kw)
    assert f('hrung') == ['2/5']                                       # default: exact word
    assert f('hrung', match_inside_words=True) == ['2/4', '2/5']       # inside 'Führung' too
    assert f('оборон', match_inside_words=True) == ['3/2']
    assert f('cyber security', match_inside_words=True) == ['2/2', '2/3', '3/1']   # still needs a separator
