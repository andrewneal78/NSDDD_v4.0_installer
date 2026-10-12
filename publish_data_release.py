"""Editor's tool: publish a new data version of NSDDD 4.0 so installed copies update themselves.

Put the data zips that changed (any of model_files.zip, encoder_model.zip, metadata.zip, label_model.zip,
viewer_pages.zip) in a folder, then:

    python publish_data_release.py --dir DATA_ZIPS --version 2026.11.02.1 --notes "Added 12 documents from 2026." [--xhr XHR_FOLDER] [--upload]

--xhr builds viewer_pages.zip from the viewer-pages folder. Without --upload it only writes data_version.json
and prints what it would upload. The manifest lists every zip, so zips not in the folder keep the hash of the
current release. Installed copies download only the zips whose hash changed. Version numbers must increase."""
import argparse, hashlib, json, subprocess, sys, zipfile
from pathlib import Path

import data_update as du


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def build_viewer_zip(xhr, out):
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(Path(xhr).glob('*.html')):
            z.write(p, p.name)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--dir', required=True, help='folder holding the changed data zips')
    ap.add_argument('--version', required=True)
    ap.add_argument('--notes', default='')
    ap.add_argument('--xhr', help='viewer-pages folder: builds viewer_pages.zip in --dir')
    ap.add_argument('--upload', action='store_true')
    a = ap.parse_args()
    folder = Path(a.dir)
    folder.mkdir(parents=True, exist_ok=True)
    if a.xhr:
        build_viewer_zip(a.xhr, folder / 'viewer_pages.zip')

    current = du.fetch_manifest() or {'data_version': du.BASELINE_VERSION, 'files': {}}
    if not du.is_newer(a.version, current['data_version']):
        sys.exit(f'Version {a.version} is not newer than the published {current["data_version"]}.')
    files = {n: dict(i) for n, i in current['files'].items()}
    for n, h in du.BASELINE_FILES.items():
        files.setdefault(n, {'sha256': h, 'size': 0})
    changed = []
    for name in du.TARGETS:
        p = folder / name
        if p.is_file():
            files[name] = {'sha256': sha256(p), 'size': p.stat().st_size}
            changed.append(name)
    if not changed:
        sys.exit('No data zips found in ' + str(folder))
    for n, i in files.items():
        if not i.get('size'):
            sys.exit(f'{n} has no recorded size: put it in the folder too, once.')
    manifest = {'data_version': a.version, 'notes': a.notes, 'files': files}
    mpath = folder / du.MANIFEST
    mpath.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Changed:', ', '.join(changed), '\nManifest:', mpath)
    cmd = ['gh', 'release', 'upload', du.TAG, *[str(folder / n) for n in changed], str(mpath), '--clobber', '--repo', f'{du.OWNER}/{du.REPO}']
    if not a.upload:
        print('Not uploaded. To publish, run:\n  ' + ' '.join(cmd))
        return
    subprocess.run(cmd, check=True)
    print('Published data version', a.version)


if __name__ == '__main__':
    main()
