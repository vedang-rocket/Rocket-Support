#!/usr/bin/env bash
# Rebuild both indexes together whenever brain.db changes:
# migrate_embeddings.py refreshes the semantic vector index, and
# BrainFTS().rebuild_from_db() refreshes the Tantivy FTS index.
# Running only one step leaves indexes out of sync.

set -u

if ! "engine/.venv/bin/python" "engine/migrate_embeddings.py"; then
  echo "Failed: migrate_embeddings.py"
  exit 1
fi

if ! "engine/.venv/bin/python" -c "import sys; sys.path.insert(0, 'engine'); from brain_fts import BrainFTS; count = BrainFTS().rebuild_from_db(); print(f'FTS index rebuilt: {count} docs')"; then
  echo "Failed: BrainFTS rebuild_from_db"
  exit 1
fi

echo "All indexes rebuilt."
