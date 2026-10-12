"""Regression tests for the findings of the 8 October 2026 Windows test (no model, no network)."""
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_allowlist_matches_windows_and_posix_paths():
    launch = _load('launch_under_test', 'launch.py')
    patterns = [a.split('=', 1)[1] for a in launch.build_voila_command('python') if a.startswith('--VoilaConfiguration.file_allowlist=')]
    ok = lambda path: any(re.fullmatch(p, path) for p in patterns)
    for good in ('XHR/84.html', 'XHR\\84.html', 'XHR\\704_bilingual.html', 'outputs/a.xlsx', 'outputs\\a_norm_context.csv'):
        assert ok(good), good
    for bad in ('launch.py', 'XHRfoo.html', 'outputs\\a.py', 'config.py', '..\\launch.py'):
        assert not ok(bad), bad


def test_zip_installs_update_automatically_git_checkouts_only_announce(monkeypatch, tmp_path):
    monkeypatch.delenv('NSDDD_AUTO_UPDATE', raising=False)
    launch = _load('launch_update_test', 'launch.py')
    assert launch.AUTO_UPDATE_ENABLED is True
    launch.check_zip_update = lambda cwd: (True, '1', '2')
    launch.local_version = lambda cwd: '1'
    applied = []
    launch.apply_zip_update = lambda cwd, v: applied.append(v) or True
    launch.is_git_install = lambda cwd: False
    assert launch.maybe_update(tmp_path, False) is True and applied == ['2']
    assert (tmp_path / launch.UPDATE_NOTICE).exists()
    assert launch.maybe_update(tmp_path, True) is False and applied == ['2']          # --no-update
    launch.check_zip_update = lambda cwd: (False, '1', '')                          # offline: carry on
    assert launch.maybe_update(tmp_path, False) is False and applied == ['2']
    launch.check_zip_update = lambda cwd: (True, '1', '2')
    launch.is_git_install = lambda cwd: True                                        # developer checkout: announce only
    launch.check_git_update = lambda cwd: (True, 'aaaaaaaa', 'bbbbbbbb')
    git_applied = []
    launch.apply_git_update = lambda cwd: git_applied.append(1) or True
    assert launch.maybe_update(tmp_path, False) is False and not git_applied
    assert launch.maybe_update(tmp_path, False, apply=True) is True and git_applied == [1]


def test_headings_from_the_windows_test_are_rejected_and_good_ones_kept():
    from _library import cluster_labeller as L
    L._country_patterns('model')
    bad = ['Klima- og säkerhet-områdene', 'Klimaendringen har økt betydning for sikkerhets- og forsvarsp',
           'Sikkerhet & klimaendringer', 'Aspect of the topic these sentences cover',
           'Cyberspace, space, technology, WMD, terrorism, climate change', 'Security in the Americas',
           'Climate change exacerbates conflicts']
    good = ['Natural disasters', 'Asymmetric and hybrid threats', 'Climate change as a threat multiplier',
            'Energy security risks, climate change, and infrastructure vulnerabilities', 'Indo-Pacific maritime security']
    assert not [t for t in bad if L._valid(L._clean(t))]
    assert all(L._valid(L._clean(t)) for t in good)


def test_headings_use_sentence_case_and_near_copies_are_detected():
    from _library import cluster_labeller as L
    assert L._clean('Climate Change and Security Risks') == 'Climate change and security risks'
    assert L._clean('Arctic Security Challenges') == 'Arctic security challenges'
    near = lambda a, b: len(L._dtoks(a) & L._dtoks(b)) / len(L._dtoks(a) | L._dtoks(b)) >= L.MAX_OVERLAP
    assert near('Climate change effects', 'Climate change impacts')
    assert near('Cybersecurity challenges', 'Cybersecurity risks and threats to national security')
    assert not near('Climate change and food security', 'Climate change and energy')


def test_intel_mac_uses_its_own_constraints(monkeypatch):
    install = _load('install_under_test', 'install.py')
    monkeypatch.setattr(install.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(install.platform, 'machine', lambda: 'x86_64')
    assert install._constraints_name() == 'constraints-intel-mac.txt'
    monkeypatch.setattr(install.platform, 'machine', lambda: 'arm64')
    assert install._constraints_name() == 'constraints.txt'
    assert 'torch==2.2.2' in (ROOT / 'constraints-intel-mac.txt').read_text()


def _dedupe_namespace():
    import json
    nb = json.loads((ROOT / 'document_metadata_search_voila.ipynb').read_text())
    src = next(''.join(c['source']) for c in nb['cells'] if 'def dedupe_pair_matches' in ''.join(c['source']))
    start, end = src.index('def dedupe_pair_matches'), src.index('def _count_once')
    ns = {'MIN_ALIGN_SIM': 0.70, 'MODEL_DICT': {'alignment_dict': {
        '7': [(['7/o/1'], ['7/1'], 0.9), (['7/o/2'], ['7/2'], 0.5), (['7/o/3', '7/o/4'], ['7/3'], 0.8)]}}}
    exec(src[start:end], ns)
    return ns


def test_a_passage_is_counted_once_when_original_and_english_both_match():
    from types import SimpleNamespace as R
    ns = _dedupe_namespace()
    ids = ['7/1', '7/o/1',        # confident pair: keep English, drop original
           '7/2', '7/o/2',        # weak alignment: both kept
           '7/o/3', '7/o/4', '7/3',   # two originals for one English: both dropped
           '7/o/9', '8/5']        # no counterpart matched: kept
    results = [R(segment_id=i) for i in ids]
    kept, dropped = ns['dedupe_pair_matches'](results, 'en')
    assert [r.segment_id for r in kept] == ['7/1', '7/2', '7/o/2', '7/3', '7/o/9', '8/5'] and dropped == 3
    kept, dropped = ns['dedupe_pair_matches'](results, 'orig')      # the 'Original languages only' view keeps the originals
    assert '7/1' not in [r.segment_id for r in kept] and '7/o/1' in [r.segment_id for r in kept]


def test_boolean_parser_quotes_and_bare_phrases():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from _library.boolean_parser import BooleanQueryParser, TermNode, AndNode
    for q in ["'African Union' AND 'peace'", "African Union AND peace",
              '"African Union" AND peace', '‘African Union’ AND ‘peace’']:
        ast = BooleanQueryParser().parse(q)
        assert ast == AndNode(TermNode('African Union'), TermNode('peace')), q
    assert BooleanQueryParser().parse("state's") == TermNode("state's")


def test_installer_downloads_from_the_github_release_not_datashare():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import config
    from utils.release_source import ReleaseClient
    assert config.DATA_SOURCE == 'github'
    client = ReleaseClient(config.DATA_RELEASE_OWNER, config.DATA_RELEASE_REPO, config.DATA_RELEASE_TAG)
    wanted = [v['filename'] for v in config.DOWNLOADS.values() if v.get('required') or v.get('soft')]
    client._assets = [{'name': n, 'size': 5, 'browser_download_url': 'https://example.invalid/' + n} for n in wanted]
    for name in wanted:
        info = client.get_file_info(name)
        assert info['download_url'].endswith(name) and info['size_bytes'] == 5
    try:
        client.get_file_info('nothing.zip')
        assert False
    except FileNotFoundError:
        pass
    assert set(wanted) == {'model_files.zip', 'encoder_model.zip', 'metadata.zip', 'label_model.zip'}


def test_update_never_downgrades_and_compares_numerically():
    launch = _load('launch_version_test', 'launch.py')
    assert launch._is_newer('2026.10.12.1', '2026.10.09.1')
    assert not launch._is_newer('2026.10.09.1', '2026.10.12.1')
    assert not launch._is_newer('2026.10.12.1', '2026.10.12.1')
    assert launch._is_newer('2026.10.12.10', '2026.10.12.9')
    assert launch._is_newer('2026.10.12.1', '')


def test_engine_still_skips_the_page_only_model_load_cell():
    import json
    from pathlib import Path
    nb = json.loads((ROOT / 'document_metadata_search_voila.ipynb').read_text(encoding='utf-8'))
    markers = ('_loading_widget', 'Initialize model (optional')
    loaders = [c for c in nb['cells'] if c['cell_type'] == 'code' and 'initialize_model(load_encoder=not LOW_POWER)' in ''.join(c['source'])]
    assert loaders and all(any(m in ''.join(c['source']) for m in markers) for c in loaders)
