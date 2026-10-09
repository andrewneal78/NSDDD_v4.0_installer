"""
File verification utilities for NSDDD v3 installation.

Provides checksum calculation and verification functionality.
"""

import hashlib
from pathlib import Path
from typing import Tuple, Dict


def calculate_sha256(filepath: Path, chunk_size: int = 8192) -> str:
    """
    Calculate SHA-256 hash of a file.

    Args:
        filepath: Path to file
        chunk_size: Bytes per chunk (default 8KB)

    Returns:
        SHA-256 hash as hexadecimal string

    Raises:
        FileNotFoundError: If file does not exist
        IOError: If file cannot be read
    """
    filepath = Path(filepath)

    if not filepath.exists():
        raise FileNotFoundError(f'File not found: {filepath}')

    sha256_hash = hashlib.sha256()

    try:
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(chunk_size), b''):
                sha256_hash.update(chunk)
    except IOError as e:
        raise IOError(f'Cannot read file {filepath}: {e}')

    return sha256_hash.hexdigest()


def verify_file(
    filepath: Path,
    expected_hash: str,
    chunk_size: int = 8192
) -> Tuple[bool, str, str]:
    """
    Verify file against expected SHA-256 hash.

    Args:
        filepath: Path to file
        expected_hash: Expected SHA-256 hash (hexadecimal string)
        chunk_size: Bytes per chunk (default 8KB)

    Returns:
        Tuple of (is_valid: bool, actual_hash: str, expected_hash: str)

    Raises:
        FileNotFoundError: If file does not exist
    """
    actual_hash = calculate_sha256(filepath, chunk_size)
    is_valid = actual_hash.lower() == expected_hash.lower()
    return is_valid, actual_hash, expected_hash


def load_checksums_file(filepath: Path) -> Dict[str, str]:
    """
    Load checksums from a checksums file.

    Expected format: one checksum per line, hash followed by filename
    Example:
        a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6  file1.txt
        x9y8z7w6v5u4t3s2r1q0p9o8n7m6l5k4  file2.txt

    Args:
        filepath: Path to checksums file

    Returns:
        Dictionary mapping filename to checksum

    Raises:
        FileNotFoundError: If file does not exist
        ValueError: If file format is invalid
    """
    filepath = Path(filepath)

    if not filepath.exists():
        raise FileNotFoundError(f'Checksums file not found: {filepath}')

    checksums = {}

    try:
        with open(filepath, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()

                if not line or line.startswith('#'):
                    continue

                parts = line.split()
                if len(parts) < 2:
                    raise ValueError(
                        f'Invalid format at line {line_num}: "{line}"\n'
                        'Expected: hash filename'
                    )

                hash_value = parts[0]
                filename = parts[1]

                if len(hash_value) != 64:
                    raise ValueError(
                        f'Invalid hash length at line {line_num}: {hash_value}\n'
                        'SHA-256 hashes must be 64 hexadecimal characters'
                    )

                checksums[filename] = hash_value

    except ValueError as e:
        raise ValueError(f'Error reading checksums file {filepath}: {e}')

    return checksums


def verify_directory(
    directory: Path,
    checksums: Dict[str, str],
    verbose: bool = True
) -> Tuple[bool, Dict]:
    """
    Verify all files in a directory against checksums.

    Args:
        directory: Directory to verify
        checksums: Dictionary mapping filenames to expected hashes
        verbose: If True, print verification results

    Returns:
        Tuple of (all_valid: bool, results: dict)
        results contains:
        - verified: List of valid files
        - mismatches: List of (filename, expected, actual) tuples
        - missing: List of missing filenames
    """
    directory = Path(directory)
    results = {
        'verified': [],
        'mismatches': [],
        'missing': []
    }

    for filename, expected_hash in checksums.items():
        filepath = directory / filename

        if not filepath.exists():
            results['missing'].append(filename)
            if verbose:
                print(f'✗ {filename}: NOT FOUND')
            continue

        try:
            is_valid, actual_hash, _ = verify_file(filepath, expected_hash)

            if is_valid:
                results['verified'].append(filename)
                if verbose:
                    print(f'✓ {filename}: OK')
            else:
                results['mismatches'].append((filename, expected_hash, actual_hash))
                if verbose:
                    print(f'✗ {filename}: MISMATCH')
                    print(f'  Expected: {expected_hash}')
                    print(f'  Actual:   {actual_hash}')

        except IOError as e:
            results['missing'].append(filename)
            if verbose:
                print(f'✗ {filename}: ERROR - {e}')

    all_valid = len(results['mismatches']) == 0 and len(results['missing']) == 0
    return all_valid, results
