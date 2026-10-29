#!/bin/bash
cd "$(dirname "$0")" || exit 1


# Resolve Python: the one recorded in install_config.json, then the local .venv, then python3 on the PATH.
# install_config.json is read with the installer's own environment, never the system python3: on a Mac without
# Apple's developer tools /usr/bin/python3 is only a stub that asks to install them.
PYTHON=""
for reader in ".venv/bin/python3" ".nsddd_python/bin/python3"; do
    if [ -x "$reader" ] && [ -f "install_config.json" ]; then
        PYTHON=$("$reader" -c "import json; print(json.load(open('install_config.json')).get('python',''))" 2>/dev/null)
        break
    fi
done
if [ -z "$PYTHON" ] || [ ! -x "$PYTHON" ]; then
    if [ -x ".venv/bin/python3" ]; then
        PYTHON=".venv/bin/python3"
    else
        PYTHON="python3"
    fi
fi

echo "================================================"
echo "  NSDDD v4.0 Search Interface"
echo "  Checking for updates, then launching..."
echo "  Note: browser may show 'server not found' briefly."
echo "  Please wait a few seconds."
echo "================================================"
echo ""

# launch.py handles update checks and starts/stops Voilà
"$PYTHON" launch.py
