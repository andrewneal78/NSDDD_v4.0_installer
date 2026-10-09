#!/bin/bash
cd "$(dirname "$0")"


# Resolve Python: prefer install_config.json, then local .venv, then system python3
if [ -f "install_config.json" ]; then
    PYTHON=$(python3 -c "import json; print(json.load(open('install_config.json')).get('python',''))" 2>/dev/null)
fi
if [ -z "$PYTHON" ] || [ ! -f "$PYTHON" ]; then
    if [ -f ".venv/bin/python3" ]; then
        PYTHON=".venv/bin/python3"
    elif [ -f "$HOME/.venv/bin/python3" ]; then
        PYTHON="$HOME/.venv/bin/python3"
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
