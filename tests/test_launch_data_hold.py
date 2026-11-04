"""A locally rebuilt search index must not be replaced by a data update the user did not ask for (2026-11-04: `launch.py
--no-update` still installed the new data release over a rebuilt index)."""
import argparse, sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import launch


def args(**kw):
    base = dict(no_update=False, no_data_update=False, restarted=False)
    base.update(kw)
    return argparse.Namespace(**base)


def test_no_update_skips_the_data_check_too():
    assert launch.data_update_wanted(args()) is True
    assert launch.data_update_wanted(args(no_update=True)) is False
    assert launch.data_update_wanted(args(no_data_update=True)) is False


def test_restart_after_a_code_update_still_checks_data(monkeypatch):
    seen = {}
    monkeypatch.setattr(launch.subprocess, 'call', lambda cmd: seen.setdefault('cmd', cmd) and 0)
    monkeypatch.setattr(launch.sys, 'argv', ['launch.py', '--update', '--low-power'])
    with pytest.raises(SystemExit):
        launch.restart_self()
    assert '--restarted' in seen['cmd'] and '--no-update' not in seen['cmd'] and '--low-power' in seen['cmd']
    assert launch.data_update_wanted(args(restarted=True)) is True      # the restarted launcher still installs new data


def test_hold_file_announces_but_never_installs_data(tmp_path, monkeypatch):
    import data_update
    manifest = {'data_version': '2099.01.01.1', 'notes': 'x', 'files': {'model_files.zip': {'size': 1, 'sha256': 'a'}}}
    monkeypatch.setattr(data_update, 'fetch_manifest', lambda: manifest)
    monkeypatch.setattr(data_update, 'pending', lambda cwd, m: (['model_files.zip'], '2026.11.01.1'))
    calls = []
    monkeypatch.setattr(data_update, 'apply', lambda *a, **k: calls.append(a) or {})
    monkeypatch.setattr(launch, 'AUTO_UPDATE_ENABLED', True)
    monkeypatch.delenv('NSDDD_AUTO_DATA_UPDATE', raising=False)
    (tmp_path / launch.DATA_UPDATE_HOLD).write_text('')
    assert launch.maybe_update_data(tmp_path, apply=True) is False
    assert calls == []                                                   # announced only
    (tmp_path / launch.DATA_UPDATE_HOLD).unlink()
    launch.maybe_update_data(tmp_path, apply=True)
    assert len(calls) == 1                                               # without the file it installs, as before
