#!/bin/bash
cd "$(dirname "$0")"
if [ -f "install_config.json" ]; then
    PYTHON=$(python3 -c "import json; print(json.load(open('install_config.json')).get('python',''))" 2>/dev/null)
fi
[ -z "$PYTHON" ] || [ ! -f "$PYTHON" ] && PYTHON="python3"
echo "Checking for a new version of NSDDD (needs the internet)..."
"$PYTHON" launch.py --update-only
echo
read -n 1 -s -r -p "Press any key to close."
