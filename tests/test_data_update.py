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


def _notice_function(monkeypatch, cwd):
    """The notebook's own _updated_notice_html, run against a folder."""
    import ast
    from html import escape
    nb = json.loads((Path(__file__).resolve().parents[1] / 'document_metadata_search_voila.ipynb').read_text(encoding='utf-8'))
    src = ''.join(nb['cells'][1]['source']).replace('%%capture', '', 1)
    wanted = {'_version_key', '_changes_between', '_updated_notice_html'}
    fns = [n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    ns = {'json': json, 'Path': Path, 'escape': escape}
    exec(compile(ast.Module(fns, []), 'notice', 'exec'), ns)
    monkeypatch.chdir(cwd)
    return ns['_updated_notice_html']


def test_changelog_is_current_and_valid():
    root = Path(__file__).resolve().parents[1]
    entries = json.loads((root / 'CHANGELOG.json').read_text(encoding='utf-8'))
    assert entries[0]['version'] == (root / 'VERSION').read_text().strip(), 'add a CHANGELOG.json entry for every VERSION bump'
    assert all(e['changes'] for e in entries)


def test_update_box_lists_code_changes_and_new_documents(tmp_path, monkeypatch):
    (tmp_path / 'CHANGELOG.json').write_text(json.dumps([
        {'version': '2026.11.01.1', 'date': '2026-11-01', 'changes': ['Newest fix']},
        {'version': '2026.10.20.1', 'date': '2026-10-20', 'changes': ['Middle fix <b>']},
        {'version': '2026.10.01.1', 'date': '2026-10-01', 'changes': ['Old fix already installed']}]))
    (tmp_path / 'update_notice.json').write_text(json.dumps({
        'from': '2026.10.01.1', 'to': '2026.11.01.1',
        'data': {'version': '2026.11.01.2', 'notes': 'Added 2026 documents.',
                 'documents_added': [{'id': '700', 'title': 'Cabo Verde National Defence Strategy 2026', 'type': 'NSS', 'year': '2026'}],
                 'documents_removed': [], 'countries_added': ['Cabo Verde']}}))
    html = _notice_function(monkeypatch, tmp_path)()
    assert 'Newest fix' in html and 'Middle fix &lt;b&gt;' in html and 'Old fix already installed' not in html
    assert '1 new document' in html and 'Cabo Verde National Defence Strategy 2026' in html and 'New countries:</strong> Cabo Verde' in html
    assert not (tmp_path / 'update_notice.json').exists()          # shown once
    assert _notice_function(monkeypatch, tmp_path)() == ''


def test_data_only_correction_is_described(tmp_path, monkeypatch):
    # old and new document lists were compared and are identical: say so, in words that match the release notes
    (tmp_path / 'update_notice.json').write_text(json.dumps({'data': {
        'version': '2026.11.01.2', 'notes': 'Fixed years.', 'documents_added': [], 'documents_removed': [], 'countries_added': []}}))
    html = _notice_function(monkeypatch, tmp_path)()
    assert 'Compared with the data already on this computer, no documents or countries were added or removed' in html
    assert 'Program' not in html and 'Corrections to existing data' not in html


def test_notice_makes_no_claim_when_the_old_data_could_not_be_compared(tmp_path, monkeypatch):
    (tmp_path / 'update_notice.json').write_text(json.dumps({'data': {'version': '2026.11.01.2', 'notes': 'Added 155 documents.'}}))
    html = _notice_function(monkeypatch, tmp_path)()
    assert 'Added 155 documents.' in html and 'no documents' not in html


def test_apply_reports_added_documents(world):
    app, data, web = world
    (data / 'model' / 'documents_dict.json').write_text(json.dumps({'1': {'name': '1 Albania Strategy 2004', 'type': 'NSS', 'year': '2004'}}))
    (data / 'model' / 'countries_dict.json').write_text(json.dumps({'ALB': {'country': 'Albania'}}))
    publish(web, '2099.01.01.1', {'model_files.zip': {
        'segments.sqlite': 'x',
        'documents_dict.json': json.dumps({'1': {'name': '1 Albania Strategy 2004', 'type': 'NSS', 'year': '2004'},
                                           '2': {'name': '2 Niue Defence Policy 2026', 'type': 'DD', 'year': '2026'}}),
        'countries_dict.json': json.dumps({'ALB': {'country': 'Albania'}, 'NIU': {'country': 'Niue'}})}})
    manifest = du.fetch_manifest()
    result = du.apply(app, manifest, ['model_files.zip'], log=lambda *_: None)
    assert result['documents_added'] == [{'id': '2', 'title': 'Niue Defence Policy 2026', 'type': 'DD', 'year': '2026'}]
    assert result['countries_added'] == ['Niue'] and result['version'] == '2099.01.01.1'


def test_file_in_use_leaves_every_installed_file_as_it_was(world, monkeypatch):
    """Windows cannot replace a file another program holds open (a copy of NSDDD still running). The update must then
    leave ALL installed files as they were, not a mix of new and old (seen on the Windows test machine, 2026-10-16)."""
    app, data, web = world
    (data / 'model' / 'documents_dict.json').write_text('old docs')
    manifest = publish(web, '2099.01.01.1', {'model_files.zip': {'documents_dict.json': 'new docs', 'segments.sqlite': 'new index'}})
    real = du.os.replace

    def locked(src, dst, *a, **k):
        if Path(src).name == 'segments.sqlite':
            raise PermissionError(32, 'The process cannot access the file because it is being used by another process')
        return real(src, dst, *a, **k)
    monkeypatch.setattr(du.os, 'replace', locked)
    m = du.fetch_manifest()
    assert not du.apply(app, m, ['model_files.zip'], log=lambda *_: None)
    assert (data / 'model' / 'documents_dict.json').read_text() == 'old docs'
    assert (data / 'model' / 'segments.sqlite').read_text() == 'old index'
    assert not list((data / 'model').glob('*.upd_old'))
    assert du.read_state(data)[0] == du.BASELINE_VERSION
