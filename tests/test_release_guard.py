"""publish_data_release refuses zips that carry the private paragraph layer."""
import sqlite3, sys, zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import publish_data_release as P


def _zip(tmp_path, schema, extra=None):
    db = tmp_path / 'segments.sqlite'
    c = sqlite3.connect(db)
    for q in schema:
        c.execute(q)
    c.commit(); c.close()
    z = tmp_path / 'model_files.zip'
    with zipfile.ZipFile(z, 'w') as zf:
        zf.write(db, 'segments.sqlite')
        for n in extra or []:
            zf.writestr(n, b'x')
    return z


CLEAN = ['CREATE TABLE seg (id TEXT PRIMARY KEY, text TEXT, lang TEXT, doc TEXT, row INTEGER)',
         'CREATE INDEX seg_doc ON seg(doc)']


def test_clean_zip_passes(tmp_path):
    assert P.forbidden_in_zip(_zip(tmp_path, CLEAN)) == []


def test_para_table_and_indexes_refused(tmp_path):
    z = _zip(tmp_path, CLEAN + ['CREATE TABLE para (row INTEGER PRIMARY KEY, pid TEXT, text TEXT)',
                                'CREATE INDEX para_pid ON para(pid)'])
    out = ' '.join(P.forbidden_in_zip(z))
    assert 'para table' in out and 'paragraph index' in out


def test_seg_para_column_refused(tmp_path):
    z = _zip(tmp_path, ['CREATE TABLE seg (id TEXT PRIMARY KEY, text TEXT, lang TEXT, doc TEXT, row INTEGER, para INTEGER)',
                        'CREATE INDEX seg_para ON seg(para)'])
    out = ' '.join(P.forbidden_in_zip(z))
    assert 'seg.para column' in out and 'paragraph index' in out


def test_para_encodings_file_refused(tmp_path):
    assert P.forbidden_in_zip(_zip(tmp_path, CLEAN, ['para_encodings.f16.memmap']))
