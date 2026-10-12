"""
GitHub release data source for the NSDDD 4.0 pre-release.

Until the full 4.0 dataset is deposited on Edinburgh DataShare, the search index, the encoder and the
metadata are published as assets of a GitHub release. This client has the same two methods that
install.py uses on the DataShare client (list_bitstreams, get_file_info), so the installer treats
the two sources alike.
"""

import json
from typing import Dict, List
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ReleaseClient:
    def __init__(self, owner: str, repo: str, tag: str):
        self.owner, self.repo, self.tag = owner, repo, tag
        self.api_url = f'https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}'
        self._assets = None

    def list_bitstreams(self) -> List[Dict]:
        if self._assets is None:
            request = Request(self.api_url, headers={
                'User-Agent': 'NSDDD-4.0-Installer', 'Accept': 'application/vnd.github+json'})
            last = None
            for _ in range(3):
                try:
                    with urlopen(request, timeout=20) as response:
                        self._assets = json.loads(response.read().decode('utf-8')).get('assets', [])
                    break
                except (HTTPError, URLError, TimeoutError) as e:
                    last = e
            if self._assets is None:
                raise ConnectionError(f'could not read the data release ({self.tag}): {last}')
        return self._assets

    def get_file_info(self, filename: str) -> Dict:
        for asset in self.list_bitstreams():
            if asset.get('name') == filename:
                size = int(asset.get('size', 0))
                return {'name': filename, 'size_bytes': size, 'size_mb': round(size / 1024 ** 2, 2),
                        'download_url': asset['browser_download_url']}
        names = ', '.join(a.get('name', '') for a in self.list_bitstreams())
        raise FileNotFoundError(f'"{filename}" is not in the data release {self.tag}. Available: {names}')
