"""
Edinburgh DataShare REST API Client

Module for interacting with Edinburgh DataShare API to list and retrieve files.
"""

from typing import List, Dict, Optional
import json
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    import requests
except ImportError:  # pragma: no cover - exercised on clean installer hosts
    requests = None


class DataShareClient:
    """
    Client for Edinburgh DataShare REST API.

    Provides methods to:
    - List files in a dataset
    - Get file metadata (sizes, checksums, etc.)
    - Construct download URLs
    - Query dataset information
    """

    def __init__(self, api_base: str, handle: str):
        """
        Initialise DataShare client.

        Args:
            api_base: Base URL for DataShare API (e.g., https://datashare.ed.ac.uk/rest)
            handle: Dataset handle (e.g., 10283/XXXXX)
        """
        self.api_base = api_base.rstrip('/')
        self.handle = handle
        self.headers = {
            'User-Agent': 'NSDDD-v3-Installer/1.0',
            'Accept': 'application/json'
        }
        self.session = None
        if requests is not None:
            self.session = requests.Session()
            self.session.headers.update(self.headers)
        self._item_id = None
        self._bitstreams = None

    def _get_json_requests(self, url: str, timeout: int):
        if self.session is None:
            raise RuntimeError('requests not available')
        response = self.session.get(url, timeout=timeout)
        response.raise_for_status()
        return response.json()

    def _get_json_stdlib(self, url: str, timeout: int):
        request = Request(url, headers=self.headers)
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode('utf-8'))

    def _get_json_curl(self, url: str, timeout: int):
        result = subprocess.run(
            [
                'curl',
                '-fsSL',
                '--retry', '4',
                '--retry-delay', '2',
                '--retry-all-errors',
                '--connect-timeout', str(timeout),
                '--max-time', str(timeout * 3),
                '-A', self.headers['User-Agent'],
                url,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)

    def _get_json(self, url: str, timeout: int = 10, attempts: int = 3) -> Dict | List[Dict]:
        """Fetch JSON with retries across requests, stdlib HTTPS, and curl."""
        last_error = None
        backoffs = [0, 2, 5]

        for attempt in range(attempts):
            if attempt < len(backoffs) and backoffs[attempt] > 0:
                time.sleep(backoffs[attempt])

            methods = []
            if self.session is not None:
                methods.append(('requests', self._get_json_requests))
            methods.extend([
                ('urllib', self._get_json_stdlib),
                ('curl', self._get_json_curl),
            ])

            for _, method in methods:
                try:
                    return method(url, timeout)
                except Exception as e:
                    last_error = e
                    continue

        raise ConnectionError(f'Failed to fetch {url}: {last_error}') from last_error

    def get_item_metadata(self) -> Dict:
        """
        Get item metadata from DataShare using handle lookup.

        Returns:
            Dictionary with item metadata including UUID, title, description

        Raises:
            ConnectionError: If API request fails
            ValueError: If handle not found
        """
        url = f'{self.api_base}/handle/{self.handle}'
        data = self._get_json(url, timeout=10)
        if not data or 'uuid' not in data:
            raise ValueError(f'Handle {self.handle} not found or invalid')

        self._item_id = data['uuid']
        return data

    def _get_item_id(self) -> str:
        """
        Get item UUID from handle (with caching).

        Returns:
            Item UUID as string
        """
        if self._item_id is None:
            metadata = self.get_item_metadata()
            self._item_id = metadata['uuid']
        return self._item_id

    def list_bitstreams(self) -> List[Dict]:
        """
        List all files (bitstreams) in the dataset.

        Returns:
            List of dictionaries with file metadata including:
            - name: Filename
            - size: File size in bytes
            - id: Bitstream ID
            - checksum: SHA-256 checksum (if available)
            - mimeType: File MIME type

        Raises:
            ConnectionError: If API request fails
        """
        if self._bitstreams is not None:
            return self._bitstreams

        item_id = self._get_item_id()
        url = f'{self.api_base}/items/{item_id}/bitstreams'
        data = self._get_json(url, timeout=15, attempts=4)
        self._bitstreams = data if isinstance(data, list) else []
        return self._bitstreams

    def get_download_url(self, bitstream_uuid: str) -> str:
        """
        Construct download URL for a bitstream.

        Args:
            bitstream_uuid: UUID of the bitstream to download

        Returns:
            Full download URL
        """
        return f'{self.api_base}/bitstreams/{bitstream_uuid}/retrieve'

    def find_file_by_name(self, filename: str) -> Dict:
        """
        Find a specific file by name in the dataset.

        Args:
            filename: Name of file to find

        Returns:
            Dictionary with file metadata (name, size, id, checksum, etc.)

        Raises:
            FileNotFoundError: If file not found in dataset
        """
        bitstreams = self.list_bitstreams()
        for bitstream in bitstreams:
            if bitstream.get('name') == filename:
                return bitstream

        available = [b.get('name', 'unknown') for b in bitstreams]
        raise FileNotFoundError(
            f'File "{filename}" not found in dataset.\n'
            f'Available files: {", ".join(available)}'
        )

    def get_file_info(self, filename: str) -> Dict:
        """
        Get detailed information about a file.

        Args:
            filename: Name of file

        Returns:
            Dictionary with:
            - name: Filename
            - size_bytes: Size in bytes
            - size_mb: Size in MB
            - size_gb: Size in GB
            - uuid: Bitstream UUID
            - download_url: Full download URL
            - checksum: MD5 checksum if available
        """
        bitstream = self.find_file_by_name(filename)

        size_bytes = bitstream.get('sizeBytes', 0)
        size_mb = size_bytes / (1024 ** 2)
        size_gb = size_bytes / (1024 ** 3)

        return {
            'name': bitstream.get('name'),
            'size_bytes': size_bytes,
            'size_mb': round(size_mb, 2),
            'size_gb': round(size_gb, 2),
            'uuid': bitstream.get('uuid'),
            'download_url': self.get_download_url(bitstream.get('uuid')),
            'checksum': bitstream.get('checkSum', {}).get('value', 'N/A'),
            'mime_type': bitstream.get('mimeType')
        }

    def list_all_files(self) -> List[str]:
        """
        List all available filenames in the dataset.

        Returns:
            List of filenames
        """
        bitstreams = self.list_bitstreams()
        return [b.get('name', 'unknown') for b in bitstreams]

    def verify_handle(self) -> bool:
        """
        Verify that the handle is accessible.

        Returns:
            True if handle is accessible, False otherwise
        """
        try:
            self.get_item_metadata()
            return True
        except Exception:
            return False

    def get_dataset_summary(self) -> Dict:
        """
        Get summary information about the dataset.

        Returns:
            Dictionary with dataset info (files, total size, etc.)
        """
        bitstreams = self.list_bitstreams()

        total_size_bytes = sum(b.get('sizeBytes', 0) for b in bitstreams)
        total_size_gb = total_size_bytes / (1024 ** 3)

        return {
            'file_count': len(bitstreams),
            'total_size_bytes': total_size_bytes,
            'total_size_gb': round(total_size_gb, 2),
            'files': [b.get('name', 'unknown') for b in bitstreams]
        }
