#!/bin/sh
# Self-contained verification and safe example reproduction. No package installs required.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"
mkdir -p artifacts
python3 --version
python3 killswitch.py --help > artifacts/help-output.txt
if python3 -m unittest discover -s tests -v > artifacts/test-output.txt 2>&1; then
    python3 -c "from pathlib import Path; print(Path('artifacts/test-output.txt').read_text())"
else
    python3 -c "from pathlib import Path; print(Path('artifacts/test-output.txt').read_text())"
    exit 1
fi
python3 examples/run_demo.py > artifacts/demo-output.txt 2>&1
python3 -c "from pathlib import Path; print(Path('artifacts/demo-output.txt').read_text())"
python3 -c "from engine import read_json, validate_state; from pathlib import Path; s=read_json(Path('starter/event-state.json')); validate_state(s); assert not s['roster'] and not s['teams'] and not s['waiting']; print('STARTER_OK empty validated event; existing user states untouched')"
printf 'Verified. Start your event with: python3 killswitch.py --state my-event.json\n'
