#!/bin/sh
# Start PyTPS from source on Linux or macOS. The first start creates .venv and installs the requirements.
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv && .venv/bin/python -m pip install --upgrade pip && .venv/bin/python -m pip install -r requirements.txt || exit 1
fi
exec .venv/bin/python run_pytps.py "$@"
