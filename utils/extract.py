"""
Extraction utilities for NSDDD v3 installation.

Handles zip file extraction with path flattening for nested archives.
"""

import zipfile
import shutil
from pathlib import Path
from typing import Optional


def extract_zip_flat(
    zip_path: Path,
    extract_to: Path,
    strip_components: Optional[int] = None,
    target_folder: Optional[str] = None
) -> None:
    """
    Extract zip file, optionally stripping path components or extracting only files from a target folder.

    Args:
        zip_path: Path to zip file
        extract_to: Destination directory
        strip_components: Number of leading path components to strip (like tar --strip-components)
        target_folder: Only extract files whose paths end with this folder name (e.g., 'model' or 'metadata')

    Example:
        If zip contains: Users/aneal/.../model/file.json
        And target_folder='model'
        Result: extract_to/file.json (strips everything before 'model/')
    """
    extract_to.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        for member in zip_ref.namelist():
            # Skip directories
            if member.endswith('/'):
                continue

            # Parse the path
            parts = Path(member).parts

            # If target_folder specified, find it in the path and extract from there
            if target_folder:
                try:
                    # Find the target folder in the path
                    target_idx = parts.index(target_folder)
                    # Keep only the target folder and everything after it
                    new_parts = parts[target_idx + 1:]

                    if not new_parts:
                        # File is directly in target folder with no name (shouldn't happen)
                        continue

                    new_path = extract_to / Path(*new_parts)
                except ValueError:
                    # Target folder not in this path, skip it
                    continue

            # Otherwise use strip_components
            elif strip_components is not None and strip_components > 0:
                if len(parts) <= strip_components:
                    # Not enough components to strip, skip
                    continue
                new_parts = parts[strip_components:]
                new_path = extract_to / Path(*new_parts)

            else:
                # No stripping, use original path
                new_path = extract_to / member

            # Reject archive paths escaping the selected destination.
            if not new_path.resolve().is_relative_to(extract_to.resolve()):
                raise ValueError(f'Unsafe archive member: {member}')
            # Create parent directories
            new_path.parent.mkdir(parents=True, exist_ok=True)

            # Extract the file
            with zip_ref.open(member) as source, open(new_path, 'wb') as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)


def extract_with_progress(
    zip_path: Path,
    extract_to: Path,
    target_folder: Optional[str] = None,
    verbose: bool = True
) -> dict:
    """
    Extract zip file with progress reporting.

    Args:
        zip_path: Path to zip file
        extract_to: Destination directory
        target_folder: Only extract files from this folder (e.g., 'model')
        verbose: Print progress messages

    Returns:
        Dictionary with extraction stats (files_extracted, bytes_extracted)
    """
    files_extracted = 0
    bytes_extracted = 0

    extract_to.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        members = [m for m in zip_ref.namelist() if not m.endswith('/')]

        for member in members:
            parts = Path(member).parts

            # Filter by target_folder if specified
            if target_folder:
                try:
                    target_idx = parts.index(target_folder)
                    new_parts = parts[target_idx + 1:]
                    if not new_parts:
                        continue
                    new_path = extract_to / Path(*new_parts)
                except ValueError:
                    continue
            else:
                new_path = extract_to / member

            # Reject archive paths escaping the selected destination.
            if not new_path.resolve().is_relative_to(extract_to.resolve()):
                raise ValueError(f'Unsafe archive member: {member}')
            # Create parent directories
            new_path.parent.mkdir(parents=True, exist_ok=True)

            # Extract file
            with zip_ref.open(member) as source, open(new_path, 'wb') as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)
                bytes_extracted += zip_ref.getinfo(member).file_size
                files_extracted += 1

                if verbose and files_extracted % 10 == 0:
                    print(f'  Extracted {files_extracted} files...', end='\r')

    if verbose and files_extracted > 0:
        print(f'  ✓ Extracted {files_extracted} files ({bytes_extracted / (1024**2):.1f} MB)' + ' ' * 20)

    return {
        'files_extracted': files_extracted,
        'bytes_extracted': bytes_extracted
    }
