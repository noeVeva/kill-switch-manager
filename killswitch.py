#!/usr/bin/env python3
"""Kill Switch CTF organizer console. Start with python3 killswitch.py."""
from __future__ import annotations

import argparse
import cmd
import csv
import json
from pathlib import Path
import shlex
import sys

from engine import Event, OrganizerError, Store, require

# This declarative registry is also the machine-readable documentation source.
MODULES = {
    "roster/add": {"description": "Organizer adds one player (unique case-sensitive ID).", "options": {
        "id": {"default": "", "type": "string", "required": True, "description": "ASCII ID, 1–40 letters/digits/_/-; first character alphanumeric."},
        "name": {"default": "", "type": "string", "required": True, "description": "Printable Unicode name up to 160 characters; quote multiword names."}}},
    "roster/import": {"description": "Atomically import UTF-8 CSV with exact id,name header; organizer only.", "options": {
        "path": {"default": "", "type": "path", "required": True, "description": "CSV path; up to 1 MiB and 2000 total players."}}},
    "teams/create": {"description": "Organizer forms random balanced teams or explicit controlled mapping. Formation is separate from mission assignment mode.", "options": {
        "size": {"default": 3, "type": "int", "required": False, "min": 1, "max": 2000, "description": "Random formation maximum team size; ceil(players/size) balanced teams. Ignored for controlled mapping."},
        "seed": {"default": 2041, "type": "int", "required": False, "min": 0, "max": 9223372036854775807, "description": "Random team formation seed; independent of event assignment seed."},
        "formation": {"default": "random", "type": "enum", "required": False, "allowed": ["random", "controlled"], "description": "Random is normal rule; controlled is explicit organizer override, never player self-selection."},
        "mapping": {"default": "", "type": "string", "required": False, "description": "Controlled only: T001=P01,P02;T002=P03,P04. All players exactly once. Quote whole value."},
        "confirm": {"default": "", "type": "enum", "required": False, "allowed": ["", "REGENERATE"], "description": "REGENERATE required if activity exists; deletes ALL teams' scores, completions, active assignments and queue. Roster/settings retained."}}},
    "missions/assign": {"description": "Assign common warehouse first, then eligible free branches; random branches differ while occupied at capacity 1. Enqueue if blocked.", "options": {
        "team": {"default": "all", "type": "string", "required": False, "description": "Team ID or all; stable sorted team order."},
        "mission": {"default": "", "type": "string", "required": False, "description": "Empty for automatic choice; explicit mission ID only in controlled mode for one team. Cannot bypass prerequisites/capacity."}}},
    "progress/complete": {"description": "Organizer verifies and records current mission completion, releases capacity and awards proposed default points.", "options": {
        "team": {"default": "", "type": "string", "required": True, "description": "One team ID."},
        "mission": {"default": "", "type": "string", "required": False, "description": "Optional guard: must equal team's active mission. Empty uses active mission."}}},
    "queue/dispatch": {"description": "Retry waiting teams in FIFO order; skip blocked requests. Does not auto-enqueue idle teams.", "options": {}},
    "event/config": {"description": "Change one scheduling setting; existing active allocations remain intact.", "options": {
        "option": {"default": "assignment_mode", "type": "enum", "required": False, "allowed": ["assignment_mode", "seed", "min_main"], "description": "Scheduling option to change."},
        "value": {"default": "random", "type": "string", "required": True, "description": "assignment_mode: random|controlled; seed: integer 0..2^63-1 (resets draw); min_main: 1..enabled reachable main mission count (default 3). Changing threshold may be rejected if existing finale activity would become premature."}}},
    "resources/config": {"description": "Configure capacity or enable state without invalidating active or explicitly queued allocations.", "options": {
        "mission": {"default": "", "type": "string", "required": True, "description": "Mission ID."},
        "capacity": {"default": "", "type": "optional-int", "required": False, "min": 1, "max": 2000, "description": "Empty means unchanged; cannot be below active count."},
        "enabled": {"default": "", "type": "enum", "required": False, "allowed": ["", "true", "false"], "description": "Empty unchanged; intro/finale cannot be disabled; reject disabling active/explicitly queued mission or making finale unreachable."}}},
    "event/status": {"description": "Show roster/team progression, scores and waiting teams.", "options": {}},
    "event/leaderboard": {"description": "Show descending total points, team ID breaks ties (not speed).", "options": {}},
    "event/reset": {"description": "Erase event activity/roster/settings; retain current catalog/resource defaults. Previous state goes to .bak until next write.", "options": {
        "confirm": {"default": "", "type": "enum", "required": True, "allowed": ["", "RESET"], "description": "Exact RESET confirmation required."}}},
}

COMMAND_REFERENCE = {
    "help [command]": "Built-in cmd help and command list. help run explains module workflow.",
    "show [modules|challenges|options|roster|teams|queue|settings]": "Default modules; teams equals status. Challenges list IDs, proposed points, occupancy, enable state and prerequisites.",
    "modules": "Alias for show modules.",
    "challenges": "Alias for show challenges.",
    "use <module>": "Select a module; initializes its option defaults. Selecting again resets options.",
    "set <option> <value>": "Set current module option; quote multiword values or paths. Use empty quotes to clear an optional string. Types/ranges/enums checked immediately.",
    "run": "Validate required options, execute selected module and auto-save successful mutations. Empty/extra arguments rejected. A printed Error leaves state unchanged.",
    "back": "Leave module context and clear its options.",
    "status": "Show event status (same as event/status).",
    "leaderboard": "Show scores (same as event/leaderboard).",
    "eligible <team>": "Show eligible missions and occupancy; eligibility excludes already-active/finished teams, availability additionally depends on capacity.",
    "audit [count]": "Show last count audit entries (default 20; 1..20000).",
    "save": "Explicit atomic save; all successful mutations already auto-save. Updates one-generation .bak.",
    "reload": "Validate and reload disk state. On failure retain current in-memory state and leave disk untouched.",
    "reset RESET": "Explicit destructive reset; same as event/reset confirm RESET. Catalog/resources retained, settings reset to random/2041/min_main=min(3, reachable enabled mains).",
    "exit | quit | EOF": "Leave console. State already auto-saved. No extra exit write, so .bak survives exit.",
    "empty line": "No-op (does not repeat last mutation).",
}


def convert(value, spec):
    kind = spec["type"]
    if kind == "int" or kind == "optional-int" and value != "":
        try:
            value = int(value)
        except (ValueError, TypeError):
            raise OrganizerError("Expected an integer.") from None
        require(spec["min"] <= value <= spec["max"], f"Value must be {spec['min']}..{spec['max']}.")
    if "allowed" in spec:
        require(value in spec["allowed"], f"Allowed values: {spec['allowed']}")
    return value


class Console(cmd.Cmd):
    intro = ("\nKill Switch CTF | by Wassim Oukoudda | StyxSec × Oblivion\n"
             "2041 / ORACLE — LOCAL ORGANIZER ONLY; no labs or offensive actions.\n"
             "Try: show modules, use roster/import, show options, help run.\n"
             "One organizer process per state file. Changes auto-save.\n")

    def __init__(self, event, **kwargs):
        super().__init__(**kwargs)
        self.event = event
        self.module = None
        self.options = {}
        self.prompt = "killswitch > "

    def out(self, value):
        self.stdout.write(str(value) + "\n")

    def onecmd(self, line):
        try:
            return super().onecmd(line)
        except (OrganizerError, OSError, UnicodeError, ValueError, csv.Error) as exc:
            self.out(f"Error: {exc}")
            return False
        except KeyboardInterrupt:
            self.out("Interrupted. Use exit to leave; committed changes are saved.")
            return False

    def emptyline(self):
        pass

    def default(self, line):
        self.out("Error: unknown command. Type help or show modules. Shell commands are not supported.")

    def do_help(self, arg):
        """help [command]: show command help; use show options for module options."""
        if not arg.strip():
            self.out("\n".join(f"{name} — {desc}" for name, desc in COMMAND_REFERENCE.items()))
        else:
            super().do_help(arg)

    def do_show(self, arg):
        """show modules|challenges|options|roster|teams|queue|settings"""
        args = shlex.split(arg)
        require(len(args) <= 1, "Usage: show [modules|challenges|options|roster|teams|queue|settings]")
        topic = args[0] if args else "modules"
        if topic == "modules":
            self.out("\n".join(f"{name} — {spec['description']}" for name, spec in MODULES.items()))
        elif topic == "options":
            require(self.module, "Select a module first: use <module>")
            self.out(MODULES[self.module]["description"])
            for name, spec in MODULES[self.module]["options"].items():
                self.out(f"{name} = {self.options[name]!r} [{spec['type']}; required={spec['required']}] — {spec['description']}")
            if not self.options:
                self.out("No options; run directly.")
        elif topic == "challenges":
            self.out("Proposed points/capacities; fictional isolated simulations/offline artifacts only.")
            for mid, m in self.event.missions.items():
                self.out(f"{mid} | {m['title']} | {m['kind']} | {m['points']} pts | {self.event.occupied(mid)}/{m['capacity']} active | enabled={m['enabled']} | requires={','.join(m['prerequisites']) or '-'}")
        elif topic in ("teams", "roster", "queue", "settings"):
            if topic == "teams":
                self.out(self.event.status())
            else:
                key = {"queue": "waiting"}.get(topic, topic)
                self.out(json.dumps(self.event.s[key], ensure_ascii=False, indent=2))
        else:
            raise OrganizerError("Unknown show topic. Type help show.")

    def do_modules(self, arg):
        """modules: list organizer modules."""
        require(not arg.strip(), "Usage: modules")
        self.do_show("modules")

    def do_challenges(self, arg):
        """challenges: list mission catalog and resource occupancy."""
        require(not arg.strip(), "Usage: challenges")
        self.do_show("challenges")

    def do_use(self, arg):
        """use <module>: select organizer module and initialize options."""
        args = shlex.split(arg)
        require(len(args) == 1 and args[0] in MODULES, "Unknown module. Use show modules.")
        self.module = args[0]
        self.options = {name: spec["default"] for name, spec in MODULES[self.module]["options"].items()}
        self.prompt = f"killswitch ({self.module}) > "
        self.out(f"Using {self.module}. Type show options, set <option> <value>, then run.")

    def do_set(self, arg):
        """set <option> <value>: set a current-module option (quote multiword values)."""
        require(self.module, "Select a module first.")
        args = shlex.split(arg)
        require(len(args) == 2, 'Usage: set <option> <value>; quote multiword text; use "" to clear.')
        name, value = args
        specs = MODULES[self.module]["options"]
        require(name in specs, f"Unknown option: {name}")
        self.options[name] = convert(value, specs[name])
        self.out(f"{name} => {self.options[name]}")

    def do_run(self, arg):
        """run: execute selected module. Mutations validate, atomically auto-save and audit.\n\nExample: use roster/import; set path examples/roster.csv; run\nThen: use teams/create; show options; run; use missions/assign; run\nNo network, exploits or external programs are executed."""
        require(not arg.strip(), "Usage: run")
        require(self.module, "Select a module first.")
        for name, spec in MODULES[self.module]["options"].items():
            require(not spec["required"] or self.options[name] != "", f"Required option missing: {name}")
        o, e, m = self.options, self.event, self.module
        if m == "roster/add":
            e.add_players([(o["id"], o["name"])])
            result = "Player added and saved."
        elif m == "roster/import":
            e.import_roster(o["path"])
            result = f"Roster imported and saved; {len(e.s['roster'])} players total."
        elif m == "teams/create":
            result = e.form_teams(**o)
        elif m == "missions/assign":
            result = e.assign(o["team"], o["mission"])
        elif m == "progress/complete":
            result = e.complete(o["team"], o["mission"])
        elif m == "queue/dispatch":
            result = e.dispatch()
        elif m == "event/config":
            value = o["value"]
            if o["option"] != "assignment_mode":
                try:
                    value = int(value)
                except ValueError:
                    raise OrganizerError("Setting value must be an integer.") from None
            result = e.configure(o["option"], value)
        elif m == "resources/config":
            require(o["capacity"] != "" or o["enabled"] != "", "Set capacity and/or enabled.")
            enabled = None if o["enabled"] == "" else o["enabled"] == "true"
            result = e.resource(o["mission"], None if o["capacity"] == "" else o["capacity"], enabled)
        elif m == "event/status":
            result = e.status()
        elif m == "event/leaderboard":
            result = e.leaderboard()
        elif m == "event/reset":
            result = e.reset(o["confirm"])
        else:
            raise OrganizerError("Module is not implemented.")
        self.out(result)
        # Destructive confirmations are one-shot to reduce accidental repeat runs.
        if "confirm" in o:
            o["confirm"] = ""

    def do_back(self, arg):
        """back: clear current module context."""
        require(not arg.strip(), "Usage: back")
        self.module, self.options, self.prompt = None, {}, "killswitch > "

    def do_status(self, arg):
        """status: show all teams, progress, scores and queue."""
        require(not arg.strip(), "Usage: status")
        self.out(self.event.status())

    def do_leaderboard(self, arg):
        """leaderboard: sort total proposed points descending, then team ID."""
        require(not arg.strip(), "Usage: leaderboard")
        self.out(self.event.leaderboard())

    def do_eligible(self, arg):
        """eligible <team>: show prerequisite-eligible missions, including full resources."""
        args = shlex.split(arg)
        require(len(args) == 1, "Usage: eligible <team>")
        eligible = self.event.eligible(args[0])
        self.out("\n".join(f"{mid}: {self.event.occupied(mid)}/{self.event.missions[mid]['capacity']} active" for mid in eligible) or "No eligible missions (team active/finished, or prerequisites/enable status block progress).")

    def do_audit(self, arg):
        """audit [count]: last audit records, default 20; maximum 20000."""
        args = shlex.split(arg)
        require(len(args) <= 1, "Usage: audit [count]")
        try:
            count = int(args[0]) if args else 20
        except ValueError:
            raise OrganizerError("Audit count must be an integer.") from None
        require(1 <= count <= 20000, "Audit count must be 1..20000.")
        self.out(json.dumps(self.event.s["audit"][-count:], indent=2, ensure_ascii=False))

    def do_save(self, arg):
        """save: explicitly save; overwrites single-generation .bak with previous state."""
        require(not arg.strip(), "Usage: save")
        self.event.store.save()
        self.out("State saved atomically; previous state in .bak.")

    def do_reload(self, arg):
        """reload: validate disk state and reload; failure preserves in-memory state."""
        require(not arg.strip(), "Usage: reload")
        self.event.store.reload()
        self.out("State reloaded and validated.")

    def do_reset(self, arg):
        """reset RESET: destructive reset; make a separate backup first."""
        self.out(self.event.reset(arg.strip()))

    def do_exit(self, arg):
        """exit: leave console; successful mutations are already saved."""
        require(not arg.strip(), "Usage: exit")
        self.out("Goodbye. Committed changes are saved.")
        return True

    do_quit = do_exit

    def do_EOF(self, arg):
        """EOF: exit console."""
        self.out("")
        return self.do_exit("")

    def complete_use(self, text, line, begidx, endidx):
        return [m for m in MODULES if m.startswith(text)]

    def complete_show(self, text, line, begidx, endidx):
        return [v for v in ("modules", "challenges", "options", "roster", "teams", "queue", "settings") if v.startswith(text)]

    def complete_set(self, text, line, begidx, endidx):
        if not self.module:
            return []
        words = line[:begidx].split()
        if len(words) <= 1:
            return [k for k in self.options if k.startswith(text)]
        key = words[1]
        spec = MODULES[self.module]["options"].get(key, {})
        candidates = spec.get("allowed", [])
        if key == "team":
            candidates = ["all", *self.event.s["teams"]]
        elif key == "mission":
            candidates = list(self.event.missions)
        return [str(v) for v in candidates if str(v).startswith(text)]

    def complete_eligible(self, text, line, begidx, endidx):
        return [t for t in self.event.s["teams"] if t.startswith(text)]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Kill Switch CTF — local organizer console; no lab execution. Python 3.9+; stdlib only.")
    parser.add_argument("--state", default=str(Path(__file__).with_name("event-state.json")), help="Local JSON state path; created if absent. Default: beside killswitch.py/event-state.json")
    parser.add_argument("--catalog", help="Validated catalog JSON for a NEW state only; otherwise catalog.json beside script.")
    args = parser.parse_args(argv)
    try:
        store = Store(args.state, args.catalog)
        console = Console(Event(store))
        console.out(f"State: {store.path}")
        console.cmdloop()
        return 0
    except (OrganizerError, OSError, UnicodeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nInterrupted. Committed changes are saved.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
