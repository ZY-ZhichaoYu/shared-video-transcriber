#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
export PYTHONUTF8=1
if command -v python3 >/dev/null 2>&1; then
    exec python3 bootstrap.py "$@"
elif command -v python >/dev/null 2>&1; then
    exec python bootstrap.py "$@"
else
    echo "Install 64-bit Python 3.12 from https://www.python.org/downloads/ and run again."
    exit 1
fi
