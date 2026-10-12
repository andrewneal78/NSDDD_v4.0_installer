"""
NSDDD v4.0 Installer launcher.

- Starts the Voilà interface.
- Checks for updates at startup.
  - Git installs: uses `git fetch` + `git pull --ff-only`.
  - Download/ZIP installs: compares local VERSION with remote VERSION,
    then downloads and overlays the latest repo zip while preserving user data.
"""

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import urllib.error
import zipfile
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8867
URL = f"http://{HOST}:{PORT}"
NOTEBOOK = "document_metadata_search_voila.ipynb"

REPO_OWNER = "andrewneal78"
REPO_NAME = "NSDDD_v4.0_installer"
DEFAULT_BRANCH = "main"

RAW_VERSION_URL = (
    f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{DEFAULT_BRANCH}/VERSION"
)
ZIP_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/archive/refs/heads/{DEFAULT_BRANCH}.zip"

# Updates (pre-release, October 2026): a download-install (the Windows package, or a Mac install from the GitHub zip) checks for a
# new version each time it starts, installs it, and tells the user (in this window and on the search page). A git checkout (a
# developer's working copy) only announces updates; run `python launch.py --update` to pull. Set NSDDD_AUTO_UPDATE=0 to stop
# automatic installs everywhere, or NSDDD_AUTO_UPDATE=1 to allow them in a git checkout.
AUTO_UPDATE_SETTING = os.environ.get("NSDDD_AUTO_UPDATE", "")
AUTO_UPDATE_ENABLED = AUTO_UPDATE_SETTING != "0"
UPDATE_NOTICE = "update_notice.json"
SHOW_TRACEBACKS_ENABLED = os.environ.get("NSDDD_SHOW_TRACEBACKS", "1") != "0"
HTTP_TIMEOUT_SECONDS = 8

# Preserve local data/environments when overlaying ZIP updates.
PRESERVE_TOP_LEVEL = {
    ".git",
    ".venv",
    "NSDDD_v3.5_workspace",
    "NSDDD_v4.0_workspace",
    "XHR",
    "install_config.json",
    "data",
    "wheels",
    "outputs",
    "__pycache__",
    ".ipynb_checkpoints",
}


def configured_python(cwd: Path) -> str | None:
    """Return the installer-selected Python, if recorded and still present."""
    config_path = cwd / "install_config.json"
    if not config_path.exists():
        return None

    try:
        import json

        data = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    python_path = data.get("python")
    if not python_path:
        return None

    from _library.runtime import resolve_path
    py = resolve_path(python_path, cwd)
    return str(py) if py.exists() else None


def find_python():
    """Return a Python executable that has voila importable."""
    cwd = Path(__file__).parent
    candidates = []

    configured = configured_python(cwd)
    if configured:
        candidates.append(Path(configured))

    if os.name == "nt":
        candidates.extend(
            [
                cwd / ".venv" / "Scripts" / "python.exe",
                cwd / "venv" / "Scripts" / "python.exe",
                Path.home() / ".venv" / "Scripts" / "python.exe",
                Path.home() / "venv" / "Scripts" / "python.exe",
            ]
        )
    else:
        candidates.extend(
            [
                cwd / ".venv" / "bin" / "python3",
                cwd / "venv" / "bin" / "python3",
                Path.home() / ".venv" / "bin" / "python3",
                Path.home() / "venv" / "bin" / "python3",
            ]
        )

    candidates.append(Path(sys.executable))

    seen = set()
    for py in candidates:
        if not py.exists():
            continue
        resolved = str(py.resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        r = subprocess.run([str(py), "-c", "import voila"], capture_output=True)
        if r.returncode == 0:
            return str(py)
    return sys.executable


def choose_port(preferred=8867):
    """Select an unused loopback port without terminating another application."""
    import socket
    with socket.socket() as sock:
        try:
            sock.bind((HOST, preferred))
        except OSError:
            sock.bind((HOST, 0))
        return sock.getsockname()[1]


def _open_url(url, timeout):
    """urlopen that also works when the system certificate store lacks GitHub's root (a fresh Windows install
    or virtual machine): tries the system store first, then the certifi bundle that Setup installs."""
    import ssl
    try:
        return urllib.request.urlopen(url, timeout=timeout)
    except urllib.error.URLError as e:
        if not isinstance(getattr(e, "reason", None), ssl.SSLError):
            raise
        try:
            import certifi
        except ImportError:
            raise e
        return urllib.request.urlopen(url, timeout=timeout, context=ssl.create_default_context(cafile=certifi.where()))


def fetch_text(url: str) -> str | None:
    try:
        with _open_url(url, HTTP_TIMEOUT_SECONDS) as resp:
            return resp.read().decode("utf-8").strip()
    except Exception:
        return None


def local_version(cwd: Path) -> str:
    vf = cwd / "VERSION"
    if not vf.exists():
        return ""
    return vf.read_text(encoding="utf-8").strip()


def write_local_version(cwd: Path, version: str):
    (cwd / "VERSION").write_text(version.strip() + "\n", encoding="utf-8")


def is_git_install(cwd: Path) -> bool:
    return (cwd / ".git").exists()


def git_rev(cwd: Path, ref: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(cwd), "rev-parse", ref],
        capture_output=True,
        text=True,
    )
    return r.stdout.strip() if r.returncode == 0 else ""


def check_git_update(cwd: Path) -> tuple[bool, str, str]:
    fetch = subprocess.run(
        ["git", "-C", str(cwd), "fetch", "origin", DEFAULT_BRANCH],
        capture_output=True,
        text=True,
    )
    if fetch.returncode != 0:
        return False, "", ""

    local = git_rev(cwd, "HEAD")
    remote = git_rev(cwd, f"origin/{DEFAULT_BRANCH}")
    if not local or not remote:
        return False, local, remote
    return local != remote, local, remote


def apply_git_update(cwd: Path) -> bool:
    pull = subprocess.run(
        ["git", "-C", str(cwd), "pull", "--ff-only", "origin", DEFAULT_BRANCH],
        capture_output=True,
        text=True,
    )
    if pull.returncode == 0:
        print("✓ Git update applied.")
        return True

    print("⚠️  Git update failed:")
    if pull.stderr.strip():
        print(pull.stderr.strip())
    return False


def _is_newer(remote: str, local: str) -> bool:
    """True when `remote` is a later version than `local` (dotted numbers, e.g. 2026.10.12.1); never downgrades."""
    def key(v: str):
        return tuple(int(x) for x in re.findall(r"\d+", v or ""))
    return key(remote) > key(local) if key(local) else bool(key(remote))


def check_zip_update(cwd: Path) -> tuple[bool, str, str]:
    local = local_version(cwd)
    remote = fetch_text(RAW_VERSION_URL) or ""
    if not remote:
        return False, local, remote
    return _is_newer(remote, local), local, remote


def remove_path(path: Path):
    if not path.exists():
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def overlay_tree(src: Path, dst: Path):
    for item in src.iterdir():
        if item.name in PRESERVE_TOP_LEVEL:
            continue
        target = dst / item.name
        if item.is_dir():
            if target.exists() and not target.is_dir():
                remove_path(target)
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def apply_zip_update(cwd: Path, remote_version: str) -> bool:
    try:
        with tempfile.TemporaryDirectory(prefix="nsddd_update_") as td:
            tmp = Path(td)
            zip_path = tmp / "update.zip"

            with _open_url(ZIP_URL, HTTP_TIMEOUT_SECONDS) as resp:
                zip_path.write_bytes(resp.read())

            extract_dir = tmp / "extract"
            extract_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)

            roots = [p for p in extract_dir.iterdir() if p.is_dir()]
            if not roots:
                print("⚠️  Update failed: could not find extracted root directory.")
                return False

            overlay_tree(roots[0], cwd)
            if remote_version:
                write_local_version(cwd, remote_version)

        print("✓ Download-install update applied.")
        return True
    except Exception as e:
        print(f"⚠️  Download-install update failed: {e}")
        return False


def write_update_notice(cwd: Path, before: str, after: str):
    try:
        (cwd / UPDATE_NOTICE).write_text(json.dumps({"from": before, "to": after}), encoding="utf-8")
    except OSError:
        pass


def maybe_update(cwd: Path, no_update: bool, apply: bool = False) -> bool:
    """Check for updates and install them when allowed. Returns True when files were updated.

    A download-install installs an available update unless NSDDD_AUTO_UPDATE=0; a git checkout only announces it
    unless apply=True (--update) or NSDDD_AUTO_UPDATE=1. A failed check never stops NSDDD from starting."""
    if no_update:
        return False
    git = is_git_install(cwd)
    apply = apply or (AUTO_UPDATE_ENABLED and not git) or AUTO_UPDATE_SETTING == "1"

    if git:
        print("Checking for updates (git)...")
        available, local, remote = check_git_update(cwd)
        if not available:
            print("✓ Already up to date.")
            return False
        print(f"🔄 Update available: {local[:7]} -> {remote[:7]}")
        if apply:
            return apply_git_update(cwd)
        print("ℹ️  Not installed. To update, run:  python launch.py --update")
        return False

    current = local_version(cwd)
    print(f"Checking for updates (current: v{current or 'unknown'})...")
    available, local, remote = check_zip_update(cwd)
    if not remote:
        print("ℹ️  Could not check for updates (no internet connection?). Carrying on with this version.")
        return False
    if not available:
        print("✓ Already up to date.")
        return False

    local_label = local or "(none)"
    print()
    print("=" * 62)
    print(f"  UPDATE AVAILABLE: {local_label} -> {remote}")
    if apply:
        print("  Installing it now. This takes a few seconds.")
    print("=" * 62)
    if apply:
        if apply_zip_update(cwd, remote):
            write_update_notice(cwd, local_label, remote)
            print(f"  NSDDD has been updated to version {remote}.")
            return True
        print("  The update could not be installed. NSDDD will start with the current version.")
        return False
    print("ℹ️  Not installed. To update, run:  python launch.py --update")
    return False


def restart_self():
    """Run the updated launcher as a child process (os.execv on Windows would detach and end the start script early)."""
    print("↻ Restarting with the updated files...")
    rc = subprocess.call([sys.executable, str(Path(__file__)), "--no-update"] + [a for a in sys.argv[1:] if a not in ("--update", "--no-update")])
    sys.exit(rc)


def build_voila_command(py: str) -> list[str]:
    cmd = [
        py,
        "-m",
        "voila",
        NOTEBOOK,
        f"--port={PORT}",
        "--Voila.port_retries=0",
        f"--Voila.ip={HOST}",
        "--no-browser",
        "--strip_sources=True",
        "--progressive_rendering=True",
        # Pass each pattern separately (the list-literal form is deprecated in traitlets 5 and
        # also triggers an invalid-escape SyntaxWarning when it eval's the list string).
        # Voila matches these against the path in the operating system's own form (XHR\84.html on Windows, XHR/84.html
        # elsewhere), so the separator is matched by [^A-Za-z0-9_] rather than '/' (a '/' pattern gave 403 on every Windows link).
        '--VoilaConfiguration.file_allowlist=outputs[^A-Za-z0-9_].*[.](csv|xlsx|svg|html)$',
        '--VoilaConfiguration.file_allowlist=XHR[^A-Za-z0-9_].*',
    ]
    if SHOW_TRACEBACKS_ENABLED:
        cmd.append("--show_tracebacks=True")
    return cmd


def open_browser(url: str):
    """Open the app URL using a platform-appropriate method."""
    try:
        if os.name == "nt":
            os.startfile(url)  # type: ignore[attr-defined]
            return
    except Exception:
        pass

    import webbrowser

    try:
        webbrowser.open(url)
    except Exception:
        pass


def open_browser_delayed(url: str, delay_seconds: float = 3.0):
    """Open the browser after a short delay without blocking server startup."""
    def _open():
        open_browser(url)

    timer = threading.Timer(delay_seconds, _open)
    timer.daemon = True
    timer.start()


def wait_for_server(url: str, timeout_seconds: float = 20.0) -> bool:
    """Poll until the local server responds or timeout expires."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status < 500:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def ensure_widget_comms_ok(py: str) -> None:
    """Disable JupyterLab extensions that break voila's widget comm layer.
    jupyter-collaboration's docprovider/collaboration extensions raise a federated-module error
    in voila ("Shared module @jupyterlab/statusbar doesn't exist"), which leaves all widgets
    (incl. the Search buttons) unresponsive. Best-effort + idempotent."""
    # Scope changes to this app and avoid repeating JupyterLab subprocesses.
    from importlib.util import find_spec
    if find_spec('jupyter_collaboration') is None and find_spec('jupyter_docprovider') is None:
        return
    marker = Path(os.environ['JUPYTER_CONFIG_DIR']) / 'widget_comms_fixed'
    if marker.exists():
        return
    marker.parent.mkdir(parents=True, exist_ok=True)
    for ext in ("@jupyter/docprovider-extension", "@jupyter/collaboration-extension"):
        try:
            subprocess.run([py, "-m", "jupyter", "labextension", "disable", ext],
                           capture_output=True, text=True, timeout=15, check=True)
        except Exception:
            return
    marker.touch()


def main():
    parser = argparse.ArgumentParser(description="Launch NSDDD search interface")
    global PORT, URL
    parser.add_argument("--low-power", action="store_true", help="Use two CPU threads, optional charts/exports and a smaller clustering limit")
    parser.add_argument("--detach", action="store_true", help="Start in background, open browser, then exit")
    parser.add_argument("--no-update", action="store_true", help="Skip update check on this run")
    parser.add_argument("--update", action="store_true", help="Install an available update (updates are otherwise only announced)")
    parser.add_argument("--update-only", action="store_true", help="Check for and install an update, then exit without starting the app")
    args = parser.parse_args()

    cwd = Path(__file__).parent

    if args.update_only:
        before = local_version(cwd)
        maybe_update(cwd, False, apply=True)
        print(f"Version before: {before or 'unknown'}; now: {local_version(cwd) or 'unknown'}")
        return

    if maybe_update(cwd, args.no_update, apply=args.update):
        restart_self()

    if args.no_update:
        os.environ['NSDDD_AUTO_UPDATE'] = '0'
    if args.low_power:
        os.environ['NSDDD_LOW_POWER'] = '1'
    from _library.runtime import configure_runtime
    configure_runtime()
    os.environ['JUPYTER_CONFIG_DIR'] = str(cwd / '.jupyter')
    PORT = choose_port(PORT)
    URL = f'http://{HOST}:{PORT}'
    os.environ['NSDDD_VOILA_BASE_URL'] = URL

    py = find_python()
    ensure_widget_comms_ok(py)
    cmd = build_voila_command(py)

    if args.detach:
        log_path = cwd / "launch.log"
        log_file = open(log_path, "a", encoding="utf-8")
        log_file.write(f"\n=== Launch at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        log_file.flush()
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            start_new_session=True,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        if wait_for_server(URL, timeout_seconds=20.0):
            open_browser(URL)
            sys.exit(0)

        rc = proc.poll()
        if rc is not None:
            print(f"NSDDD failed to start. See launch.log for details. (exit code {rc})")
            sys.exit(1)

        print("NSDDD started, but the browser did not open automatically.")
        print(f"Open {URL} manually if needed.")
        sys.exit(0)

    print("NSDDD Search Interface")
    print(f"  URL : {URL}")
    print("  Stop: Ctrl+C")
    print("  Note: browser may show 'server not found' for a few seconds.")
    print("  Please be patient and wait for the server to be ready.")
    print()

    open_browser_delayed(URL, delay_seconds=3.0)

    try:
        subprocess.run(cmd, cwd=str(cwd))
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    main()
