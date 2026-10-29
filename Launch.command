#!/bin/bash
cd "$(dirname "$0")" || exit 1
# Python: the one in install_config.json, read with the installer's own Python (the system python3 may be
# only a stub on a Mac without the developer tools), then .venv, then python3 on the PATH.
PYTHON=""
for r in .venv/bin/python3 .nsddd_python/bin/python3; do
    [ -x "$r" ] && [ -f install_config.json ] && PYTHON=$("$r" -c "import json; print(json.load(open('install_config.json')).get('python',''))" 2>/dev/null) && break
done
if [ -z "$PYTHON" ] || [ ! -x "$PYTHON" ]; then
    if [ -x .venv/bin/python3 ]; then PYTHON=.venv/bin/python3; else PYTHON=python3; fi
fi
echo "NSDDD v4.0: checking for updates, then launching. The browser may show 'server not found' briefly."
# Updates overwrite this file while bash runs it, so the launch.py line must end at byte 913 in every version.
##########################################################
"$PYTHON" launch.py
