#!/bin/bash
cd "$(dirname "$0")" || exit 1
PYTHON=python3
for p in .venv/bin/python3 .nsddd_python/bin/python3; do [ -x "$p" ] && PYTHON=$p && break; done
echo "Checking for a new version of NSDDD (needs the internet)..."
# launch.py line must end at byte 349 (updates overwrite this file while it runs)
##########
"$PYTHON" launch.py --update-only
echo
read -n 1 -s -r -p "Press any key to close."
