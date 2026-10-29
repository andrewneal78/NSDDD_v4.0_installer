#!/bin/bash
# NSDDD 4.0 installer for Mac: double-click this file. It needs no Python of its own.
#
# 1. Looks for Python 3.11 or 3.12 on this Mac.
# 2. If there is none, it downloads 'uv' (a small, widely used Python manager from Astral; a fixed version, checked against
#    the SHA-256 recorded below) and uses it to fetch a private Python 3.12 into the hidden folder .nsddd_python next to this file.
#    Nothing is installed system-wide.
# 3. Runs install.py with that Python (downloads the search index and models, about 2.5 GB, then checks everything).
#
# Options (for testing): --python-only  stop after finding or fetching Python and print where it is.
#                        NSDDD_FETCH_PYTHON=1  ignore any Python already on this Mac and fetch the private one.
cd "$(dirname "$0")" || exit 1
ONLY=0; [ "$1" = "--python-only" ] && ONLY=1

# uv release used to fetch Python, and the SHA-256 of each Mac build (from the release's .sha256 files, which match
# GitHub's own asset digests). To move to a newer uv, change all three together.
UV_VERSION="0.12.24"
UV_SHA256_ARM64="0c4346de7abdb49495b393b9ec809fe387aa43e586be20fecb972216c1e71732"
UV_SHA256_X86_64="4fa82e37cb94767661f532b001e470b67a186c7260e305bd84ddb78fd545c0b6"

fail() {        # print, keep the window open long enough to read it, and stop
    echo "$1"
    echo ""
    read -r -p "Press Return to close this window. "
    exit 1
}

echo "================================================"
echo "  NSDDD 4.0: installer for Mac"
echo "================================================"
echo ""

ok_python() {   # $1 = command or path; succeeds for a 64-bit CPython 3.11 or 3.12
    "$1" -c 'import sys; sys.exit(0 if sys.version_info[:2] in ((3,11),(3,12)) and sys.maxsize > 2**32 else 1)' 2>/dev/null
}

PYTHON=""
if [ -x ".nsddd_python/bin/python3" ] && ok_python .nsddd_python/bin/python3; then
    PYTHON="$PWD/.nsddd_python/bin/python3"
fi
if [ -z "$PYTHON" ] && [ "$NSDDD_FETCH_PYTHON" != "1" ]; then     # NSDDD_FETCH_PYTHON=1 ignores system Pythons (for testing)
    for c in python3.12 python3.11 python3 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 /usr/local/bin/python3.12 /usr/local/bin/python3.11 \
             /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 /Library/Frameworks/Python.framework/Versions/3.11/bin/python3; do
        if command -v "$c" >/dev/null 2>&1 && ok_python "$c"; then PYTHON="$(command -v "$c")"; break; fi
    done
fi

if [ -z "$PYTHON" ]; then
    echo "No Python 3.11 or 3.12 found. Fetching a private copy of Python 3.12 (about 40 MB, needs the internet)..."
    case "$(uname -m)" in
        arm64)  TRIPLE="aarch64-apple-darwin"; WANT="$UV_SHA256_ARM64" ;;
        x86_64) TRIPLE="x86_64-apple-darwin";  WANT="$UV_SHA256_X86_64" ;;
        *) fail "Unsupported processor: $(uname -m)" ;;
    esac
    BASE="https://github.com/astral-sh/uv/releases/download/$UV_VERSION"
    TMP="$(mktemp -d)" || fail "Could not create a temporary folder."
    trap 'rm -rf "$TMP"' EXIT
    if ! curl -fsSL "$BASE/uv-$TRIPLE.tar.gz" -o "$TMP/uv.tar.gz"; then
        fail "Could not download the Python manager. Check your internet connection, or install Python 3.12 from https://www.python.org/downloads/ and run this again."
    fi
    GOT="$(shasum -a 256 "$TMP/uv.tar.gz" | awk '{print $1}')"
    if [ "$WANT" != "$GOT" ]; then
        fail "The download did not match its recorded checksum, so it was not used. Please try again."
    fi
    tar -xzf "$TMP/uv.tar.gz" -C "$TMP" || fail "Could not unpack the Python manager."
    UV="$(find "$TMP" -name uv -type f | head -1)"
    STORE="$PWD/.nsddd_python/store"
    export UV_PYTHON_INSTALL_DIR="$STORE"
    export UV_PYTHON_BIN_DIR="$PWD/.nsddd_python/uvbin"        # keep uv's shortcut links inside this folder too
    "$UV" python install 3.12 || fail "Python could not be fetched."
    # Only the Python just fetched: without this, uv may return an active or nearby virtual environment instead
    FOUND="$("$UV" python find --managed-python --system --no-project 3.12)"
    STORE_REAL="$(cd "$STORE" && pwd -P)"                     # uv may report the path with symlinks resolved
    case "$FOUND" in
        "$STORE"/*)      REL="${FOUND#"$STORE"/}" ;;
        "$STORE_REAL"/*) REL="${FOUND#"$STORE_REAL"/}" ;;
        *) fail "The fetched Python was not where it was expected ($FOUND)." ;;
    esac
    mkdir -p .nsddd_python/bin && ln -sf "../store/$REL" .nsddd_python/bin/python3     # relative, so the folder can be moved before install
    if ok_python .nsddd_python/bin/python3; then PYTHON="$PWD/.nsddd_python/bin/python3"; else fail "The fetched Python does not work here."; fi
fi

echo "Using Python: $PYTHON ($("$PYTHON" --version 2>&1))"
echo ""
[ "$ONLY" = 1 ] && exit 0
"$PYTHON" install.py
STATUS=$?
echo ""
if [ $STATUS -eq 0 ]; then
    echo "Done. To start NSDDD, double-click Launch.command."
else
    echo "The installer stopped with an error (see above). You can run this file again; downloads resume."
fi
echo ""
read -r -p "Press Return to close this window. "
exit $STATUS
