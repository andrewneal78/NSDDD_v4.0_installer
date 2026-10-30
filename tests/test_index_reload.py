"""The engine must notice a rebuilt search index (changed files on disk) and reload, not serve mismatched data."""
import os
import time
from pathlib import Path

import pytest

from mcp_server_local import engine


@pytest.fixture
def index(tmp_path, monkeypatch):
    for name in ('segments.sqlite', 'alignment_dict.json'):
        (tmp_path / name).write_text('{}')
    old = time.time() - 3600
    for f in tmp_path.iterdir():
        os.utime(f, (old, old))
    ns = {'MODEL_PATH': tmp_path, 'MODEL_DICT': {'loaded': True}}
    monkeypatch.setattr(engine, '_index_sig', engine._index_signature(ns))
    monkeypatch.setattr(engine, '_model_ready', True)
    return tmp_path, ns


def test_unchanged_index_is_kept(index):
    _, ns = index
    engine._reload_if_index_changed(ns)
    assert ns['MODEL_DICT'] == {'loaded': True}


def test_changed_index_triggers_reload(index):
    path, ns = index
    f = path / 'alignment_dict.json'
    f.write_text('{"1": []}')                 # different size
    old = time.time() - 1800
    os.utime(f, (old, old))
    engine._reload_if_index_changed(ns)
    assert ns['MODEL_DICT'] is None
    assert engine._index_sig is None and engine._model_ready is False


def test_rebuild_in_progress_is_not_loaded(index):
    path, ns = index
    (path / 'segments.sqlite').write_text('{"changed": 1}')      # modified just now
    with pytest.raises(RuntimeError, match='being updated'):
        engine._reload_if_index_changed(ns)
    assert ns['MODEL_DICT'] == {'loaded': True}           # still serving the old data until the rebuild settles


def test_nothing_loaded_yet_is_a_no_op(monkeypatch):
    monkeypatch.setattr(engine, '_index_sig', None)
    ns = {'MODEL_PATH': Path('.'), 'MODEL_DICT': None}
    engine._reload_if_index_changed(ns)
