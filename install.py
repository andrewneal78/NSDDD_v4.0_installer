"""
NSDDD v4.0 — Interactive Installer

Run this script once to download and install the dataset:
    python3 install.py

Then double-click Launch.command (Mac) or Launch.vbs (Windows) to start.
"""

import json
import os
import platform
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure we can import utils and config from the repo root
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent
sys.path.insert(0, str(REPO_ROOT))

from config import (
    DATASHARE_API_BASE,
    DATASHARE_HANDLE,
    DOWNLOADS,
    DEFAULT_INSTALL_DIR,
    DISK_SPACE_REQUIRED_MIN_GB,
    RAM_REQUIRED_GB,
    RAM_RECOMMENDED_GB,
    PYTHON_VERSION_MIN,
    DATASET_NAME,
)
from utils.datashare import DataShareClient
from utils.download import download_file, check_disk_space, calculate_total_size
from utils.extract import extract_with_progress
from utils.setup import create_directory_structure, validate_installation_directory
from utils.verify import verify_directory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _separator():
    print('=' * 60)


def _header(title: str):
    _separator()
    print(f'  {title}')
    _separator()


def _install_ai_headings(venv_py) -> None:
    """Optional: the llama.cpp runtime for AI-written cluster headings, from a prebuilt wheel only (never compiled here).
    macOS (Apple silicon): the wheel bundled in wheels/ (the published macOS wheels are corrupt upstream, 2026-10).
    Windows and Linux: the project's CPU wheel index. Anything else (Intel Mac, unusual platforms) or any failure:
    skipped, and cluster headings use keywords. Never stops the install."""
    pinned = 'llama-cpp-python==0.3.36'
    system, machine = platform.system(), platform.machine().lower()
    if system == 'Darwin' and machine == 'arm64':
        args = ['--find-links', str(REPO_ROOT / 'wheels')]
    elif system in ('Windows', 'Linux') and machine in ('amd64', 'x86_64', 'aarch64', 'arm64'):
        args = ['--extra-index-url', 'https://abetlen.github.io/llama-cpp-python/whl/cpu']
    else:
        print(f'  – AI cluster headings: no prebuilt runtime for {system} {machine}; clusters will stay numbered (no AI headings)')
        return
    print('  Installing the AI-headings runtime (optional)...')
    result = subprocess.run([str(venv_py), '-m', 'pip', 'install', '--only-binary=:all:', *args, pinned],
                            capture_output=True, text=True)
    ok = result.returncode == 0 and subprocess.run(
        [str(venv_py), '-c', 'import llama_cpp'], capture_output=True).returncode == 0
    print("  ✓ AI-headings runtime installed" if ok else "  – AI-headings runtime unavailable; clusters stay numbered.")


def _check_python() -> bool:
    v = sys.version_info
    ok = PYTHON_VERSION_MIN <= (v.major, v.minor) <= (3, 12)
    status = '✓' if ok else '✗'
    print(f'  {status} Python {v.major}.{v.minor}', end='')
    if not ok:
        min_v = '.'.join(str(x) for x in PYTHON_VERSION_MIN)
        print(' (this release requires Python 3.11 or 3.12)')
    else:
        print()
    return ok


def _constraints_name() -> str:
    """Intel Macs have their own tested package set (PyTorch 2.9 has no Intel-Mac build)."""
    intel_mac = platform.system() == 'Darwin' and platform.machine().lower() == 'x86_64'
    return 'constraints-intel-mac.txt' if intel_mac else 'constraints.txt'


def _check_windows_python_compatibility() -> bool:
    """The pinned numerical wheels require a 64-bit interpreter."""
    if sys.maxsize <= 2**32:
        print('  ✗ Install a 64-bit Python interpreter for this release.')
        return False
    if platform.system() == 'Darwin' and platform.machine().lower() == 'x86_64':
        print('  – Intel Mac: using the older PyTorch 2.2.2 (the only Intel-Mac build). Searches work the same but run more slowly, '
              'and AI headings are not available (no prebuilt runtime).')
    return True


def _check_disk(path: str) -> tuple:
    ok, available_gb, required_gb = check_disk_space(path, DISK_SPACE_REQUIRED_MIN_GB)
    status = '✓' if ok else '✗'
    print(f'  {status} Disk: {available_gb:.0f} GB available ({required_gb} GB required)')
    return ok, available_gb


def _detect_ram_gb() -> float:
    """Best-effort physical RAM detection without requiring third-party packages."""
    try:
        import psutil
        return psutil.virtual_memory().total / (1024 ** 3)
    except Exception:
        pass

    system = platform.system()

    try:
        if system == 'Darwin':
            result = subprocess.run(
                ['sysctl', '-n', 'hw.memsize'],
                capture_output=True,
                text=True,
                check=True,
            )
            return int(result.stdout.strip()) / (1024 ** 3)

        if system == 'Linux':
            pages = os.sysconf('SC_PHYS_PAGES')
            page_size = os.sysconf('SC_PAGE_SIZE')
            return (pages * page_size) / (1024 ** 3)

        if system == 'Windows':
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ('dwLength', ctypes.c_ulong),
                    ('dwMemoryLoad', ctypes.c_ulong),
                    ('ullTotalPhys', ctypes.c_ulonglong),
                    ('ullAvailPhys', ctypes.c_ulonglong),
                    ('ullTotalPageFile', ctypes.c_ulonglong),
                    ('ullAvailPageFile', ctypes.c_ulonglong),
                    ('ullTotalVirtual', ctypes.c_ulonglong),
                    ('ullAvailVirtual', ctypes.c_ulonglong),
                    ('ullAvailExtendedVirtual', ctypes.c_ulonglong),
                ]

            memory_status = MEMORYSTATUSEX()
            memory_status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory_status)):
                return memory_status.ullTotalPhys / (1024 ** 3)
    except Exception:
        pass

    return 0


def _check_ram() -> int:
    """Return detected RAM in GB (0 if unknown)."""
    ram_gb = _detect_ram_gb()
    status = '✓' if ram_gb >= RAM_REQUIRED_GB or ram_gb == 0 else '⚠'
    if ram_gb > 0:
        print(f'  {status} RAM: {ram_gb:.0f} GB detected')
        if ram_gb < RAM_REQUIRED_GB:
            print(f'    (minimum {RAM_REQUIRED_GB} GB: search needs about 3 GB for itself, plus the system and browser; with less RAM '
                  f'the computer will swap to disk and searches will be slow)')
        elif ram_gb < RAM_RECOMMENDED_GB:
            print(f'    (enough; {RAM_RECOMMENDED_GB} GB recommended if you keep other large programs open)')
    else:
        print('  ? RAM: could not detect automatically')
    return int(ram_gb)


def _is_windows_unc_path(path: Path | str) -> bool:
    """Return True when running on Windows and the path is a UNC/network path."""
    if platform.system() != 'Windows':
        return False
    return str(path).startswith('\\\\')


def _abort_for_windows_network_share(path: Path):
    print()
    print('Windows network-share installs are not supported for this installer.')
    print(f'Current path: {path}')
    print()
    print('Please copy or extract the installer to a local Windows folder first, for example:')
    print(r'  C:\Users\your-name\Downloads\NSDDD_v4.0_installer-main')
    print()
    print('Then open a terminal in that local folder and run:')
    print(r'  python install.py')
    sys.exit(1)


def _prompt_install_dir() -> Path:
    default = REPO_ROOT / DEFAULT_INSTALL_DIR
    print()
    print('Press Enter to accept the default location, or type a different folder path.')
    raw = input(f'Install directory [{default}]: ').strip()
    chosen = Path(raw) if raw else default
    return chosen



def _python_exe(venv_dir: Path) -> Path:
    """Return the Python executable path for a given venv directory."""
    if platform.system() == 'Windows':
        return venv_dir / 'Scripts' / 'python.exe'
    return venv_dir / 'bin' / 'python3'


def _find_existing_venvs() -> list:
    """
    Return list of (label, python_path) tuples for venvs that exist and have voila.
    Checks: currently active venv, common locations relative to repo and home.
    """
    found = []
    seen = set()

    candidates = []

    # Currently active venv (VIRTUAL_ENV env var)
    active = os.environ.get('VIRTUAL_ENV')
    if active:
        candidates.append(('Currently active venv', Path(active)))

    # Common locations
    candidates += [
        ('Repo .venv',  REPO_ROOT / '.venv'),
        ('Repo venv',   REPO_ROOT / 'venv'),
        ('~/.venv',     Path.home() / '.venv'),
        ('~/venv',      Path.home() / 'venv'),
    ]

    for label, venv_dir in candidates:
        py = _python_exe(venv_dir)
        key = str(py.resolve()) if py.exists() else str(py)
        if not py.exists() or key in seen:
            continue
        seen.add(key)
        # Check voila is importable
        result = subprocess.run(
            [str(py), '-c', 'import voila'],
            capture_output=True,
        )
        has_voila = result.returncode == 0
        found.append((label, py, has_voila))

    return found


def _prompt_venv() -> Path:
    """
    Prompt the user to choose an existing venv or create a new one.
    Returns the Python executable path to use.
    """
    existing = _find_existing_venvs()
    new_venv_dir = REPO_ROOT / '.venv'

    print()
    print('Python environment:')
    print()
    print('  The installer will set up a virtual environment — a self-contained')
    print('  folder that holds all the Python packages this tool needs. It has no')
    print('  effect on the rest of your system: nothing is changed globally, and')
    print('  you can remove it at any time by deleting the installer folder.')
    print()

    options = []
    for label, py, has_voila in existing:
        voila_tag = '✓ voila' if has_voila else '  no voila'
        print(f'  [{len(options) + 1}] Use {label} ({voila_tag})')
        print(f'      {py}')
        options.append(('existing', py))

    new_idx = len(options) + 1
    print(f'  [{new_idx}] Create new .venv inside installer directory')

    while True:
        raw = input(f'Choose [1-{new_idx}] (default {new_idx}): ').strip()
        if not raw:
            choice = new_idx
        elif raw.isdigit() and 1 <= int(raw) <= new_idx:
            choice = int(raw)
        else:
            print(f'  Please enter a number between 1 and {new_idx}.')
            continue
        break

    if choice == new_idx:
        return None  # Caller will create new venv
    else:
        _, py, _ = existing[choice - 1]
        return py


def _install_dependencies() -> Path:
    """
    Set up the Python environment and install dependencies.
    Returns the Python executable path used.
    """
    req_file = REPO_ROOT / 'requirements.txt'

    chosen_py = _prompt_venv()

    if chosen_py is None:
        # Create a new .venv
        venv_dir = REPO_ROOT / '.venv'
        venv_py = _python_exe(venv_dir)
        if not venv_py.exists():
            print('  Creating virtual environment (.venv)...')
            result = subprocess.run(
                [sys.executable, '-m', 'venv', str(venv_dir)],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                print('  ⚠ Could not create venv:')
                for line in result.stderr.splitlines()[-5:]:
                    print(f'    {line}')
                sys.exit(1)
            print('  ✓ Virtual environment created')
        else:
            print('  ✓ .venv already exists')
    else:
        venv_py = chosen_py
        print(f'  ✓ Using {venv_py}')

    if platform.system() == 'Linux':
        result = subprocess.run([str(venv_py), '-m', 'pip', 'install', 'torch==2.9.1',
                                 '--index-url', 'https://download.pytorch.org/whl/cpu'])
        if result.returncode:
            sys.exit('CPU PyTorch installation failed')

    # Install requirements
    if req_file.exists():
        print('  Installing Python dependencies...')
        result = subprocess.run(
            [str(venv_py), '-m', 'pip', 'install', '-r', str(req_file), '-c', str(REPO_ROOT / _constraints_name())],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print('  ⚠ pip install reported errors:')
            for line in result.stderr.splitlines()[-5:]:
                print(f'    {line}')
        else:
            print('  ✓ Dependencies installed')
    else:
        print('  ⚠ requirements.txt not found — skipping')

    # Install voila
    result = subprocess.run(
        [str(venv_py), '-c', 'import voila'],
        capture_output=True,
    )
    if result.returncode != 0:
        print('  Installing voila...')
        result = subprocess.run(
            [str(venv_py), '-m', 'pip', 'install', 'voila'],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            print('  ✓ voila installed')
        else:
            print('  ⚠ voila install failed — install manually: pip install voila')
    else:
        print('  ✓ voila already installed')

    required_imports = [
        ('voila', 'voila'),
        ('ipywidgets', 'ipywidgets'),
        ('numpy', 'numpy'),
        ('pandas', 'pandas'),
        ('matplotlib', 'matplotlib'),
        ('seaborn', 'seaborn'),
        ('tqdm', 'tqdm'),
        ('requests', 'requests'),
        ('torch', 'torch'),
        ('sentence-transformers', 'sentence_transformers'),
    ]

    missing = []
    for package_name, import_name in required_imports:
        result = subprocess.run(
            [str(venv_py), '-c', f'import {import_name}'],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            missing.append(package_name)

    if missing:
        print('  ✗ Some required Python packages are still missing:')
        for name in missing:
            print(f'    - {name}')
        print('  Re-run the installer with a supported Python version, or install the missing packages into the selected environment.')
        sys.exit(1)

    print('  ✓ Core Python packages verified')

    return venv_py


def _ensure_windows_runtime():
    if platform.system() != 'Windows':
        return
    import ctypes
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64') as key:
            version = winreg.QueryValueEx(key, 'Version')[0]
        if tuple(int(v) for v in version.lstrip('vV').split('.')) >= (14, 44, 35211, 0):
            ctypes.WinDLL('MSVCP140.dll')
            return
    except OSError:
        pass
    import tempfile
    import urllib.request
    print('Installing the Microsoft VC++ x64 runtime; accept its licence/administrator prompt.')
    with tempfile.TemporaryDirectory(prefix='nsddd-vc-') as tmp:
        installer = Path(tmp) / 'vc_redist.x64.exe'
        urllib.request.urlretrieve('https://aka.ms/vs/17/release/vc_redist.x64.exe', installer)
        status = subprocess.run([str(installer), '/install', '/norestart']).returncode
        if status == 3010:
            sys.exit('Restart Windows, then rerun install.py to finish setup.')
        if status not in (0, 1638):
            sys.exit(f'Microsoft VC++ runtime setup failed (exit {status}).')
        ctypes.WinDLL('MSVCP140.dll')


def _make_launcher_executable():
    launcher = REPO_ROOT / 'Launch.command'
    if launcher.exists() and platform.system() == 'Darwin':
        try:
            launcher.chmod(launcher.stat().st_mode | 0o111)
        except Exception:
            pass


def _is_already_extracted(spec: dict, install_dir: Path) -> bool:
    """Return True if this download's files are already present in any known workspace."""
    filename = spec['filename']
    subdir = spec['extract_to'].rstrip('/')
    expected_files = spec.get('expected_files', [])
    expected_any = spec.get('expected_any', [])

    # Candidate locations: chosen install dir + repo-local workspace
    candidates = [install_dir / subdir]

    def _contains_expected_files(extract_to: Path) -> bool:
        if not extract_to.is_dir():
            return False

        def _exists_anywhere(name: str) -> bool:
            return (extract_to / name).is_file() and (extract_to / name).stat().st_size > 0

        if expected_files and not all(_exists_anywhere(name) for name in expected_files):
            return False

        for group in expected_any:
            if not any(_exists_anywhere(name) for name in group):
                return False

        if expected_files or expected_any:
            return True

        return any(f.is_file() for f in extract_to.rglob('*'))

    for extract_to in candidates:
        if filename.endswith('.zip'):
            if _contains_expected_files(extract_to):
                return True
        else:
            if (extract_to / filename).exists():
                return True

    return False


def _download_encoder(install_dir: Path, venv_py: Path):
    """Verify the Qwen3-Embedding-0.6B encoder is present (v4.0: hosted on DataShare as encoder_model.zip,
    extracted to model/qwen3-embedding-0.6b/ — no HuggingFace pull at install)."""
    model_dir = install_dir / 'model' / 'qwen3-embedding-0.6b'
    if model_dir.exists() and any(model_dir.iterdir()):
        print('  ✓ Encoder (Qwen3-Embedding-0.6B) present')
    else:
        print('  ⚠ Encoder not found in model/qwen3-embedding-0.6b — ensure encoder_model.zip downloaded')

def _write_install_config(install_path: Path, python_path: Path):
    config = {
        'install_path': str(install_path),
        'installer_root': str(REPO_ROOT),
        'python': str(python_path),
    }
    config_path = REPO_ROOT / 'install_config.json'
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)


def _cleanup_stale_archives(downloads_dir: Path):
    """
    Remove leftover ZIP archives from downloads directory.

    Extraction already removes ZIP files on success, but older installer runs
    may have left archives behind. This pass keeps workspace size predictable.
    """
    if not downloads_dir.exists():
        return

    removed = []
    for spec in DOWNLOADS.values():
        filename = spec.get('filename', '')
        if not filename.endswith('.zip'):
            continue
        archive = downloads_dir / filename
        if archive.exists():
            try:
                archive.unlink()
                removed.append(filename)
            except Exception:
                pass

    if removed:
        print('  ✓ Cleaned leftover archives from downloads/:')
        for name in removed:
            print(f'    - {name}')


# ---------------------------------------------------------------------------
# Main installer flow
# ---------------------------------------------------------------------------

def main():
    _header(f'NSDDD v4.0 — Installer')
    print()
    print('Checking system requirements...')

    py_ok = _check_python()
    if not py_ok:
        print()
        print('Use 64-bit Python 3.11 or 3.12 for this release and try again.')
        sys.exit(1)

    if not _check_windows_python_compatibility():
        print()
        print('Please install Python 3.11 or 3.12, then run the installer again.')
        sys.exit(1)

    if _is_windows_unc_path(REPO_ROOT):
        _abort_for_windows_network_share(REPO_ROOT)

    # Determine install dir before disk check (need path to check disk)
    install_dir = _prompt_install_dir()

    if _is_windows_unc_path(install_dir):
        _abort_for_windows_network_share(install_dir)

    disk_ok, available_gb = _check_disk(str(install_dir))
    _check_ram()

    if not disk_ok:
        print()
        print(f'Insufficient disk space at {install_dir}.')
        print(f'Free up space and try again.')
        sys.exit(1)

    # Compute all downloads: required files only
    required_keys = [k for k, v in DOWNLOADS.items() if v.get('required')]
    # 'soft' items (the optional AI-heading model) are fetched with the rest, but a failure never stops the install
    low_power = os.environ.get('NSDDD_LOW_POWER', '').lower() in ('1', 'true', 'yes')
    all_selected = required_keys + ([] if low_power else [k for k, v in DOWNLOADS.items() if v.get('soft')])

    # Exclude already-installed files from size calculation
    install_dir.mkdir(parents=True, exist_ok=True)
    to_download = [k for k in all_selected if not _is_already_extracted(DOWNLOADS[k], install_dir)]
    size_info = calculate_total_size(DOWNLOADS, to_download)
    total_gb = size_info['total_gb']

    print()
    if to_download:
        print(f'Downloading required files ({total_gb:.1f} GB)...')
    else:
        print('All files already installed — skipping downloads.')

    # Initialise DataShare client
    client = DataShareClient(DATASHARE_API_BASE, DATASHARE_HANDLE)
    try:
        if to_download:
            client.list_bitstreams()
    except Exception as e:
        print()
        print(f'Could not connect to Edinburgh DataShare: {e}')
        print('Please check your internet connection and run the installer again.')
        sys.exit(1)

    # Create directory structure
    dirs = create_directory_structure(str(install_dir))
    downloads_dir = dirs['downloads']
    failed_required, failed_soft = [], []

    # Download each selected file
    for key in all_selected:
        spec = DOWNLOADS[key]
        filename = spec['filename']
        size_mb = spec['size_mb']

        # Skip if already extracted
        if _is_already_extracted(spec, install_dir):
            extract_to = install_dir / spec['extract_to'].rstrip('/')
            print(f'  ✓ {filename:<45} already installed — skipping')
            continue

        # Get download URL from DataShare
        try:
            file_info = client.get_file_info(filename)
            url = file_info['download_url']
            expected_bytes = file_info['size_bytes']
        except Exception as e:
            print(f'  ✗ Could not resolve {filename}: {e}')
            (failed_soft if spec.get('soft') else failed_required).append(filename)
            continue

        dest = downloads_dir / filename
        size_str = (
            f'{size_mb / 1024:.1f} GB' if size_mb >= 1024
            else f'{size_mb:.0f} MB' if size_mb >= 1
            else f'{size_mb:.3f} MB'
        )
        print(f'  {filename:<45} {size_str:>8}', end='  ', flush=True)

        try:
            download_file(
                url=url,
                destination=str(dest),
                expected_size=expected_bytes,
                progress_callback=_progress_bar,
            )
            print(' ✓')
        except Exception as e:
            print(f'\n  ✗ Download failed: {e}')
            (failed_soft if spec.get('soft') else failed_required).append(filename)
            continue

        # Extract
        extract_to = install_dir / spec['extract_to'].rstrip('/')
        if filename.endswith('.zip'):
            print(f'    Extracting...', end='  ', flush=True)
            try:
                extract_with_progress(dest, extract_to, verbose=False)
                print('✓')
                # Remove zip to save space
                dest.unlink(missing_ok=True)
            except Exception as e:
                print(f'\n  ✗ Extraction failed: {e}')
                (failed_soft if spec.get('soft') else failed_required).append(filename)
        else:
            # Plain file — just move to destination
            extract_to.mkdir(parents=True, exist_ok=True)
            import shutil as _shutil
            try:
                _shutil.move(str(dest), str(extract_to / filename))
            except Exception as e:
                print(f'\n  ✗ Move failed: {e}')
                (failed_soft if spec.get('soft') else failed_required).append(filename)

    if failed_soft:
        print()
        print(f"  ⚠ Optional files not installed: {', '.join(sorted(set(failed_soft)))}")
        print('    The search still works; cluster headings will use keywords instead of the small language model.')

    if failed_required:
        print()
        print('Installation could not continue because required files failed:')
        for name in sorted(set(failed_required)):
            print(f'  - {name}')
        rerun_command = 'python install.py' if platform.system() == 'Windows' else 'python3 install.py'
        print(f'Re-run `{rerun_command}` to retry the missing required files.')
        sys.exit(1)

    print()
    print('Installing dependencies...')
    _ensure_windows_runtime()
    venv_py = _install_dependencies()
    if not low_power:
        _install_ai_headings(venv_py)

    print()
    print('Downloading encoder model...')
    _download_encoder(install_dir, venv_py)

    print()
    print('Verifying installation...')
    # Use the selected interpreter for integrity and real application checks.
    check = subprocess.run([str(venv_py), str(REPO_ROOT / 'verify_install.py'),
                            '--install-path', str(install_dir)], cwd=str(REPO_ROOT))
    if check.returncode:
        print('  ✗ Installation verification failed. Correct the errors above and rerun setup.')
        sys.exit(1)

    print()
    print('Cleaning installer download cache...')
    _cleanup_stale_archives(downloads_dir)

    # Write config and make launcher executable
    _write_install_config(install_dir, venv_py)
    _make_launcher_executable()

    print()
    _separator()
    on_mac = platform.system() == 'Darwin'
    on_win = platform.system() == 'Windows'
    if on_mac:
        print('  ✓ Installation complete. Double-click Launch.command to start.')
    elif on_win:
        print('  ✓ Installation complete. Double-click Launch.vbs to start.')
    else:
        print('  ✓ Installation complete. Run: python3 launch.py')
    _separator()
    print()


# ---------------------------------------------------------------------------
# Progress bar helper
# ---------------------------------------------------------------------------

_last_pct = -1


def _progress_bar(downloaded: int, total: int):
    global _last_pct
    if total <= 0:
        return
    pct = int(downloaded * 100 / total)
    if pct == _last_pct:
        return
    _last_pct = pct
    filled = pct // 5
    bar = '█' * filled + '░' * (20 - filled)
    print(f'\r    [{bar}] {pct:3d}%', end='', flush=True)


if __name__ == '__main__':
    _last_pct = -1
    main()
