"""Validate the on-disk search index before announcing installation success."""
import csv
import json
import sqlite3
from pathlib import Path


def validate_data(base, require_encoder=True):
    base = Path(base)
    model = base / 'model'
    errors = []
    required = ['segment_encodings_metadata.json', 'encoded_segments.json', 'documents_dict.json',
                'countries_dict.json', 'segments.sqlite', 'short_mask.npy', 'alignment_dict.json']
    required += ['qwen3-embedding-0.6b/config.json', 'qwen3-embedding-0.6b/modules.json',
                 'qwen3-embedding-0.6b/tokenizer.json', 'qwen3-embedding-0.6b/model.safetensors'] if require_encoder else []
    for name in required:
        if not (model / name).is_file() or (model / name).stat().st_size == 0:
            errors.append('missing or empty model/' + name)
    for name in ('document_metadata.csv', 'Country_metadata.csv'):
        if not (base / 'metadata' / name).is_file():
            errors.append('missing metadata/' + name)
    if errors:
        return errors
    try:
        import numpy as np
        meta = json.loads((model / 'segment_encodings_metadata.json').read_text(encoding='utf-8'))
        ids = json.loads((model / 'encoded_segments.json').read_text(encoding='utf-8'))
        docs = json.loads((model / 'documents_dict.json').read_text(encoding='utf-8'))
        shape = tuple(meta['memmap_shape'])
        if len(shape) != 2 or shape[0] != len(ids) or shape[1] != meta['dim']:
            errors.append('embedding dimensions/rows do not match metadata and encoded IDs')
        index = model / meta['memmap_file']
        if not index.is_file() or index.stat().st_size != int(np.prod(shape)) * np.dtype(meta['memmap_dtype']).itemsize:
            errors.append('embedding index has the wrong byte length')
        if len(set(ids)) != len(ids):
            errors.append('duplicate encoded segment IDs')
        short = np.load(model / 'short_mask.npy', mmap_mode='r')
        if short.shape != (len(ids),):
            errors.append('short-segment mask row count is incorrect')
        topics = model / 'topic_of_row.npy'
        if topics.exists() and np.load(topics, mmap_mode='r').shape != (len(ids),):
            errors.append('topic index row count is incorrect')
        with sqlite3.connect((model / 'segments.sqlite').resolve().as_uri() + '?mode=ro', uri=True) as con:
            if con.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                errors.append('SQLite integrity check failed')
            if con.execute('SELECT COUNT(*) FROM seg').fetchone()[0] != len(ids):
                errors.append('SQLite and embedding row counts differ')
            if {r[0] for r in con.execute('SELECT DISTINCT doc FROM seg')} != set(docs):
                errors.append('SQLite document IDs differ from document metadata')
            # All IDs are verified in bounded batches; no second full text/index copy.
            for start in range(0, len(ids), 10000):
                rows = con.execute('SELECT id, row FROM seg WHERE row >= ? AND row < ? ORDER BY row',
                                   (start, min(start + 10000, len(ids)))).fetchall()
                if [r[0] for r in rows] != ids[start:start + 10000] or any(r[1] != start + i for i, r in enumerate(rows)):
                    errors.append('SQLite row ordering differs from encoded segment IDs')
                    break
        with (base / 'metadata' / 'document_metadata.csv').open(encoding='utf-8-sig', newline='') as f:
            metadata_ids = {r['File prefix'] for r in csv.DictReader(f)}
        if metadata_ids != set(docs):
            errors.append('CSV document IDs differ from the model documents')
    except Exception as exc:
        errors.append(f'invalid search data: {exc}')
    return errors
