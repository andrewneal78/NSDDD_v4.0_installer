"""Anonymous daily start-up count: sent once a day, never from a git checkout, easy to switch off, never raises."""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import usage_ping as up


class Reply:
    def read(self, n=-1): return b''


def make(tmp_path):
    app, data = tmp_path / 'app', tmp_path / 'data'
    app.mkdir(); data.mkdir()
    (app / 'install_config.json').write_text(json.dumps({'install_path': str(data)}))
    return app, data


def recorder(sent):
    def opener(req, timeout):
        sent.append(req); return Reply()
    return opener


def test_sends_once_a_day_with_versions_only(tmp_path, monkeypatch):
    monkeypatch.delenv('NSDDD_NO_PING', raising=False)
    app, data = make(tmp_path); sent = []
    assert up.ping_once_a_day(app, '2026.10.16.3', today='2026-10-20', opener=recorder(sent))
    assert not up.ping_once_a_day(app, '2026.10.16.3', today='2026-10-20', opener=recorder(sent))
    assert up.ping_once_a_day(app, '2026.10.16.3', today='2026-10-21', opener=recorder(sent))
    assert len(sent) == 2
    url = sent[0].full_url
    assert url.startswith('https://nsddd.goatcounter.com/count?') and '2026.10.16.3' in url and str(tmp_path) not in url


def test_switches_and_git_checkout_stop_it(tmp_path, monkeypatch):
    monkeypatch.delenv('NSDDD_NO_PING', raising=False)
    app, data = make(tmp_path); sent = []
    (app / 'no_ping').touch()
    assert not up.ping_once_a_day(app, 'v', today='d', opener=recorder(sent))
    (app / 'no_ping').unlink(); (app / '.git').mkdir()
    assert not up.ping_once_a_day(app, 'v', today='d', opener=recorder(sent))
    (app / '.git').rmdir(); monkeypatch.setenv('NSDDD_NO_PING', '1')
    assert not up.ping_once_a_day(app, 'v', today='d', opener=recorder(sent))
    assert sent == []


def test_offline_never_raises_and_does_not_mark_the_day(tmp_path, monkeypatch):
    monkeypatch.delenv('NSDDD_NO_PING', raising=False)
    app, data = make(tmp_path)
    def boom(req, timeout): raise OSError('offline')
    assert not up.ping_once_a_day(app, 'v', today='d', opener=boom)
    assert not (data / up.STAMP).exists()
    assert not up.ping_once_a_day(tmp_path / 'nowhere', 'v')
