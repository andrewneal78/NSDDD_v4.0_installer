"""Regression coverage for install, viewer, filter and resource-limit failures."""
import __future__
import json
import os
import socket
import sqlite3
import tempfile
import types
import unittest
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def notebook_cell(index, **namespace):
    nb = json.loads((ROOT / 'document_metadata_search_voila.ipynb').read_text())
    src = ''.join(l for l in nb['cells'][index]['source'] if not l.lstrip().startswith('%'))
    exec(compile(src, '<notebook>', 'exec', __future__.annotations.compiler_flag), namespace)
    return namespace


class InstallationTests(unittest.TestCase):
    def test_busy_port_preserves_listener(self):
        import launch
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            used = listener.getsockname()[1]
            self.assertNotEqual(launch.choose_port(used), used)
            self.assertEqual(listener.getsockname()[1], used)

    def test_zip_streams_and_rejects_escape(self):
        from utils.extract import extract_with_progress
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            archive = base / 'good.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('nested/data.bin', b'x' * 2500000)
            result = extract_with_progress(archive, base / 'output', verbose=False)
            self.assertEqual(result['bytes_extracted'], 2500000)
            self.assertEqual((base / 'output/nested/data.bin').stat().st_size, 2500000)
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('../outside', 'bad')
            with self.assertRaises(ValueError):
                extract_with_progress(archive, base / 'output', verbose=False)
            self.assertFalse((base / 'outside').exists())

    def test_skip_uses_selected_destination_and_exact_paths(self):
        import install
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            old_root, old_default = install.REPO_ROOT, install.DEFAULT_INSTALL_DIR
            install.REPO_ROOT, install.DEFAULT_INSTALL_DIR = base, 'default'
            try:
                existing = base / 'default/model'; existing.mkdir(parents=True)
                (existing / 'data.bin').write_bytes(b'x')
                spec = {'filename': 'model.zip', 'extract_to': 'model', 'expected_files': ['data.bin']}
                self.assertFalse(install._is_already_extracted(spec, base / 'selected'))
                selected = base / 'selected/model'; selected.mkdir(parents=True)
                (selected / 'data.bin').write_bytes(b'x')
                self.assertTrue(install._is_already_extracted(spec, base / 'selected'))
                (selected / 'data.bin').write_bytes(b'')
                self.assertFalse(install._is_already_extracted(spec, base / 'selected'))
            finally:
                install.REPO_ROOT, install.DEFAULT_INSTALL_DIR = old_root, old_default

    def test_relocated_relative_configuration(self):
        import launch
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); app = root / 'app'; app.mkdir()
            py = root / 'python/python.exe'; py.parent.mkdir(); py.touch()
            (app / 'install_config.json').write_text(json.dumps({'python': '../python/python.exe'}))
            self.assertEqual(Path(launch.configured_python(app)).resolve(), py.resolve())

    def test_viewer_generation_preserves_supplied_pages_and_deep_links(self):
        from _library.viewers import ensure_viewers
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp) / 'model'; model.mkdir(); dest = Path(tmp) / 'XHR'
            (model / 'documents_dict.json').write_text(json.dumps({'1': {'name': '<Document>'}}))
            (model / 'alignment_dict.json').write_text(json.dumps({'1': [[['1/o/1'], ['1/1'], .9]]}))
            with sqlite3.connect(model / 'segments.sqlite') as con:
                con.execute('CREATE TABLE seg(id TEXT, text TEXT, doc TEXT, row INTEGER)')
                con.executemany('INSERT INTO seg VALUES (?,?,?,?)', [('1/1','English <text>','1',0), ('1/o/1','Original & text','1',1)])
            self.assertEqual(ensure_viewers(model, dest), 3)
            for filename, anchor in [('1.html', '1'), ('1_original.html', '1'), ('1_bilingual.html', 'o1')]:
                text = (dest / filename).read_text()
                self.assertIn(f'id="{anchor}"', text)
                self.assertIn('URLSearchParams', text)
                self.assertNotIn('English <text>', text)
            (dest / '1.html').write_text('supplied viewer')
            self.assertEqual(ensure_viewers(model, dest), 0)
            self.assertEqual((dest / '1.html').read_text(), 'supplied viewer')

    def test_corrupt_index_and_database_mapping_are_rejected(self):
        from _library.installation import validate_data
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);model=base/'model';metadata=base/'metadata'
            model.mkdir();metadata.mkdir()
            files={'segment_encodings_metadata.json':{'memmap_shape':[2,2], 'dim':2, 'memmap_dtype':'float16','memmap_file':'index.bin'},
                   'encoded_segments.json':['1/1','1/2'], 'documents_dict.json':{'1':{}}, 'countries_dict.json':{}, 'alignment_dict.json':{}}
            for name,value in files.items(): (model/name).write_text(json.dumps(value))
            (model/'index.bin').write_bytes(b'0'*8);np.save(model/'short_mask.npy',np.zeros(2,dtype=bool))
            (metadata/'document_metadata.csv').write_text('File prefix\n1\n')
            (metadata/'Country_metadata.csv').write_text('iso\nFRA\n')
            with sqlite3.connect(model/'segments.sqlite') as con:
                con.execute('CREATE TABLE seg(id TEXT, doc TEXT, row INTEGER)')
                con.executemany('INSERT INTO seg VALUES (?,?,?)',[('1/1','1',0),('1/2','1',1)])
            self.assertEqual(validate_data(base, require_encoder=False),[])
            (model/'index.bin').write_bytes(b'0'*7)
            self.assertIn('embedding index has the wrong byte length',validate_data(base,require_encoder=False))
            (model/'index.bin').write_bytes(b'0'*8)
            with sqlite3.connect(model/'segments.sqlite') as con:
                con.execute("UPDATE seg SET id='1/9' WHERE row=1")
            self.assertIn('SQLite row ordering differs from encoded segment IDs',validate_data(base,require_encoder=False))

    def test_filters_never_resurrect_empty_intersection(self):
        metadata = {'documents': pd.DataFrame({'File prefix': ['1','2'], 'ISO Alpha-3 Code': ['FRA','CHN'], 'Year':[2020,2021], 'NSS/WP/DD':['NSS','NSS']}),
                    'regions': {'FRA':'Europe','CHN':'Asia'}, 'freedom_house':{'FRA':'Free','CHN':'Not Free'},
                    'organizations': {'NATO': {'FRA'}, 'ASEAN':set()}, 'income_groups':{'FRA':'High'}}
        ns = notebook_cell(3, METADATA=metadata, pd=pd)
        def filtered(**kwargs):
            f=types.SimpleNamespace(**kwargs); f.to_dict=lambda:kwargs
            return ns['apply_metadata_filters'](['1','2'],f)
        self.assertEqual(filtered(countries=['FRA'], regions=['Asia']), [])
        self.assertEqual(filtered(countries=['FRA'], freedom_house_status=['Not Free'], income_groups=['High']), [])
        self.assertEqual(filtered(countries=['FRA'], organizations=['ASEAN']), [])
        self.assertEqual(filtered(countries=['FRA'], organizations=['NATO']), ['1'])
        self.assertEqual(filtered(regions=['Europe','Asia']), ['1','2'])
        self.assertEqual(filtered(countries=['ZZZ'], year_min=2000), [])

    def test_large_search_preserves_every_result_without_embeddings(self):
        ns = notebook_cell(4, os=os, LOW_POWER=False)
        results = [types.SimpleNamespace(cluster_id=None) for _ in range(6001)]
        ci = ns['cluster_search_results_internal'](results, {})
        self.assertEqual(ci['num_singletons'], len(results))
        self.assertEqual(ci['cluster_dict']['singletons'], list(range(len(results))))
        self.assertIn('all results are retained', ci['clustering_note'])
        self.assertTrue(all(r.cluster_name == 'Unclustered' for r in results))

    def test_offline_version_check_does_not_request_network(self):
        from unittest.mock import patch
        # Execute only version helpers; path loading requires installed CSVs.
        nb=json.loads((ROOT/'document_metadata_search_voila.ipynb').read_text());src=''.join(nb['cells'][1]['source'])
        src=src[src.index('def check_notebook_update'):src.index('def build_update_banner_html')]
        ns={'os':os, '_read_local_version':lambda:'test'}
        exec(compile(src,'<update>','exec',__future__.annotations.compiler_flag),ns)
        with patch.dict(os.environ, {'NSDDD_AUTO_UPDATE':'0'}), patch('urllib.request.urlopen',side_effect=AssertionError('network used')):
            self.assertIsNone(ns['check_notebook_update']()['error'])


if __name__ == '__main__':
    unittest.main()
