#!/usr/bin/env python3
"""Run exact console walkthroughs in fresh isolated states and retain real transcripts."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts"


def main():
    OUTPUT.mkdir(exist_ok=True)
    records = []
    for name in ("walkthrough", "full-event"):
        # Fresh temporary state on every run; the default event-state.json is never touched.
        with tempfile.TemporaryDirectory(prefix="killswitch-demo-") as directory:
            path = Path(directory) / (name + ".json")
            commands = (ROOT / "examples" / (name + ".txt")).read_text(encoding="utf-8")
            argv = [sys.executable, str(ROOT / "killswitch.py"), "--state", str(path)]
            result = subprocess.run(argv, input=commands, text=True, encoding="utf-8", cwd=ROOT,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            transcript = ("ACTUAL COMMAND: " + " ".join(argv) + "\n"
                          + "STDIN SOURCE: examples/" + name + ".txt\n"
                          + "EXIT CODE: " + str(result.returncode) + "\n\n"
                          + result.stdout + result.stderr)
            (OUTPUT / (name + "-transcript.txt")).write_text(transcript, encoding="utf-8")
            if result.returncode or "Error:" in result.stdout or "Traceback" in transcript:
                raise RuntimeError(f"Demo failed: {name}; see transcript.")
            state = json.loads(path.read_text(encoding="utf-8"))
            if name == "full-event":
                assert state["teams"]["T001"]["score"] == 1200
                assert state["teams"]["T001"]["completed"][-1] == "maze"
                assert state["teams"]["T002"]["score"] == 300
                assert not state["waiting"]
            else:
                assert state["teams"]["T001"]["active"] == "quadruped"
                assert len(state["teams"]["T001"]["completed"]) == 2
            # Generated demo states are deliberately distinct from the clean starter state.
            destination = OUTPUT / (name + "-state.json")
            destination.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            records.append({"demo": name, "returncode": result.returncode,
                            "commands": "examples/" + name + ".txt",
                            "transcript": "artifacts/" + name + "-transcript.txt",
                            "state": "artifacts/" + name + "-state.json"})
            print(f"DEMO_OK {name}: {len(state['teams'])} teams; scores="
                  + str({t: data['score'] for t, data in state['teams'].items()}))
    (OUTPUT / "demo-results.json").write_text(json.dumps(records, indent=2) + "\n")


if __name__ == "__main__":
    main()
