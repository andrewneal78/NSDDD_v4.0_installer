#!/bin/bash
cd "$(dirname "$0")" || exit 1
# Same interpreter choice as Launch.command (never the system python3, which may be only a stub on a Mac).
PYTHON=""
for reader in ".venv/bin/python3" ".nsddd_python/bin/python3"; do
    if [ -x "$reader" ] && [ -f "install_config.json" ]; then
        PYTHON=$("$reader" -c "import json; print(json.load(open('install_config.json')).get('python',''))" 2>/dev/null)
        break
    fi
done
if [ -z "$PYTHON" ] || [ ! -x "$PYTHON" ]; then
    if [ -x ".venv/bin/python3" ]; then PYTHON=".venv/bin/python3"; else PYTHON="python3"; fi
fi
echo "Checking for a new version of NSDDD (needs the internet)..."
"$PYTHON" launch.py --update-only
echo
read -n 1 -s -r -p "Press any key to close."
