"""Data updates: new data versions on the release reach an installed copy (local web server, no internet)."""
import functools, hashlib, http.server, json, sys, threading, zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import data_update as du


def make_zip(path, files):
    with zipfile.ZipFile(path, 'w') as z:
        for name, text in files.items():
            z.writestr(name, text)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture
def world(tmp_path, monkeypatch):
    app = tmp_path / 'app'
    data = tmp_path / 'data'
    (data / 'model' / 'qwen3-embedding-0.6b').mkdir(parents=True)
    (data / 'metadata').mkdir()
    (app / 'XHR').mkdir(parents=True)
    (data / 'model' / 'segments.sqlite').write_text('old index')
    (data / 'model' / 'qwen3-embedding-0.6b' / 'model.safetensors').write_text('encoder')
    (app / 'XHR' / '1.html').write_text('old viewer')
    (app / 'install_config.json').write_text(json.dumps({'install_path': '../data'}))
    web = tmp_path / 'web'
    web.mkdir()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(web))
    handler.log_message = lambda *a, **k: None
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(du, 'BASE_URL', f'http://127.0.0.1:{server.server_port}/')
    yield app, data, web
    server.shutdown()


def publish(web, version, files, notes='new documents'):
    manifest = {'data_version': version, 'notes': notes, 'files': {}}
    for name, content in files.items():
        make_zip(web / name, content)
        manifest['files'][name] = {'sha256': sha(web / name), 'size': (web / name).stat().st_size}
    (web / du.MANIFEST).write_text(json.dumps(manifest))
    return manifest


def test_nothing_to_do_at_the_baseline_version(world):
    app, data, web = world
    publish(web, du.BASELINE_VERSION, {'model_files.zip': {'segments.sqlite': 'x'}})
    manifest = du.fetch_manifest()
    assert du.pending(app, manifest)[0] == []


def test_new_version_updates_only_changed_installed_zips(world):
    app, data, web = world
    manifest = publish(web, '2099.01.01.1', {
        'model_files.zip': {'segments.sqlite': 'new index', 'extra.json': '{}'},
        'viewer_pages.zip': {'1.html': 'new viewer', '2.html': 'second'},
        'label_model.zip': {'q.gguf': 'x'},          # not installed here: must be skipped
    })
    manifest = du.fetch_manifest()
    changed, local = du.pending(app, manifest)
    assert local == du.BASELINE_VERSION
    assert sorted(changed) == ['model_files.zip', 'viewer_pages.zip']
    assert du.apply(app, manifest, changed, log=lambda *_: None)
    assert (data / 'model' / 'segments.sqlite').read_text() == 'new index'
    assert (data / 'model' / 'extra.json').exists()
    assert (data / 'model' / 'qwen3-embedding-0.6b' / 'model.safetensors').read_text() == 'encoder'   # untouched
    assert sorted(p.name for p in (app / 'XHR').iterdir()) == ['1.html', '2.html']
    assert not (data / 'model' / 'label_model').exists()
    version, files = du.read_state(data)
    assert version == '2099.01.01.1' and files['model_files.zip'] == manifest['files']['model_files.zip']['sha256']
    assert du.pending(app, manifest)[0] == []         # now up to date
    assert not (data / '_update').exists()


def test_damaged_download_leaves_installed_data_unchanged(world):
    app, data, web = world
    manifest = publish(web, '2099.01.01.1', {'model_files.zip': {'segments.sqlite': 'new index'}})
    (web / du.MANIFEST).write_text(json.dumps(dict(manifest, files={'model_files.zip': dict(manifest['files']['model_files.zip'], sha256='0' * 64)})))
    m = du.fetch_manifest()
    assert not du.apply(app, m, ['model_files.zip'], log=lambda *_: None)
    assert (data / 'model' / 'segments.sqlite').read_text() == 'old index'
    assert du.read_state(data)[0] == du.BASELINE_VERSION


def test_older_or_equal_version_is_never_installed(world):
    app, data, web = world
    publish(web, '2026.10.01.1', {'model_files.zip': {'segments.sqlite': 'older'}})
    assert du.pending(app, du.fetch_manifest())[0] == []


def test_unreachable_release_gives_none(world, monkeypatch):
    monkeypatch.setattr(du, 'BASE_URL', 'http://127.0.0.1:9/')
    assert du.fetch_manifest(timeout=2) is None


def test_failed_overlay_restores_the_old_program_files(tmp_path, monkeypatch):
    import shutil as sh
    import launch
    src, dst = tmp_path / 'src', tmp_path / 'dst'
    (src / 'sub').mkdir(parents=True)
    dst.mkdir()
    (src / 'a.py').write_text('new a')
    (src / 'sub' / 'b.py').write_text('new b')
    (dst / 'a.py').write_text('old a')
    real = sh.copy2
    def flaky(f, t, *a, **k):
        if Path(f).name == 'b.py' and Path(t).parent.name == 'sub':
            raise OSError('file is in use')
        return real(f, t, *a, **k)
    monkeypatch.setattr(launch.shutil, 'copy2', flaky)
    with pytest.raises(OSError):
        launch.overlay_tree(src, dst)
    assert (dst / 'a.py').read_text() == 'old a' and not (dst / 'sub' / 'b.py').exists()
    monkeypatch.setattr(launch.shutil, 'copy2', real)
    launch.overlay_tree(src, dst)
    assert (dst / 'a.py').read_text() == 'new a' and (dst / 'sub' / 'b.py').read_text() == 'new b'
