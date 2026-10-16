"""Data updates for the NSDDD 4.0 pre-release.

New documents and corrections reach an installed copy as a new *data version* on the project's GitHub data release
(tag data-4.0-pre). The release carries a small file, data_version.json, listing each data zip with its SHA-256.
Each start compares it with the data on this computer and downloads only the zips that changed. Everything is
downloaded, checked and unpacked into a temporary folder before any installed file is touched.

Standard library only. Programs: launch.py (checks at start-up), fetch_data.py / install.py (record the version
after a fresh install), publish_data_release.py (the editor's tool that builds data_version.json)."""
import hashlib, http.client, json, os, shutil, ssl, time, zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen as _urlopen

OWNER, REPO, TAG = 'andrewneal78', 'NSDDD_v4.0_installer', 'data-4.0-pre'
BASE_URL = os.environ.get('NSDDD_DATA_BASE_URL') or f'https://github.com/{OWNER}/{REPO}/releases/download/{TAG}/'
MANIFEST, STATE = 'data_version.json', 'DATA_STATE.json'
HEADERS = {'User-Agent': 'NSDDD-4.0-DataUpdate'}
NETWORK_ERRORS = (HTTPError, URLError, TimeoutError, ConnectionError, http.client.HTTPException, ssl.SSLError, OSError)

# Every copy installed before data versions existed holds exactly this data.
BASELINE_VERSION = '2026.10.12.1'
BASELINE_FILES = {
    'model_files.zip': '874f82f4085b57a4ba06de891eb08ec1a2e782e00f541ab9a53cfee6693c568e',
    'encoder_model.zip': '10d4c31e29eb8c0248dd2806087075afb4c828c2c810c5e0fe070c92165dd147',
    'metadata.zip': 'c0394d9990395e4ec526f253e226f6533452fa1fca9f574b540ebe88f87963a1',
    'label_model.zip': '77bc65a477274c1df43ca382365c3de13a9435f795a191070105ff9aeacb4797',
    'viewer_pages.zip': '6c33594e4d9feb16637e5f3379609b85f3874eeab7fa463567580f0fa45356a7',
}
# zip name -> (where it unpacks, how). 'merge' replaces the files it contains; 'replace' swaps the whole folder.
# '@XHR' is the viewer-pages folder next to the app; everything else is under the data folder.
TARGETS = {
    'model_files.zip': ('model', 'merge'),
    'encoder_model.zip': ('model/qwen3-embedding-0.6b', 'replace'),
    'metadata.zip': ('metadata', 'merge'),
    'label_model.zip': ('model/label_model', 'replace'),
    'viewer_pages.zip': ('@XHR', 'replace'),
}


def urlopen(request, timeout):
    """urlopen that falls back to the certifi bundle when the system store lacks GitHub's root certificate."""
    try:
        return _urlopen(request, timeout=timeout)
    except URLError as e:
        if not isinstance(getattr(e, 'reason', None), ssl.SSLError):
            raise
        try:
            import certifi
        except ImportError:
            raise e
        return _urlopen(request, timeout=timeout, context=ssl.create_default_context(cafile=certifi.where()))


def is_newer(remote, local):
    def key(v):
        return [int(p) if p.isdigit() else 0 for p in str(v).strip().split('.')]
    return bool(remote) and key(remote) > key(local)


def locate(app_dir):
    """(data folder, viewer-pages folder) for this install, or (None, None) when it is not set up."""
    app_dir = Path(app_dir)
    try:
        cfg = json.loads((app_dir / 'install_config.json').read_text(encoding='utf-8'))
        raw = cfg.get('install_path')
        if not raw:
            return None, None
        p = Path(raw)
        data = (p if p.is_absolute() else (app_dir / p)).resolve()
    except Exception:
        return None, None
    return (data, app_dir / 'XHR') if data.is_dir() else (None, None)


def read_state(data_dir):
    try:
        s = json.loads((Path(data_dir) / STATE).read_text(encoding='utf-8'))
        return s.get('version', BASELINE_VERSION), dict(s.get('files', {}))
    except Exception:
        return BASELINE_VERSION, {}


def write_state(data_dir, version, files, notes=''):
    tmp = Path(data_dir) / (STATE + '.tmp')
    tmp.write_text(json.dumps({'version': version, 'files': files, 'notes': notes}, indent=2), encoding='utf-8')
    tmp.replace(Path(data_dir) / STATE)


def fetch_manifest(timeout=15):
    """The data release's current data_version.json, or None when it cannot be read."""
    try:
        with urlopen(Request(BASE_URL + MANIFEST, headers=HEADERS), timeout) as r:
            m = json.loads(r.read().decode('utf-8'))
        return m if m.get('data_version') and isinstance(m.get('files'), dict) else None
    except Exception:
        return None


def pending(app_dir, manifest):
    """(changed zips, local version) for an installed copy. Zips that are not installed here (such as the optional
    heading model) are left alone."""
    data_dir, xhr_dir = locate(app_dir)
    if data_dir is None:
        return [], ''
    version, have = read_state(data_dir)
    if not is_newer(manifest['data_version'], version):
        return [], version
    changed = []
    for name, info in manifest['files'].items():
        if name not in TARGETS:
            continue
        sub, _ = TARGETS[name]
        target = xhr_dir if sub == '@XHR' else data_dir / sub
        if not target.is_dir():
            continue
        if info.get('sha256') != have.get(name, BASELINE_FILES.get(name)):
            changed.append(name)
    return changed, version


def _download(name, size, sha, dest, log):
    for attempt in range(1, 8):
        have = dest.stat().st_size if dest.exists() else 0
        if have > size:
            dest.unlink()
            have = 0
        if have < size:
            headers = dict(HEADERS)
            if have:
                headers['Range'] = f'bytes={have}-'
            try:
                with urlopen(Request(BASE_URL + name, headers=headers), 60) as r:
                    if have and getattr(r, 'status', 206) == 200:
                        have = 0
                    with open(dest, 'ab' if have else 'wb') as f:
                        last = time.time()
                        while True:
                            block = r.read(1 << 20)
                            if not block:
                                break
                            f.write(block)
                            if time.time() - last > 5:
                                log(f'      {dest.stat().st_size / size:.0%} of {size / 1e6:,.0f} MB')
                                last = time.time()
            except NETWORK_ERRORS as e:
                log(f'      interrupted ({e}); retrying ({attempt} of 7)...')
                time.sleep(3)
                continue
        if dest.exists() and dest.stat().st_size == size:
            h = hashlib.sha256()
            with open(dest, 'rb') as f:
                for block in iter(lambda: f.read(1 << 20), b''):
                    h.update(block)
            if h.hexdigest() == sha:
                return True
            log(f'      {name} arrived damaged; downloading it again...')
            dest.unlink()
    return False


def _swap_in(stage, target, mode):
    target = Path(target)
    if mode == 'merge':
        # All or nothing: first move every file being replaced aside (this fails at once on a file another program holds
        # open, such as the index of a copy of NSDDD that is still running, before anything has changed), then move the new
        # files in; on any failure put the old files back. Only then delete the old ones.
        target.mkdir(parents=True, exist_ok=True)
        aside, moved = [], []
        try:
            for item in stage.iterdir():
                dest = target / item.name
                if dest.exists() or dest.is_symlink():
                    keep = dest.with_name(dest.name + '.upd_old')
                    if keep.is_dir():
                        shutil.rmtree(keep, ignore_errors=True)
                    elif keep.exists():
                        keep.unlink()
                    os.replace(dest, keep)
                    aside.append((dest, keep))
            for item in stage.iterdir():
                dest = target / item.name
                shutil.move(str(item), str(dest))
                moved.append(dest)
        except Exception:
            for dest in moved:
                if dest.is_dir():
                    shutil.rmtree(dest, ignore_errors=True)
                else:
                    dest.unlink(missing_ok=True)
            for dest, keep in aside:
                os.replace(keep, dest)
            raise
        for _, keep in aside:
            if keep.is_dir():
                shutil.rmtree(keep, ignore_errors=True)
            else:
                keep.unlink(missing_ok=True)
        return
    old = target.with_name(target.name + '.old')
    shutil.rmtree(old, ignore_errors=True)
    had = target.exists()
    if had:
        os.replace(target, old)
    try:
        shutil.move(str(stage), str(target))
    except Exception:
        if had:
            shutil.rmtree(target, ignore_errors=True)
            os.replace(old, target)
        raise
    shutil.rmtree(old, ignore_errors=True)


def _catalogue(data_dir):
    """(documents, countries) from the installed index, or None when unreadable."""
    try:
        model = Path(data_dir) / 'model'
        return (json.loads((model / 'documents_dict.json').read_text(encoding='utf-8')),
                json.loads((model / 'countries_dict.json').read_text(encoding='utf-8')))
    except Exception:
        return None


def _title(doc_id, info):
    name = str(info.get('name') or doc_id)
    return name[len(doc_id) + 1:] if name.startswith(str(doc_id) + ' ') else name


def describe_changes(before, after):
    """What a data update added or removed, from the catalogues before and after (None when either is unknown)."""
    if not before or not after:
        return {}
    docs0, ctry0 = before
    docs1, ctry1 = after
    def label(i):
        d = docs1[i]
        return {'id': i, 'title': _title(i, d), 'type': d.get('type', ''), 'year': str(d.get('year', ''))}
    added = sorted((i for i in docs1 if i not in docs0), key=lambda i: (len(str(i)), str(i)))
    removed = sorted((i for i in docs0 if i not in docs1), key=lambda i: (len(str(i)), str(i)))
    def cname(c, k):
        v = c.get(k)
        return (v.get('country') or v.get('short_name') or k) if isinstance(v, dict) else (v or k)
    return {'documents_added': [label(i) for i in added],
            'documents_removed': [{'id': i, 'title': _title(i, docs0[i])} for i in removed],
            'countries_added': sorted(cname(ctry1, k) for k in ctry1 if k not in ctry0)}


def apply(app_dir, manifest, changed, log=print):
    """Download, check, unpack, then swap in the changed zips. Returns a dict (version, plus the documents and
    countries added or removed) on success, or False. Installed files are untouched when anything fails before the
    final swap."""
    data_dir, xhr_dir = locate(app_dir)
    if data_dir is None or not changed:
        return False
    need = sum(int(manifest['files'][n].get('size', 0)) for n in changed)
    free = shutil.disk_usage(data_dir).free
    if free < need * 2.2:
        log(f'  Not enough free disk space for the data update (needs about {need * 2.2 / 1e9:.1f} GB, {free / 1e9:.1f} GB free).')
        return False
    tmp = data_dir / '_update'
    shutil.rmtree(tmp / 'stage', ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    stages = []
    before = _catalogue(data_dir)
    try:
        for i, name in enumerate(changed, 1):
            info = manifest['files'][name]
            log(f'  [{i} of {len(changed)}] {name} ({int(info["size"]) / 1e6:,.0f} MB)')
            zpath = tmp / name
            if not _download(name, int(info['size']), info['sha256'], zpath, log):
                log(f'  Could not download {name}; the data is unchanged.')
                return False
            stage = tmp / 'stage' / name
            with zipfile.ZipFile(zpath) as z:
                z.extractall(stage)
            stages.append((name, stage))
        done = {}
        for name, stage in stages:
            sub, mode = TARGETS[name]
            _swap_in(stage, xhr_dir if sub == '@XHR' else data_dir / sub, mode)
            done[name] = manifest['files'][name]['sha256']
        version, have = read_state(data_dir)
        have.update(done)
        write_state(data_dir, manifest['data_version'], have, manifest.get('notes', ''))
        return dict(describe_changes(before, _catalogue(data_dir)), version=manifest['data_version'])
    except Exception as e:
        log(f'  The data update did not finish ({e}); the data is unchanged or was restored.')
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def record_current(data_dir):
    """After a fresh install: note which data version was just downloaded (best effort; never replaces a record)."""
    data_dir = Path(data_dir)
    if (data_dir / STATE).exists():
        return
    m = fetch_manifest()
    if m:
        files = {n: i.get('sha256') for n, i in m['files'].items() if n in TARGETS and n != 'viewer_pages.zip'}
        write_state(data_dir, m['data_version'], files, m.get('notes', ''))
