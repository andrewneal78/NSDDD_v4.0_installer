#!/usr/bin/env python3
"""Verify integrity, viewers, metadata filters and real searches using the app's engine."""
import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-path', help='Data directory to verify without changing saved settings')
    parser.add_argument('--keyword-only', action='store_true', help='Verify without requiring/loading the semantic encoder')
    args = parser.parse_args()
    try:
        from _library.runtime import resolve_path
        cfg = json.loads((ROOT / 'install_config.json').read_text(encoding='utf-8')) if (ROOT / 'install_config.json').exists() else {}
        base = resolve_path(args.install_path or cfg.get('install_path', ROOT), ROOT)
        os.environ.update(NSDDD_INSTALL_PATH=str(base), NSDDD_AUTO_UPDATE='0', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
        from _library.installation import validate_data
        errors = validate_data(base, require_encoder=not args.keyword_only)
        if errors:
            for error in errors:
                print('✗ ' + error)
            return 1
        print('✓ index integrity, dimensions and every SQLite row mapping')
        from _library.viewers import ensure_viewers
        print(f'✓ document viewers ({ensure_viewers(base / "model", ROOT / "XHR")} generated)')
        from _library import cluster_labeller
        ai_ok, ai_msg = cluster_labeller.status(base / 'model')
        print(f"{'✓' if ai_ok else '–'} optional AI headings: {ai_msg}")
        from mcp_server_local import engine
        ns = engine.ensure_loaded(semantic=False)
        assert ns['ENCODER'] is None, 'keyword startup unexpectedly loaded the semantic encoder'
        ids = list(ns['MODEL_DICT']['documents_dict'])
        for kwargs in ({'countries': ['FRA'], 'freedom_house_status': ['Not Free']},
                       {'countries': ['FRA'], 'regions': ['Asia']},
                       {'countries': ['FRA'], 'organizations': ['ASEAN'], 'membership_at_publication': False}):
            if ns['apply_metadata_filters'](ids, ns['MetadataFilters'](**kwargs)):
                raise RuntimeError('contradictory filters returned documents: ' + str(kwargs))
        print('✓ empty filter intersections remain empty')
        t = time.time()
        k = engine.keyword_search('Gesamtverteidigung')
        if k.get('num_results', 0) < 1:
            raise RuntimeError('original-language keyword search returned no results')
        if ns['ENCODER'] is not None:
            raise RuntimeError('keyword search unexpectedly loaded the semantic encoder')
        print(f"✓ keyword search: {k['num_results']} results ({time.time() - t:.1f} s), encoder remains unloaded")
        if not args.keyword_only:
            t = time.time()
            r = engine.semantic_search('climate change is a security threat')
            if r.get('num_results', 0) <= 100:
                raise RuntimeError('semantic smoke search returned too few results')
            print(f"✓ semantic search: {r['num_results']:,} results ({time.time() - t:.1f} s)")
        print('\nAll checks passed.')
        return 0
    except Exception as exc:
        print(f'✗ Verification failed: {exc}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
