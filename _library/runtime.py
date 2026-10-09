"""Shared path and processor settings, applied before numerical libraries load."""
import os
from pathlib import Path

LOW_POWER = os.environ.get('NSDDD_LOW_POWER', '').lower() in ('1', 'true', 'yes')


def resolve_path(value, root):
    path = Path(value).expanduser()
    return path if path.is_absolute() else Path(root) / path


def configure_runtime():
    threads = int(os.environ.get('NSDDD_THREADS', min(2 if LOW_POWER else 4, os.cpu_count() or 2)))
    if threads < 1:
        raise ValueError('NSDDD_THREADS must be a positive integer')
    os.environ['NSDDD_THREADS'] = str(threads)
    for key in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        os.environ[key] = str(threads)
    os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')
