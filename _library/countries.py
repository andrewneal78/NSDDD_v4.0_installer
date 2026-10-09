"""
Country lookup utilities for NSDDD v3.

Provides access to country data from the installed dataset.
"""

from __future__ import annotations
import json
from pathlib import Path


class CountryLookup:
    """
    Lookup country information from countries_dict.json.

    Resolves the data file from:
    1. Explicit data_path argument
    2. install_config.json -> install_path/model/countries_dict.json
    3. NSDDD_v3.5_workspace/model/countries_dict.json (relative to cwd)
    4. NSDDD_v3_workspace/model/countries_dict.json (legacy fallback)
    5. model/countries_dict.json (repo-local fallback)
    Falls back gracefully with empty data if not found.
    """

    def __init__(self, data_path: str | None = None):
        self._data = {}
        candidates = []

        if data_path is not None:
            candidates.append(Path(data_path))
        else:
            root = Path.cwd()
            config_path = root / 'install_config.json'
            if config_path.exists():
                try:
                    install_path = json.loads(config_path.read_text(encoding='utf-8')).get('install_path')
                    if install_path:
                        from _library.runtime import resolve_path
                        candidates.append(resolve_path(install_path, config_path.parent) / 'model' / 'countries_dict.json')
                except Exception:
                    pass

            candidates.extend([
                root / 'NSDDD_v4.0_workspace' / 'model' / 'countries_dict.json',
                root / 'NSDDD_v3.5_workspace' / 'model' / 'countries_dict.json',
                root / 'NSDDD_v3_workspace' / 'model' / 'countries_dict.json',
                root / 'model' / 'countries_dict.json',
            ])

        for candidate in candidates:
            if not candidate.exists():
                continue
            try:
                with open(candidate, 'r', encoding='utf-8') as f:
                    self._data = json.load(f)
                break
            except Exception:
                self._data = {}

    def list_all_countries(self, show_region: bool = False) -> list[tuple]:
        """
        Return a list of (num, iso_alpha3, country_name, region) tuples,
        sorted alphabetically by country name, numbered from 1.
        The show_region parameter is accepted for compatibility but region
        is always included as the fourth element.
        """
        entries = []
        for iso_alpha3, info in self._data.items():
            country_name = info.get('country', iso_alpha3)
            region = info.get('unsd_region', '')
            entries.append((iso_alpha3, country_name, region))

        entries.sort(key=lambda x: x[1])

        return [(i + 1, iso, name, region) for i, (iso, name, region) in enumerate(entries)]
