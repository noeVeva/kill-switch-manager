#!/usr/bin/env python3
"""Build initial or Writer-refreshed ZIP and structured implementation handoff."""
import hashlib
import json
from pathlib import Path
import platform
import re
import sys
import zipfile

ROOT = Path(__file__).absolute().parents[1]
WORKSPACE = ROOT.parents[1]
sys.path.insert(0, str(ROOT))
from engine import read_json, validate_state
from killswitch import COMMAND_REFERENCE, MODULES


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    artifacts = ROOT / "artifacts"
    output = WORKSPACE / "writing_space"
    output.mkdir(exist_ok=True)
    tests = (artifacts / "test-output.txt").read_text()
    match = re.search(r"Ran (\d+) tests in ([0-9.]+)s\s+OK\s*$", tests)
    if not match:
        raise SystemExit("Refusing to package: missing successful test report; run sh entrypoint.sh.")
    starter = read_json(ROOT / "starter/event-state.json")
    validate_state(starter)
    assert not starter["roster"] and not starter["teams"] and not starter["waiting"]
    demos = read_json(artifacts / "demo-results.json")
    interface = {"commands": COMMAND_REFERENCE, "modules": MODULES}
    dump(artifacts / "interface-reference.json", interface)
    files = sorted(p for p in ROOT.rglob("*") if p.is_file()
                   and "__pycache__" not in p.parts and ".git" not in p.parts
                   and p.suffix not in (".pyc", ".bak")
                   and p.relative_to(ROOT).as_posix() != "event-state.json")
    archive = output / "kill-switch-manager.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        for path in files:
            handle.write(path, "kill-switch-manager/" + path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(archive) as handle:
        assert handle.testzip() is None
        members = handle.namelist()
        assert "kill-switch-manager/starter/event-state.json" in members
        assert "kill-switch-manager/event-state.json" not in members
        expanded = sum(item.file_size for item in handle.infolist())
    manifest = [{"path": str(p), "archive_path": "kill-switch-manager/" + p.relative_to(ROOT).as_posix(),
                 "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]
    handoff = {
        "status": "implemented, exercised and packaged; final presentation and documentation belong to Writer",
        "event_credit": {k: starter["catalog"][k] for k in ("event", "author", "organizers", "story")},
        "source": "/home/novix/workspace/user_data/challenge.txt",
        "artifacts": {
            "source_project": str(ROOT), "zip": str(archive),
            "technical_handoff": str(output / "kill-switch-manager-implementation.json"),
            "catalog": str(ROOT / "catalog.json"), "clean_starter": str(ROOT / "starter/event-state.json"),
            "interface_reference": str(artifacts / "interface-reference.json"),
            "test_report": str(artifacts / "test-output.txt"), "test_source": str(ROOT / "tests/test_organizer.py"),
            "walkthrough_transcript": str(artifacts / "walkthrough-transcript.txt"),
            "full_event_transcript": str(artifacts / "full-event-transcript.txt"),
            "demo_results": str(artifacts / "demo-results.json"), "package_entrypoint": str(ROOT / "entrypoint.sh"),
            "workspace_entrypoint": str(ROOT.parent / "entrypoint.sh")},
        "requirements": {"python": "3.9+", "tested_python": platform.python_version(), "dependencies": "Python standard library only", "installation_command": "None; do not pip install anything.", "network": "No network access or listeners.", "platform": "Tested Linux; atomic file replacement relies on local filesystem semantics. Terminal tab completion depends on readline availability."},
        "exact_commands": {
            "launch": "cd /home/novix/workspace/project/kill-switch-manager && python3 killswitch.py",
            "isolated_launch": "python3 /home/novix/workspace/project/kill-switch-manager/killswitch.py --state /home/novix/workspace/project/kill-switch-manager/my-event.json",
            "help": "python3 /home/novix/workspace/project/kill-switch-manager/killswitch.py --help",
            "new_custom_catalog": "python3 /home/novix/workspace/project/kill-switch-manager/killswitch.py --state /home/novix/workspace/project/kill-switch-manager/custom-event.json --catalog /home/novix/workspace/project/kill-switch-manager/catalog.json",
            "unit_integration_tests": "python3 -m unittest discover -s /home/novix/workspace/project/kill-switch-manager/tests -v",
            "safe_demos": "python3 /home/novix/workspace/project/kill-switch-manager/examples/run_demo.py",
            "reproduce_all": "sh /home/novix/workspace/project/entrypoint.sh",
            "refresh_zip_after_writer_docs": "python3 /home/novix/workspace/project/kill-switch-manager/scripts/build_package.py",
            "manual_walkthrough_new_state_only": "cd /home/novix/workspace/project/kill-switch-manager && python3 killswitch.py --state my-demo.json < examples/walkthrough.txt"},
        "startup_flags": {"--help": "Print usage and exit 0 without creating state.", "--state PATH": "Default absolute path beside script/event-state.json; create when absent, resume when present. Relative paths resolve from current working directory.", "--catalog PATH": "Only for a new state. Existing state embeds its authoritative catalog; cannot silently override it."},
        "command_reference": COMMAND_REFERENCE, "module_reference": MODULES,
        "defaults": {"formation": "random organizer shuffle", "team_size": 3, "formation_seed": 2041,
                     "assignment_mode": "random", "assignment_seed": 2041, "min_main": 3,
                     "warehouse_capacity": 2000, "other_mission_capacity": 1,
                     "points": "warehouse=100; intermediate mains=200; advanced mains=300; maze=500. All proposed defaults, not source facts.",
                     "custom_catalog_threshold": "Fresh/reset min_main=min(3, reachable enabled main count); at least one reachable main required."},
        "scheduling_semantics": [
            "Team formation and mission assignment mode are independent. Team formation defaults random; players never choose their own team. Controlled formation is an explicit organizer override with a full exact mapping.",
            "Random formation sorts IDs then seeded-shuffles and distributes round-robin into ceil(N/size) teams; sizes differ by at most 1, each at most size. Team IDs T001 onward. IDs are case-sensitive; team ID all is reserved. Duplicate player IDs rejected, duplicate display names allowed.",
            "The shared warehouse is prerequisite of every later mission. All 12 main branches require only warehouse in the supplied catalog; none has a fragile forced dependency chain. Custom acyclic prerequisites are validated.",
            "Main branches differ across simultaneously active teams when their capacity is 1. Raising a capacity explicitly permits sharing. Choices are randomized among eligible free IDs, not among occupied resources. Assignment order is stable sorted team ID; this is reproducible, not lottery-fair priority.",
            "After 3 completed MAIN branches (warehouse excluded), maze becomes eligible. Random assignment prioritizes a free maze; if maze is full it can give another eligible free main. No immediate finale out of gate. Completed maze makes team finished.",
            "Each team has at most one active mission. Completed missions cannot be reassigned or scored twice. Organizer completion is a manual assertion, not flag verification.",
            "A blocked assignment creates one waiting entry per team. Controlled explicit requests retain the requested mission; generic controlled requests after warehouse wait for organizer selection. Queue dispatch is FIFO, skipping blocked entries rather than globally blocking the queue.",
            "Completion releases capacity but never auto-assigns or auto-enqueues. Run missions/assign to assign/enqueue idle teams; run queue/dispatch to retry teams already queued. Capacity changes also require explicit dispatch.",
            "Controlled assignment cannot bypass completion, prerequisite, enable or capacity checks. Requested mission requires controlled assignment mode and a single team, not all.",
            "Switching assignment mode never mutates existing active allocations. Explicit queued mission requests are preserved and honored by dispatch even after a mode switch; generic requests follow current mode. A deliberate new missions/assign invocation can replace a team's queued request.",
            "Setting assignment seed resets draw=0; formation seed is separate. Save/resume includes draw counter. Reproducibility is verified in tested runtime; use same Python runtime for identical pseudo-random results.",
            "Disabling active missions or explicitly requested waiting missions is rejected. Capacity below active occupancy is rejected. Intro/finale cannot be disabled. Disable/threshold changes that make finale unreachable or invalidate recorded finale activity are rejected and rolled back.",
            "Disabling branches can leave some teams waiting if they already completed all remaining eligible enabled branches; organizer should re-enable an uncompleted branch or lower min_main subject to validation. No silent prerequisite/capacity bypass."
        ],
        "state_model": {
            "schema_version": 1,
            "catalog": "Embedded authoritative event metadata and mission definitions; initial seed from catalog.json. Editing source catalog.json does not change an existing event.",
            "settings": {"assignment_mode": "random|controlled", "seed": "integer 0..2^63-1", "draw": "persisted nonnegative random draw counter", "min_main": "integer 1..main count; enough reachable enabled branches required"},
            "roster": "object player_id -> printable Unicode display name; max 2000; frozen after teams formed",
            "teams": "object team_id -> {players:[IDs], completed:[chronological mission IDs], active:mission ID|null, score:int derived from completions}",
            "waiting": "ordered [{team:team ID, mission:mission ID|null}]",
            "audit": "UTC ISO time + actor=organizer + action + detail; max 20000; all successful state-machine actions, including no-op assignment attempts, are logged. Direct save/reload are not audit actions."
        },
        "persistence_and_recovery": [
            "Every successful mutation uses full validation, rollback on failure, same-directory temp file, fsync and os.replace. State JSON limited to 8 MiB. New file modes are 0600 on POSIX; parent directory permissions remain operator responsibility.",
            "Before each overwrite, exact previous valid bytes are atomically saved to <state>.bak. This is ONE generation, not versioned backup. Any subsequent successful save/mutation overwrites .bak. Exit performs no save, preserving .bak.",
            "Malformed state or catalog is rejected with Error and no traceback or silent overwrite. Reload failure retains in-memory snapshot and disk bytes. Invalid interactive commands show Error and continue; interactive exit code 0 is not proof every command succeeded. Startup validation failures exit 2; Ctrl-C exits 130 when outside a command.",
            "For recovery: stop all organizer processes; make an independent filesystem copy of current state AND .bak; inspect/validate backup by launching with --state pointing to the independent copy; only after validation replace the intended event file offline. Never use reset to recover corrupt data.",
            "reset RESET or event/reset confirm RESET clears roster, teams, scores, waiting, audit history and scheduling settings; retains embedded catalog, capacities and enable states. A reset audit entry starts a new log. Prior complete state is .bak until next write. Make a separately named backup first.",
            "teams/create with existing active/completed/waiting activity refuses unless confirm=REGENERATE. This erases all teams' activity/scores/queue and reforms teams; roster and settings remain. Without activity regeneration is allowed. Confirmation options are cleared after successful module execution.",
            "Single organizer process per state. SHA256 fingerprint detects sequential stale writers or deletion, but there is no interprocess lock; simultaneous writers can race. Not a multi-user database or network service.",
            "Raw JSON edits are unsupported during an event; invariants may reject them. Custom new-event catalogs may change goals/points/prerequisites before launch but must pass validation. No migration, undo or completion correction command is provided."
        ],
        "safety_and_omissions": [
            "14 catalog stages only: warehouse, quadruped, humanoid, drones, medical, vehicle, industrial_arm, elevator, plant, cctv, cpu_rings, blind_spot, through_walls, maze. No actual vulnerabilities, flags, labs, firmware images, pcaps, datasets, containers or infrastructure are implemented/provisioned.",
            "No exploits, scanning, real ICS/medical/RF/device actions, shell execution, network calls, Kubernetes control or attack/defense execution. Workshop choice and optional attack/defense score tracking are deliberately omitted in favor of reliable core event management.",
            "No authentication or role enforcement: organizer authority is an operational assumption, not access control. Anyone with filesystem/terminal access can alter local records. Audit is plaintext and not tamper-proof; scores are not cryptographically attested.",
            "State and backups contain names; keep private and apply event retention/consent policy. Sample roster is fictional. No encryption, server, GUI, simultaneous organizers, external integrations, timers, flag verification, score export or event hosting.",
            "Balanced formation is by participant count only, not skill balancing. Seeded pseudorandom is not cryptographic randomness. Leaderboard ties sort by team ID, not completion timestamp."
        ],
        "test_evidence": {"final_pass_count": int(match.group(1)), "final_failures": 0,
                          "last_report_elapsed_seconds": float(match.group(2)),
                          "report": str(artifacts / "test-output.txt"),
                          "coverage": ["balanced/reproducible teams", "Unicode CSV and duplicate rejection", "random/controlled assignment", "shared intro and divergent branches", "full branch capacity waiting/retry", "completion capacity release and scoring", "duplicate completion protection", "prerequisites/advanced eligibility/finale gating", "save/resume/backup/stale writer rollback", "reset/regeneration confirmations", "invalid state/catalog/console inputs", "actual subprocess console walkthroughs", "--help smoke"],
                          "honest_development_note": "Initial run was 28/29 passing: a reference-count test expected 12 modules but actual defined count is 11. Assertion corrected; final report is the rerun, not fabricated."},
        "tested_demos": demos,
        "archive_portability_verification": read_json(artifacts / "archive-verification.json") if (artifacts / "archive-verification.json").exists() else None,
        "demo_outcomes": {"walkthrough": "12 fictional players -> 4 balanced teams; shared intro then 4 distinct branches; controlled switch; T001 quadruped active and 400 points; others 100 each; save/reload successful.",
                          "full_event": "2 one-player teams; intro capacity 1 causes queue and dispatch; controlled quadruped capacity 1 causes queue and release; T001 completes warehouse+quadruped+humanoid+drones+maze = 1200 points, T002 warehouse+quadruped = 300; no waiting entries remain."},
        "writer_instructions": [
            "Main challenge presentation PDF must stay separate and contain NO CLI/tool discussion. Preserve Kill Switch CTF, Wassim Oukoudda, StyxSec × Oblivion and 2041 ORACLE framing.",
            "Use catalog.json as safe challenge-presentation source; split elevator tower from virtual plant; negative rings are narrative shorthand; Blind Spot is intermittent docking, not permanently air-gapped; Through the Walls uses synthetic CSI/RSSI.",
            "Write separate organizer documentation from this exact command/module reference and actual transcripts, not imagined commands. Explicitly distinguish organizer team formation from random/controlled mission assignment, queue dispatch versus assign, and destructive reset/regenerate behavior.",
            "Include quickstart, exact defaults/types/enums, end-to-end workflows, capacity/wait/finale behavior, state recovery/privacy and omissions. Mention points/difficulty/capacities are proposed defaults. No user-facing claims of implemented exploit labs.",
            "Add final docs to /home/novix/workspace/project/kill-switch-manager/docs/ (e.g. organizer-guide.pdf and editable source). Preserve README as minimal launcher. Do not overwrite code, test evidence or clean starter with demo activity.",
            "After adding docs run python3 /home/novix/workspace/project/kill-switch-manager/scripts/build_package.py. It refreshes the ZIP including all package/docs files and updates this handoff/checksums. It excludes pycache, .git, .pyc, .bak and root event-state.json. Do not place personal real event states elsewhere in package before packaging.",
            "The main challenge PDF can be delivered separately; optionally put a copy under docs/ only if desired, but never mix tool content into it. Coordinator owns final frontend delivery."
        ],
        "archive": {"bytes": archive.stat().st_size, "expanded_member_bytes": expanded, "member_count": len(members),
                    "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "crc_test": "passed"},
        "file_manifest": manifest,
        "version_control": "Workspace project was not a Git repository (git status returned fatal). No commits made: no user commit request. Source and hashes provided instead."
    }
    dump(output / "kill-switch-manager-implementation.json", handoff)
    print(f"PACKAGE_OK {archive} bytes={archive.stat().st_size} members={len(members)} CRC=passed")
    print(f"HANDOFF_OK {output / 'kill-switch-manager-implementation.json'} tests={match.group(1)}")


if __name__ == "__main__":
    main()
