#!/usr/bin/env bash
# refresh.sh — Re-fetch all KB docs from GitHub raw markdown.
# Usage: bash engine/kb/refresh.sh  (from ~/rocket-support/)
#        or:  engine/kb/refresh.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE_DIR="$(dirname "$SCRIPT_DIR")"
VENV="$ENGINE_DIR/.venv"

echo "── Rocket.new KB Refresh ──"
echo "Engine: $ENGINE_DIR"

# Activate venv if present
if [ -f "$VENV/bin/python" ]; then
    PYTHON="$VENV/bin/python"
    echo "Python: $PYTHON"
else
    PYTHON="python3"
    echo "Python: $PYTHON (system)"
fi

"$PYTHON" "$SCRIPT_DIR/kb_builder.py"
