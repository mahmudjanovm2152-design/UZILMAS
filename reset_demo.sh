#!/usr/bin/env bash
# Demo oldidan bazani toza holatga qaytarish
cd "$(dirname "$0")/backend" && source .venv/bin/activate 2>/dev/null; python -m app.seed
