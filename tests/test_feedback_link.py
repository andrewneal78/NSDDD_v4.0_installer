"""The feedback link carries the app version, data version and system, and nothing else."""
import json, sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _library import feedback as fb


def test_versions_are_filled_in_and_placeholders_are_gone():
    url = fb.feedback_url('2026.10.16.9', '2026.10.16.1', 'macOS')
    q = parse_qs(urlparse(url).query)
    assert urlparse(url).netloc == 'forms.cloud.microsoft'
    assert sorted(v[0] for k, v in q.items() if k != 'id') == ['2026.10.16.1', '2026.10.16.9', 'macOS']
    assert not any(w in url for w in ('APPVER', 'DATAVER', 'OSNAME'))


def test_values_are_url_encoded_and_blanks_become_unknown():
    url = fb.feedback_url('a b&c', None, '')
    assert 'a%20b%26c' in url and url.count('unknown') >= 1


def test_data_version_reads_state_or_says_unknown(tmp_path):
    (tmp_path / 'model').mkdir()
    assert fb.data_version(tmp_path / 'model') == 'unknown'
    (tmp_path / 'DATA_STATE.json').write_text(json.dumps({'version': '2026.10.16.1'}))
    assert fb.data_version(tmp_path / 'model') == '2026.10.16.1'
