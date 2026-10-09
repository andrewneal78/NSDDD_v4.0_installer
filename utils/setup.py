"""
Setup utilities for NSDDD v3 installation.

Provides directory structure creation and management utilities.
"""

from pathlib import Path
from typing import Dict, List
import os


def create_directory_structure(base_path: str) -> Dict[str, Path]:
    """
    Create NSDDD v3 directory structure.

    Creates the following structure:
    ```
    base_path/
    ├── model/                    # Model files and embeddings
    ├── documents/                # Document files
    ├── metadata/                 # Metadata CSVs
    ├── documentation/            # Documentation
    └── downloads/                # Temporary download directory
    ```

    Args:
        base_path: Base installation directory

    Returns:
        Dictionary mapping directory names to Path objects
    """
    base = Path(base_path)

    directories = {
        'base': base,
        'model': base / 'model',
        'documents': base / 'documents',
        'metadata': base / 'metadata',
        'documentation': base / 'documentation',
        'downloads': base / 'downloads'
    }

    # Create all directories
    for name, path in directories.items():
        if name != 'base':
            path.mkdir(parents=True, exist_ok=True)

    return directories


def get_directory_tree(
    base_path: str,
    prefix: str = '',
    max_depth: int = 3,
    current_depth: int = 0
) -> str:
    """
    Generate a text tree representation of directory structure.

    Args:
        base_path: Root directory to display
        prefix: Prefix for tree formatting (used recursively)
        max_depth: Maximum directory depth to display
        current_depth: Current recursion depth (internal use)

    Returns:
        String containing tree representation
    """
    base = Path(base_path)

    if current_depth >= max_depth:
        return ''

    lines = []
    items = []

    try:
        items = sorted(base.iterdir(), key=lambda x: (not x.is_dir(), x.name))
    except PermissionError:
        return ''

    for i, item in enumerate(items):
        is_last = i == len(items) - 1
        current_prefix = '└── ' if is_last else '├── '
        next_prefix = '    ' if is_last else '│   '

        if item.is_dir():
            lines.append(f'{prefix}{current_prefix}{item.name}/')

            # Recursively show subdirectories
            if current_depth < max_depth - 1:
                subtree = get_directory_tree(
                    str(item),
                    prefix + next_prefix,
                    max_depth,
                    current_depth + 1
                )
                if subtree:
                    lines.append(subtree.rstrip('\n'))
        else:
            # Show file with size
            size = item.stat().st_size
            if size < 1024:
                size_str = f'{size}B'
            elif size < 1024 ** 2:
                size_str = f'{size / 1024:.1f}KB'
            elif size < 1024 ** 3:
                size_str = f'{size / (1024 ** 2):.1f}MB'
            else:
                size_str = f'{size / (1024 ** 3):.1f}GB'

            lines.append(f'{prefix}{current_prefix}{item.name} ({size_str})')

    return '\n'.join(lines)


def display_directory_structure(base_path: str, title: str = 'Directory Structure'):
    """
    Display directory tree in formatted output.

    Args:
        base_path: Root directory to display
        title: Title to display above tree
    """
    base = Path(base_path)

    print(f'\n{title}')
    print('=' * 60)
    print(f'{base.name}/')
    print(get_directory_tree(str(base)))
    print()


def get_directory_size(path: str) -> dict:
    """
    Calculate total size of directory and contents.

    Args:
        path: Directory path

    Returns:
        Dictionary with:
        - size_bytes: Total size in bytes
        - size_mb: Total size in MB
        - size_gb: Total size in GB
        - file_count: Total number of files
        - dir_count: Total number of directories
    """
    path = Path(path)

    total_bytes = 0
    file_count = 0
    dir_count = 0

    try:
        for item in path.rglob('*'):
            if item.is_file():
                total_bytes += item.stat().st_size
                file_count += 1
            elif item.is_dir():
                dir_count += 1
    except Exception:
        pass

    return {
        'size_bytes': total_bytes,
        'size_mb': round(total_bytes / (1024 ** 2), 2),
        'size_gb': round(total_bytes / (1024 ** 3), 2),
        'file_count': file_count,
        'dir_count': dir_count
    }


def list_directory_contents(
    path: str,
    extensions: List[str] = None,
    recursive: bool = False
) -> List[Path]:
    """
    List directory contents, optionally filtered by extension.

    Args:
        path: Directory path
        extensions: List of file extensions to include (e.g., ['.json', '.csv'])
        recursive: If True, search recursively; if False, only direct children

    Returns:
        List of Path objects
    """
    path = Path(path)

    if not path.exists():
        return []

    if recursive:
        pattern = '**/*'
    else:
        pattern = '*'

    items = list(path.glob(pattern))

    if extensions:
        extensions = [e.lower() if e.startswith('.') else f'.{e}' for e in extensions]
        items = [i for i in items if i.suffix.lower() in extensions]

    return sorted(items)


def validate_installation_directory(base_path: str) -> dict:
    """
    Validate that installation directory contains expected structure.

    Args:
        base_path: Installation directory path

    Returns:
        Dictionary with validation results:
        - valid: bool indicating if all required files present
        - model_files: list of files in model/
        - document_files: list of files in documents/
        - metadata_files: list of files in metadata/
        - missing: list of expected but missing components
    """
    base = Path(base_path)
    results = {
        'valid': True,
        'model_files': [],
        'document_files': [],
        'metadata_files': [],
        'documentation_files': [],
        'missing': []
    }

    from _library.installation import validate_data
    results['missing'] = validate_data(base)
    results['valid'] = not results['missing']

    return results


def cleanup_downloads(base_path: str, keep_zips: bool = False) -> dict:
    """
    Clean up temporary download files.

    Args:
        base_path: Installation directory
        keep_zips: If True, keep zip files; if False, delete them

    Returns:
        Dictionary with cleanup results:
        - deleted: list of deleted files
        - kept: list of kept files
        - freed_mb: MB of space freed
    """
    downloads_dir = Path(base_path) / 'downloads'
    results = {
        'deleted': [],
        'kept': [],
        'freed_mb': 0
    }

    if not downloads_dir.exists():
        return results

    for filepath in downloads_dir.glob('*'):
        if filepath.is_file():
            size = filepath.stat().st_size
            size_mb = size / (1024 ** 2)

            if keep_zips and filepath.suffix == '.zip':
                results['kept'].append(filepath.name)
            else:
                try:
                    filepath.unlink()
                    results['deleted'].append(filepath.name)
                    results['freed_mb'] += size_mb
                except Exception:
                    pass

    results['freed_mb'] = round(results['freed_mb'], 2)
    return results
