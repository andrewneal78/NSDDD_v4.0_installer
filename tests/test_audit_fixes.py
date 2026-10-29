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


# --------------------------------------------------------------------------- H1, H3: downloads
import hashlib, http.server, io, json, os, threading, zipfile


class _RangeServer(http.server.ThreadingHTTPServer):
    """Serves one payload; honours byte ranges and answers 416 past the end, like GitHub's storage. Counts requests."""
    def __init__(self, payload, honour_range=True):
        self.payload, self.honour_range, self.requests = payload, honour_range, 0
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                outer.requests += 1
                body, rng = outer.payload, self.headers.get('Range')
                if rng and outer.honour_range:
                    start = int(rng.split('=')[1].split('-')[0])
                    if start >= len(body):
                        self.send_response(416)
                        self.send_header('Content-Range', f'bytes */{len(body)}')
                        self.end_headers()
                        return
                    self.send_response(206)
                    body = body[start:]
                else:
                    self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        super().__init__(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.serve_forever, daemon=True).start()

    @property
    def url(self):
        return f'http://127.0.0.1:{self.server_port}/f.zip'


def test_complete_leftover_file_is_not_requested_again(tmp_path):
    from utils.download import download_file
    payload = os.urandom(50_000)
    server = _RangeServer(payload)
    try:
        dest = tmp_path / 'f.zip'
        download_file(server.url, str(dest), expected_size=len(payload))
        download_file(server.url, str(dest), expected_size=len(payload))       # used to fail with HTTP 416
        assert dest.read_bytes() == payload and server.requests == 1
    finally:
        server.shutdown()


def test_server_ignoring_the_range_restarts_instead_of_appending(tmp_path):
    from utils.download import download_file
    payload = os.urandom(50_000)
    server = _RangeServer(payload, honour_range=False)
    try:
        dest = tmp_path / 'f.zip'
        dest.write_bytes(payload[:20_000])
        download_file(server.url, str(dest), expected_size=len(payload))
        assert dest.read_bytes() == payload
    finally:
        server.shutdown()


def _run_install(tmp_path, monkeypatch, archive, published_sha):
    """install.main for one archive served locally, stopped just before the Python environment is set up."""
    import install
    import data_update
    server = _RangeServer(archive)
    spec = {'filename': 'metadata.zip', 'size_mb': 0.01, 'size_gb': 0.0, 'extract_to': 'metadata/',
            'expected_files': ['document_metadata.csv'], 'required': True, 'description': 'test'}

    class Client:
        def __init__(self, *a):
            pass

        def list_bitstreams(self):
            return []

        def get_file_info(self, name):
            return {'download_url': server.url, 'size_bytes': len(archive), 'sha256': None}

    class Stop(Exception):
        pass

    def stop():
        raise Stop
    data = tmp_path / 'data'
    monkeypatch.setattr(install, 'DOWNLOADS', {'metadata': spec})
    monkeypatch.setattr(install, 'ReleaseClient', Client)
    monkeypatch.setattr(install, '_prompt_install_dir', lambda: data)
    monkeypatch.setattr(install, '_check_disk', lambda path: (True, 100))
    monkeypatch.setattr(install, '_ensure_windows_runtime', stop)
    monkeypatch.setattr(data_update, 'fetch_manifest',
                        lambda *a, **k: {'data_version': '2099.01.01.1', 'files': {'metadata.zip': {'sha256': published_sha}}})
    try:
        install.main()
        return 'finished'
    except Stop:
        return 'reached environment setup'
    except SystemExit as e:
        return f'exit {e.code}'
    finally:
        server.shutdown()


def _zip_bytes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('document_metadata.csv', 'File prefix\n1\n')
    return buf.getvalue()


def test_install_checks_each_archive_against_its_published_sha256(tmp_path, monkeypatch):
    archive = _zip_bytes()
    assert _run_install(tmp_path, monkeypatch, archive, hashlib.sha256(archive).hexdigest()) == 'reached environment setup'
    assert (tmp_path / 'data' / 'metadata' / 'document_metadata.csv').exists()
    assert not (tmp_path / 'data' / 'downloads' / 'metadata.zip').exists()


def test_install_rejects_and_deletes_an_archive_that_does_not_match(tmp_path, monkeypatch):
    archive = _zip_bytes()
    assert _run_install(tmp_path, monkeypatch, archive, '0' * 64) == 'exit 1'
    assert not (tmp_path / 'data' / 'metadata' / 'document_metadata.csv').exists()
    assert not (tmp_path / 'data' / 'downloads' / 'metadata.zip').exists()


def test_data_version_is_recorded_only_from_matching_archives(tmp_path):
    import data_update as du
    manifest = {'data_version': '2099.01.01.1', 'files': {'metadata.zip': {'sha256': 'a' * 64}}}
    assert not du.record_current(tmp_path, verified={'metadata.zip': 'b' * 64}, manifest=manifest)
    assert not (tmp_path / du.STATE).exists()
    assert du.record_current(tmp_path, verified={'metadata.zip': 'a' * 64}, manifest=manifest)
    assert du.read_state(tmp_path) == ('2099.01.01.1', {'metadata.zip': 'a' * 64})


# --------------------------------------------------------------------------- M4, M5, M7: the installer's own choices
import subprocess, types


def test_install_path_expands_home_and_resolves_against_the_installer(monkeypatch):
    import install
    monkeypatch.setattr('builtins.input', lambda prompt='': '~/NSDDD_data')
    assert install._prompt_install_dir() == (Path.home() / 'NSDDD_data').resolve()
    monkeypatch.setattr('builtins.input', lambda prompt='': 'elsewhere')
    assert install._prompt_install_dir() == (install.REPO_ROOT / 'elsewhere').resolve()


def test_failed_pip_install_stops_the_installer(monkeypatch, tmp_path):
    import install
    monkeypatch.setattr(install, '_prompt_venv', lambda: tmp_path / 'python3')
    monkeypatch.setattr(install.platform, 'system', lambda: 'Darwin')
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        return types.SimpleNamespace(returncode=1, stdout='', stderr='ERROR: No matching distribution')
    monkeypatch.setattr(install.subprocess, 'run', run)
    with pytest.raises(SystemExit):
        install._install_dependencies()
    assert len(calls) == 1 and '-r' in calls[0]          # nothing further was attempted


def test_home_folder_environments_are_not_offered(monkeypatch, tmp_path):
    import install
    monkeypatch.delenv('VIRTUAL_ENV', raising=False)
    monkeypatch.setattr(install, 'REPO_ROOT', tmp_path)
    looked_at = []
    monkeypatch.setattr(install, '_python_exe', lambda d: looked_at.append(d) or d / 'missing')
    install._find_existing_venvs()
    assert all(str(d).startswith(str(tmp_path)) for d in looked_at)


OLD_PYTHON = Path('/usr/bin/python3')


@pytest.mark.skipif(not OLD_PYTHON.exists(), reason='no system Python to test with')
def test_old_python_gets_the_friendly_version_message():
    code = ('import sys; sys.path.insert(0, sys.argv[1]); import install, launch; '
            'print("supported" if install._check_python() else "refused")')
    out = subprocess.run([str(OLD_PYTHON), '-I', '-c', code, str(ROOT)], capture_output=True, text=True,
                         env={'PYTHONDONTWRITEBYTECODE': '1'})
    version = subprocess.run([str(OLD_PYTHON), '-c', 'import sys; print(sys.version_info[:2] < (3, 11))'],
                             capture_output=True, text=True).stdout.strip()
    if version != 'True':
        pytest.skip('system Python is new enough')
    assert out.returncode == 0, out.stderr
    assert 'requires Python 3.11 or 3.12' in out.stdout and 'refused' in out.stdout


# --------------------------------------------------------------------------- L1, L3, L9
def test_health_reports_the_model_once_loaded(monkeypatch):
    from mcp_server_local import engine
    monkeypatch.setattr(engine, '_model_ready', False)
    monkeypatch.setattr(engine, 'load_namespace', lambda: {'initialize_model': lambda load_encoder: ({}, object())})
    engine.ensure_loaded()
    assert engine._model_ready is True


def test_widget_comms_check_asks_the_voila_interpreter(monkeypatch, tmp_path):
    import launch
    monkeypatch.setenv('JUPYTER_CONFIG_DIR', str(tmp_path))
    calls = []
    monkeypatch.setattr(launch.subprocess, 'run', lambda cmd, **kw: calls.append(cmd) or types.SimpleNamespace(returncode=1))
    launch.ensure_widget_comms_ok('/path/to/voila/python')
    assert calls and calls[0][0] == '/path/to/voila/python'


def test_csv_export_neutralises_spreadsheet_formulas():
    import ast, json as _json
    nb = _json.loads((ROOT / 'document_metadata_search_voila.ipynb').read_text(encoding='utf-8'))
    src = next(''.join(c['source']) for c in nb['cells'] if 'def _csv_safe' in ''.join(c['source']))
    fn = next(n for n in ast.parse(src.replace('%%capture', '', 1)).body if getattr(n, 'name', '') == '_csv_safe')
    ns = {}
    exec(compile(ast.Module([fn], []), 'csv_safe', 'exec'), ns)
    rows = ns['_csv_safe']([['=HYPERLINK("x")', '-bullet', '@SUM', 'plain', 0.75, None]])
    assert rows == [["'=HYPERLINK(\"x\")", "'-bullet", "'@SUM", 'plain', 0.75, None]]
