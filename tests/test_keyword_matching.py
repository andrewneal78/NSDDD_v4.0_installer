"""Keyword and Boolean terms mean the same thing everywhere, and the SQLite prefilter loses nothing."""
import itertools
import random
import re
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _library.keyword_matching import compile_term, fts_query, split_words  # noqa: E402
from _library.segment_store import SegmentStore, build_fts  # noqa: E402


def hit(term, text, smart=True):
    return bool(compile_term(term, smart).search(text))


@pytest.mark.parametrize('term,text,smart,expected', [
    # an exact word is an exact word
    ('security', 'national security policy', True, True),
    ('security', 'cybersecurity', True, False),
    ('security', 'securities', True, False),
    ('cybersecurity', 'cyber security', True, False),
    ('cybersecurity', 'Cybersecurity strategy', True, True),
    # a phrase needs at least one separator, never none
    ('cyber security', 'cyber security', True, True),
    ('cyber security', 'cyber-security', True, True),
    ('cyber security', 'cyber/security', True, True),
    ('cyber security', 'cyber – security', True, True),
    ('cyber security', 'Cybersecurity', True, False),
    ('cyber security', 'cyber-security', False, False),       # exact mode: white space only
    ('cyber  security', 'cyber\nsecurity', False, True),
    ('counter-terrorism', 'counter terrorism', True, True),
    ('counter-terrorism', 'counter terrorism', False, False),
    ('counter-terrorism', 'counter-terrorism', False, True),
    ('counter-terrorism', 'counterterrorism', True, False),
    # boundaries hold in every script
    ('hrung', 'Die Führung', True, False),
    ('ber', 'Über alles', True, False),
    ('оборон', 'необоронный', True, False),
    ('оборон', 'оборона', True, False),
    ('Führung', 'die fÜHRUNG', True, True),
    ('U.S.', 'the U.S. army', True, True),
    # wildcards stay inside a word
    ('cyber*', 'cybersecurity', True, True),
    ('cyber*', 'cyber', True, True),
    ('cyber*', 'cyber security', True, True),
    ('*security', 'cybersecurity', True, True),
    ('nuclear*weapon', 'nuclear weapon', True, False),
    ('nuclear*weapon', 'nuclearweapon', True, True),
    ('defen?e', 'defence', True, True),
    ('defen?e', 'defense', True, True),
    ('defen?e', 'defe', True, False),
    # unspaced scripts have no word boundaries
    ('防衛', '国防衛生白書', True, True),
])
def test_what_a_term_matches(term, text, smart, expected):
    assert hit(term, text, smart) is expected


def test_empty_and_wildcard_only_terms():
    assert not compile_term('').search('anything') and not compile_term(None).search('anything')
    for bad in ('*', '?', 'cyber * ?'):
        with pytest.raises(ValueError):
            compile_term(bad)


def test_split_words():
    assert split_words('counter-terrorism', True) == ['counter', 'terrorism']
    assert split_words('counter-terrorism', False) == ['counter-terrorism']
    assert split_words('  a **b  ') == ['a', '*b']


@pytest.mark.parametrize('term,expected', [
    ('cyber security', '"cyber" AND "security"'),
    ('cyber*', '"cyber"*'),
    ('defen?e', '"defen"*'),
    ('*security', None),                     # a wildcard may extend the front: nothing safe to require
    ('a*b-c', '"a"* AND "c"'),
    ("state's", '"state" AND "s"'),
    ('防衛', None),
])
def test_prefilter_query(term, expected):
    assert fts_query(term, True) == expected


# --- parity: the prefiltered search finds exactly what a full scan finds ---------------------------------------------------

WORDS = ['cyber', 'security', 'cybersecurity', 'counter', 'terrorism', 'counterterrorism', 'defence', 'defense', 'defen', 'state',
         "state's", 'states', 'Führung', 'FÜHRUNG', 'führung', 'hrung', 'Über', 'ber', 'оборона',
         'Оборона', 'оборон', 'необоронный',
         'U.S.', '9/11', 'e-mail', 'a', 'x1', 'x_y', 'nuclear', 'weapon', 'weapons', 'critical', 'infrastructure', 'école',
         'Ecole', 'naïve', 'co-operation', 'cooperation', 'co operation']
GLUE = [' ', ' ', ' ', '-', '/', ' – ', '', ', ', '. ', '\n', '­']


def _corpus(n=700, seed=7):
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        k = rng.randint(1, 6)
        out.append(''.join(rng.choice(WORDS) + rng.choice(GLUE) for _ in range(k)).strip())
    out += ['国防衛生白書', 'Cybersecurity is a priority', 'Our cyber security posture', 'cyber-security']
    return out


@pytest.fixture(scope='module')
def store(tmp_path_factory):
    p = tmp_path_factory.mktemp('fts') / 'segments.sqlite'
    con = sqlite3.connect(p)
    con.execute('CREATE TABLE seg(id TEXT PRIMARY KEY, doc TEXT, row INTEGER, text TEXT, lang TEXT)')
    texts = _corpus()
    con.executemany('INSERT INTO seg VALUES (?,?,?,?,?)', [(f'{i % 5 + 1}/{i}', str(i % 5 + 1), i, t, 'en') for i, t in enumerate(texts)])
    con.commit()
    con.close()
    build_fts(p)
    return SegmentStore(p), texts


def _terms(seed=11, n=250):
    rng = random.Random(seed)
    base = ['cyber security', 'cyber*', '*security', 'counter-terrorism', 'counter terrorism', 'counterterrorism', 'defen?e', "state's",
            'Führung', 'fÜHRUNG', 'оборон*', 'оборона', 'U.S.', '9/11', 'e-mail',
            'x_y', 'a', 'nuclear*weapon*', 'critical infrastructure', 'co-operation', 'cooperation', 'école', 'ecole', 'naïve',
            'ber', 'Über', 'weapon?', '?eapon', 'a*', '国防', 'state*', 'st?te*', 'cyber*security']
    gen = []
    for _ in range(n):
        ws = [rng.choice(WORDS) for _ in range(rng.randint(1, 3))]
        t = rng.choice([' ', '-', '/']).join(ws)
        if rng.random() < .35:
            i = rng.randrange(len(t))
            t = t[:i] + rng.choice(['*', '?']) + t[i + 1:]
        if rng.random() < .15:
            t += '*'
        gen.append(t)
    return base + gen


def test_prefilter_equals_full_scan(store):
    st, texts = store
    used = 0
    for term, smart in itertools.product(_terms(), (True, False)):
        try:
            pat = compile_term(term, smart)
        except ValueError:
            continue
        full = sorted(sid for sid, v in st.items() if pat.search(v['text']))
        via = sorted(sid for sid, v in st.candidates(term, smart=smart) if pat.search(v['text']))
        assert via == full, (term, smart, sorted(set(full) - set(via))[:3])
        used += fts_query(term, smart) is not None
    assert used > 200                              # the prefilter, not the fallback scan, was what was tested


def test_candidates_are_a_superset_even_before_confirmation(store):
    st, _ = store
    for term in ('cyber security', 'cyber*', 'counter-terrorism', 'führung'):
        pat = compile_term(term, True)
        cands = {sid for sid, _ in st.candidates(term, smart=True)}
        assert {sid for sid, v in st.items() if pat.search(v['text'])} <= cands
