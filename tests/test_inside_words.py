"""'Match inside words': an option that restores substring matching inside longer words, off by default."""
import sqlite3, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _library.keyword_matching import compile_term, fts_query


def hit(term, text, **kw):
    return bool(compile_term(term, **kw).search(text))


def test_default_is_exact_word():
    assert not hit('Sicherheit', 'Die Sicherheitspolitik ist wichtig')
    assert not hit('security', 'cybersecurity')


def test_inside_finds_compounds_and_infixes():
    assert hit('Sicherheit', 'Die Sicherheitspolitik ist wichtig', inside=True)
    assert hit('Verteidigung', 'Gesamtverteidigung und Verteidigungspolitik', inside=True)
    assert hit('hrung', 'Innere Führung', inside=True)
    assert hit('security', 'cybersecurity', inside=True)


def test_inside_keeps_phrase_separator_rule_and_wildcards_in_word():
    assert not hit('cyber security', 'cybersecurity', inside=True)
    assert hit('cyber security', 'cyber-security', inside=True)
    assert not hit('cyber*policy', 'cyber and policy', inside=True)


def test_inside_cannot_use_the_full_text_index():
    assert fts_query('Sicherheit') is not None
    assert fts_query('Sicherheit', inside=True) is None


def test_store_scans_everything_when_inside(tmp_path):
    from _library.segment_store import SegmentStore, build_fts
    db = tmp_path / 'segments.sqlite'
    c = sqlite3.connect(db)
    c.execute('CREATE TABLE seg (id TEXT PRIMARY KEY, text TEXT, lang TEXT, doc TEXT, row INTEGER)')
    c.executemany('INSERT INTO seg VALUES (?,?,?,?,?)', [('1/1', 'Die Sicherheitspolitik', 'de', '1', 1), ('1/2', 'Sicherheit zuerst', 'de', '1', 2),
                                                          ('1/3', 'Nichts davon', 'de', '1', 3)])
    c.commit(); c.close()
    build_fts(str(db))
    st = SegmentStore(str(db))
    exact = {sid for sid, v in st.candidates('Sicherheit') if compile_term('Sicherheit').search(v['text'])}
    inside = {sid for sid, v in st.candidates('Sicherheit', inside=True) if compile_term('Sicherheit', inside=True).search(v['text'])}
    assert exact == {'1/2'} and inside == {'1/1', '1/2'}
