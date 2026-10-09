#!/bin/bash
# NSDDD 4.0 installer for Mac: double-click this file. It needs no Python of its own.
#
# 1. Looks for Python 3.11 or 3.12 on this Mac.
# 2. If there is none, it downloads 'uv' (a small, widely used Python manager from Astral, checked against its published
#    checksum) and uses it to fetch a private Python 3.12 into the hidden folder .nsddd_python next to this file.
#    Nothing is installed system-wide.
# 3. Runs install.py with that Python (downloads the search index and models, about 2.5 GB, then checks everything).
#
# Options (for testing): --python-only  stop after finding or fetching Python and print where it is.
#                        NSDDD_FETCH_PYTHON=1  ignore any Python already on this Mac and fetch the private one.
cd "$(dirname "$0")" || exit 1
ONLY=0; [ "$1" = "--python-only" ] && ONLY=1

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
        arm64)  TRIPLE="aarch64-apple-darwin" ;;
        x86_64) TRIPLE="x86_64-apple-darwin" ;;
        *) echo "Unsupported processor: $(uname -m)"; exit 1 ;;
    esac
    BASE="https://github.com/astral-sh/uv/releases/latest/download"
    TMP="$(mktemp -d)"
    if ! curl -fsSL "$BASE/uv-$TRIPLE.tar.gz" -o "$TMP/uv.tar.gz" || ! curl -fsSL "$BASE/uv-$TRIPLE.tar.gz.sha256" -o "$TMP/uv.sha256"; then
        echo "Could not download the Python manager. Check your internet connection, or install Python 3.12 from https://www.python.org/downloads/ and run this again."
        exit 1
    fi
    WANT="$(awk '{print $1}' "$TMP/uv.sha256")"
    GOT="$(shasum -a 256 "$TMP/uv.tar.gz" | awk '{print $1}')"
    if [ -z "$WANT" ] || [ "$WANT" != "$GOT" ]; then
        echo "The download did not match its published checksum, so it was not used. Please try again."
        exit 1
    fi
    tar -xzf "$TMP/uv.tar.gz" -C "$TMP" || exit 1
    UV="$(find "$TMP" -name uv -type f | head -1)"
    export UV_PYTHON_INSTALL_DIR="$PWD/.nsddd_python/store"
    export UV_PYTHON_BIN_DIR="$PWD/.nsddd_python/uvbin"        # keep uv's shortcut links inside this folder too
    "$UV" python install 3.12 || { echo "Python could not be fetched."; exit 1; }
    FOUND="$("$UV" python find 3.12)"
    mkdir -p .nsddd_python/bin && ln -sf "../store/${FOUND#*/.nsddd_python/store/}" .nsddd_python/bin/python3     # relative, so the folder can be moved before install
    rm -rf "$TMP"
    if ok_python .nsddd_python/bin/python3; then PYTHON="$PWD/.nsddd_python/bin/python3"; else echo "The fetched Python does not work here."; exit 1; fi
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
