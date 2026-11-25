# Kill Switch CTF — organizer

Requires Python 3.9+ (tested with Python 3.11.15). Standard library only; no installation or pip command is needed.

From this folder:

```sh
python3 killswitch.py
```

Or choose an isolated event state:

```sh
python3 killswitch.py --state my-event.json
```

Start with `show modules`, `use roster/import`, `set path examples/roster.csv`, `run`. Then `use teams/create`, `show options`, `run`, `use missions/assign`, `run`. Type `help` for the exact command list. Quote multiword names and paths. This is organizer-only local management, not a lab or exploit tool. All challenge catalog entries refer to fictional isolated simulations/offline artifacts.

Tests and safe demo walkthroughs (never modify your event state):

```sh
sh entrypoint.sh
```

Read the complete [organizer user guide (PDF)](docs/USER_GUIDE.pdf) or its [editable Markdown source](docs/USER_GUIDE.md). It includes the tested quickstart, all 11 module references, scheduling, safe backup/recovery and security limits. The challenge/event presentation is a separate document and contains no organizer operations.

Test output and real demo transcripts are under `artifacts/`; editable console inputs are under `examples/`. `starter/event-state.json` is an empty starter, while `artifacts/*-state.json` are clearly labeled generated demo states. Do not use demo states as a fresh event.
