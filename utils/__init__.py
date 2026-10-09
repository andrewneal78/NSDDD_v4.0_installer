"""
NSDDD v3 Installer utilities.

Keep package imports lightweight so ``python3 install.py`` works on a clean
machine before third-party dependencies have been installed.
"""

__all__ = [
    'datashare',
    'download',
    'verify',
    'setup',
]
