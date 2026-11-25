"""Local organizer state machine. Stdlib only; no challenge execution or networking."""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import random
import re
import tempfile
from datetime import datetime, timezone

MAX_JSON = 8 * 1024 * 1024
MAX_CSV = 1024 * 1024
MAX_PLAYERS = 2000
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")


class OrganizerError(Exception):
    """Expected user, configuration or persistence error."""


def require(condition, message):
    if not condition:
        raise OrganizerError(message)


def integer(value, low, high, label):
    require(type(value) is int and low <= value <= high,
            f"{label} must be an integer from {low} to {high}.")


def text(value, label, limit=160):
    require(isinstance(value, str) and bool(value.strip()) and len(value) <= limit
            and not any(ord(c) < 32 or 127 <= ord(c) < 160 for c in value),
            f"{label} must be nonempty printable text (up to {limit} characters).")


def identifier(value, label="ID"):
    require(isinstance(value, str) and ID.fullmatch(value),
            f"{label} must use 1–40 ASCII letters, digits, underscores or hyphens.")


def exact(obj, keys, label):
    require(isinstance(obj, dict) and set(obj) == set(keys), f"Invalid {label} fields.")


def read_json(path):
    try:
        p = Path(path)
        require(p.stat().st_size <= MAX_JSON, f"JSON file exceeds {MAX_JSON} bytes.")
        with p.open("rb") as handle:
            raw = handle.read(MAX_JSON + 1)
        require(len(raw) <= MAX_JSON, f"JSON file exceeds {MAX_JSON} bytes.")
        def pairs(items):
            result = {}
            for key, value in items:
                require(key not in result, f"Duplicate JSON key: {key}")
                result[key] = value
            return result
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
    except (OSError, ValueError, RecursionError) as exc:
        raise OrganizerError(f"Cannot read JSON {path}: {exc}") from None


def validate_catalog(catalog):
    exact(catalog, ["schema_version", "event", "author", "organizers", "story", "scope", "missions"], "catalog")
    require(type(catalog["schema_version"]) is int and catalog["schema_version"] == 1, "Unsupported catalog version.")
    for key in ("event", "author", "organizers", "story", "scope"):
        text(catalog[key], key, 2000)
    missions = catalog["missions"]
    require(isinstance(missions, list) and 3 <= len(missions) <= 100, "Catalog needs 3–100 missions.")
    index = {}
    for mission in missions:
        require(isinstance(mission, dict), "Invalid mission record.")
        required = {"id", "title", "kind", "goal", "skills", "difficulty", "points", "capacity", "prerequisites", "enabled"}
        require(required <= set(mission) <= required | {"note"}, "Invalid mission fields.")
        identifier(mission["id"], "Mission ID")
        require(mission["id"] not in index, "Duplicate mission ID.")
        for key in ("title", "goal", "difficulty"):
            text(mission[key], key, 2000)
        if "note" in mission:
            text(mission["note"], "note", 2000)
        require(mission["kind"] in ("intro", "main", "finale"), "Invalid mission kind.")
        require(isinstance(mission["skills"], list) and 1 <= len(mission["skills"]) <= 20, "Invalid skill tags.")
        for skill in mission["skills"]:
            text(skill, "skill", 100)
        integer(mission["points"], 0, 100000, "Points")
        integer(mission["capacity"], 1, 2000, "Capacity")
        require(type(mission["enabled"]) is bool, "Enabled must be a boolean.")
        deps = mission["prerequisites"]
        require(isinstance(deps, list) and all(isinstance(x, str) for x in deps)
                and len(set(deps)) == len(deps), "Invalid prerequisites.")
        index[mission["id"]] = mission
    require("warehouse" in index and index["warehouse"]["kind"] == "intro", "Warehouse must be the intro.")
    require("maze" in index and index["maze"]["kind"] == "finale", "Maze must be the finale.")
    require(sum(m["kind"] == "intro" for m in missions) == 1
            and sum(m["kind"] == "finale" for m in missions) == 1, "Exactly one intro and finale required.")
    require(not index["warehouse"]["prerequisites"], "Intro cannot have prerequisites.")
    for mission in missions:
        require(all(d in index and d != mission["id"] for d in mission["prerequisites"]), "Unknown/self prerequisite.")
        if mission["kind"] != "intro":
            require("warehouse" in mission["prerequisites"], "Every later mission must require warehouse.")
        require("maze" not in mission["prerequisites"], "Finale cannot be a prerequisite.")
    visiting, visited = set(), set()
    def visit(mid):
        require(mid not in visiting, "Cyclic mission prerequisites.")
        if mid in visited:
            return
        visiting.add(mid)
        for dep in index[mid]["prerequisites"]:
            visit(dep)
        visiting.remove(mid)
        visited.add(mid)
    for mid in index:
        visit(mid)
    require(index["warehouse"]["enabled"] and index["maze"]["enabled"], "Intro and finale must remain enabled.")
    return index


def reachable_mains(missions):
    reachable = set()
    while True:
        added = {mid for mid, mission in missions.items() if mission["enabled"]
                 and mission["kind"] != "finale"
                 and set(mission["prerequisites"]) <= reachable} - reachable
        if not added:
            return {mid for mid in reachable if missions[mid]["kind"] == "main"}
        reachable.update(added)


def fresh(catalog):
    missions = validate_catalog(catalog)
    reachable = reachable_mains(missions)
    require(reachable, "Catalog needs at least one reachable enabled main mission.")
    return {"schema_version": 1, "catalog": copy.deepcopy(catalog),
            "settings": {"assignment_mode": "random", "seed": 2041, "draw": 0, "min_main": min(3, len(reachable))},
            "roster": {}, "teams": {}, "waiting": [], "audit": []}


def validate_state(state):
    exact(state, ["schema_version", "catalog", "settings", "roster", "teams", "waiting", "audit"], "state")
    require(type(state["schema_version"]) is int and state["schema_version"] == 1, "Unsupported state version.")
    missions = validate_catalog(state["catalog"])
    settings = state["settings"]
    exact(settings, ["assignment_mode", "seed", "draw", "min_main"], "settings")
    require(settings["assignment_mode"] in ("random", "controlled"), "Invalid assignment mode.")
    integer(settings["seed"], 0, 2**63-1, "Seed")
    integer(settings["draw"], 0, 2**63-1, "Draw")
    main_count = sum(m["kind"] == "main" for m in missions.values())
    integer(settings["min_main"], 1, main_count, "Minimum main missions")
    reachable = reachable_mains(missions)
    require(len(reachable) >= settings["min_main"], "Not enough reachable enabled main missions for finale threshold; enable missions or lower min_main first.")
    require(set(missions["maze"]["prerequisites"]) <= reachable | {"warehouse"}, "Finale prerequisites are not reachable while enabled.")
    roster, teams = state["roster"], state["teams"]
    require(isinstance(roster, dict) and len(roster) <= MAX_PLAYERS, "Invalid/oversized roster.")
    for pid, name in roster.items():
        identifier(pid, "Player ID")
        text(name, "Player name")
    require(isinstance(teams, dict) and len(teams) <= MAX_PLAYERS, "Invalid teams.")
    membership, occupancy = [], {mid: 0 for mid in missions}
    for tid, team in teams.items():
        identifier(tid, "Team ID")
        require(tid != "all", "Team ID all is reserved for the console selector.")
        exact(team, ["players", "completed", "active", "score"], "team")
        require(isinstance(team["players"], list) and team["players"]
                and all(isinstance(p, str) and p in roster for p in team["players"]), "Invalid team players.")
        membership.extend(team["players"])
        done = team["completed"]
        require(isinstance(done, list) and all(isinstance(m, str) and m in missions for m in done)
                and len(set(done)) == len(done), "Invalid/duplicate completed missions.")
        seen = set()
        for mid in done:
            require(set(missions[mid]["prerequisites"]) <= seen, "Completion prerequisite violation.")
            require("maze" not in seen, "Completion recorded after finale.")
            if mid == "maze":
                require(sum(missions[x]["kind"] == "main" for x in seen) >= settings["min_main"], "Premature finale completion.")
            seen.add(mid)
        active = team["active"]
        require(active is None or isinstance(active, str) and active in missions, "Unknown active mission.")
        if active is not None:
            require(active not in seen and "maze" not in seen, "Active mission already completed or team finished.")
            require(missions[active]["enabled"], "Disabled active mission.")
            require(set(missions[active]["prerequisites"]) <= seen, "Active prerequisite violation.")
            if active == "maze":
                require(sum(missions[x]["kind"] == "main" for x in seen) >= settings["min_main"], "Premature active finale.")
            occupancy[active] += 1
        require(type(team["score"]) is int and team["score"] == sum(missions[x]["points"] for x in done), "Score does not match completions.")
    require(len(membership) == len(set(membership)), "Player assigned more than once.")
    if teams:
        require(set(membership) == set(roster), "Every roster player must belong to exactly one team.")
    for mid, count in occupancy.items():
        require(count <= missions[mid]["capacity"], f"Capacity exceeded for {mid}.")
    waiting = state["waiting"]
    require(isinstance(waiting, list) and len(waiting) <= len(teams), "Invalid waiting list.")
    waiting_ids = set()
    for entry in waiting:
        exact(entry, ["team", "mission"], "waiting record")
        tid, mid = entry["team"], entry["mission"]
        require(isinstance(tid, str) and tid in teams and tid not in waiting_ids, "Unknown/duplicate waiting team.")
        require(teams[tid]["active"] is None and "maze" not in teams[tid]["completed"], "Active/finished team in waiting list.")
        require(mid is None or isinstance(mid, str) and mid in missions, "Unknown waiting mission.")
        if mid is not None:
            require(mid not in teams[tid]["completed"] and missions[mid]["enabled"]
                    and set(missions[mid]["prerequisites"]) <= set(teams[tid]["completed"]), "Ineligible waiting mission.")
            if mid == "maze":
                require(sum(missions[x]["kind"] == "main" for x in teams[tid]["completed"]) >= settings["min_main"], "Premature queued finale.")
        waiting_ids.add(tid)
    audit = state["audit"]
    require(isinstance(audit, list) and len(audit) <= 20000, "Invalid/full audit log (maximum 20000 records).")
    for record in audit:
        exact(record, ["time", "actor", "action", "detail"], "audit record")
        require(record["actor"] == "organizer", "Invalid audit actor.")
        for key in ("time", "action", "detail"):
            text(record[key], f"audit {key}", 20000)
    return missions


def atomic_write(path, content):
    """Same-directory temp + fsync + replace; private mode for roster-containing files."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        if os.name == "posix":
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class Store:
    """Single-process local store. Fingerprint rejects stale sequential writers."""
    def __init__(self, path, catalog_path=None):
        self.path = Path(path).expanduser().resolve()
        self.fingerprint = None
        if self.path.exists():
            require(catalog_path is None, "--catalog is only accepted for a new state; existing state owns its catalog.")
            self.reload()
        else:
            catalog = read_json(catalog_path or Path(__file__).with_name("catalog.json"))
            self.state = fresh(catalog)
            validate_state(self.state)
            self.save()

    def _bytes(self):
        require(self.path.stat().st_size <= MAX_JSON, "State file is too large.")
        with self.path.open("rb") as handle:
            raw = handle.read(MAX_JSON + 1)
        require(len(raw) <= MAX_JSON, "State file is too large.")
        return raw

    def reload(self):
        try:
            # Read a single snapshot rather than parsing one version and hashing another.
            raw = self._bytes()
            def unique_pairs(items):
                result = {}
                for key, value in items:
                    require(key not in result, f"Duplicate JSON key: {key}")
                    result[key] = value
                return result
            state = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs)
            validate_state(state)
            self.state = state
            self.fingerprint = hashlib.sha256(raw).hexdigest()
        except (OSError, ValueError, RecursionError) as exc:
            raise OrganizerError(f"Cannot reload state: {exc}") from None

    def save(self):
        validate_state(self.state)
        content = (json.dumps(self.state, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
        require(len(content) <= MAX_JSON, "State exceeds 8 MiB; archive event and reset explicitly.")
        try:
            if self.path.exists():
                old = self._bytes()
                require(self.fingerprint is not None and hashlib.sha256(old).hexdigest() == self.fingerprint,
                        "State changed on disk. No overwrite performed; use reload after checking the other organizer.")
                atomic_write(str(self.path) + ".bak", old)
            else:
                require(self.fingerprint is None, "State file disappeared; restore it before saving.")
            atomic_write(self.path, content)
            self.fingerprint = hashlib.sha256(content).hexdigest()
        except OSError as exc:
            raise OrganizerError(f"Cannot save state: {exc}") from None

    def transaction(self, action, detail, mutate):
        old = copy.deepcopy(self.state)
        try:
            result = mutate()
            self.state["audit"].append({"time": datetime.now(timezone.utc).isoformat(),
                                        "actor": "organizer", "action": action, "detail": str(detail)})
            self.save()
            return result
        except Exception:
            self.state = old
            raise


class Event:
    def __init__(self, store):
        self.store = store

    @property
    def s(self):
        return self.store.state

    @property
    def missions(self):
        return {m["id"]: m for m in self.s["catalog"]["missions"]}

    def team(self, tid):
        require(tid in self.s["teams"], f"Unknown team: {tid}")
        return self.s["teams"][tid]

    def mission(self, mid):
        require(mid in self.missions, f"Unknown mission: {mid}")
        return self.missions[mid]

    def tx(self, action, detail, func):
        return self.store.transaction(action, detail, func)

    def add_players(self, players):
        require(not self.s["teams"], "Roster is frozen after team formation. Reset explicitly to change players.")
        require(players and len(self.s["roster"]) + len(players) <= MAX_PLAYERS, "Empty/oversized roster import.")
        seen = set(self.s["roster"])
        for pid, name in players:
            identifier(pid, "Player ID")
            text(name, "Player name")
            require(pid not in seen, f"Duplicate player ID: {pid} (IDs are case-sensitive).")
            seen.add(pid)
        return self.tx("roster_add", f"{len(players)} players", lambda: self.s["roster"].update(players))

    def import_roster(self, path):
        try:
            path = Path(path).expanduser()
            require(path.stat().st_size <= MAX_CSV, "Roster CSV exceeds 1 MiB.")
            with path.open("rb") as handle:
                raw = handle.read(MAX_CSV + 1)
            require(len(raw) <= MAX_CSV, "Roster CSV exceeds 1 MiB.")
            players = []
            reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
            require(reader.fieldnames == ["id", "name"], "CSV header must be exactly id,name.")
            for row in reader:
                require(set(row) == {"id", "name"} and all(isinstance(v, str) for v in row.values()), "Malformed roster CSV row.")
                players.append((row["id"].strip(), row["name"].strip()))
                require(len(players) <= MAX_PLAYERS, "Roster exceeds 2000 players.")
            self.add_players(players)
        except (OSError, UnicodeError, csv.Error) as exc:
            raise OrganizerError(f"Cannot import CSV: {exc}") from None

    def form_teams(self, size=3, seed=2041, formation="random", mapping="", confirm=""):
        require(self.s["roster"], "Add/import players first.")
        integer(size, 1, MAX_PLAYERS, "Team size")
        integer(seed, 0, 2**63-1, "Team seed")
        require(formation in ("random", "controlled"), "Formation must be random or controlled.")
        activity = bool(self.s["waiting"]) or any(t["active"] or t["completed"] for t in self.s["teams"].values())
        require(not activity or confirm == "REGENERATE", "Activity exists. Set confirm REGENERATE to erase ALL assignments, completions, scores and waiting entries; roster/settings retained.")
        groups = {}
        if formation == "random":
            require(not mapping, "Mapping is only for controlled organizer formation.")
            players = sorted(self.s["roster"])
            random.Random(seed).shuffle(players)
            count = math.ceil(len(players) / size)
            groups = {f"T{i+1:03d}": players[i::count] for i in range(count)}
        else:
            # Explicit organizer override, never player self-selection.
            require(mapping, "Controlled formation requires mapping T001=P01,P02;T002=P03,P04 (quote at set).")
            for chunk in mapping.split(";"):
                parts = chunk.split("=")
                require(len(parts) == 2, "Malformed organizer team mapping.")
                tid, members = parts
                identifier(tid, "Team ID")
                require(tid not in groups, "Duplicate team ID in mapping.")
                groups[tid] = members.split(",")
            flattened = [p for members in groups.values() for p in members]
            require(len(flattened) == len(set(flattened)) and set(flattened) == set(self.s["roster"]), "Mapping must assign every roster ID exactly once.")
        def change():
            self.s["teams"] = {tid: {"players": members, "completed": [], "active": None, "score": 0} for tid, members in groups.items()}
            self.s["waiting"] = []
            return f"Formed {len(groups)} teams by organizer ({formation}); size range {min(map(len, groups.values()))}–{max(map(len, groups.values()))}."
        return self.tx("teams_form", f"formation={formation}; seed={seed}; size={size}; destructive={activity}", change)

    def eligible(self, tid):
        team = self.team(tid)
        if team["active"] or "maze" in team["completed"]:
            return []
        done = set(team["completed"])
        main_done = sum(self.missions[x]["kind"] == "main" for x in done)
        return [mid for mid, m in self.missions.items() if m["enabled"] and mid not in done
                and set(m["prerequisites"]) <= done
                and (m["kind"] != "finale" or main_done >= self.s["settings"]["min_main"])]

    def occupied(self, mid):
        return sum(t["active"] == mid for t in self.s["teams"].values())

    def _attempt(self, tid, requested=None):
        available = self.eligible(tid)
        if requested:
            require(requested in available, f"{requested} is not eligible for {tid}; check prerequisites, completion, active mission and enable status.")
            candidates = [requested]
        else:
            if self.s["settings"]["assignment_mode"] == "controlled" and "warehouse" in self.team(tid)["completed"]:
                return "waiting: organizer must select an eligible mission"
            candidates = available
        free = [m for m in candidates if self.occupied(m) < self.missions[m]["capacity"]]
        if not free:
            return "waiting: no eligible free mission (capacity, enable status or prerequisites)"
        # Prefer finale after threshold; if occupied, other available main missions remain usable.
        if "maze" in free and requested is None:
            mid = "maze"
        elif requested:
            mid = requested
        else:
            settings = self.s["settings"]
            mid = random.Random(f"{settings['seed']}:{settings['draw']}").choice(sorted(free))
            settings["draw"] += 1
        self.team(tid)["active"] = mid
        self.s["waiting"] = [e for e in self.s["waiting"] if e["team"] != tid]
        return f"assigned {mid}"

    def assign(self, tid="all", mission=""):
        require(self.s["teams"], "Form teams first.")
        require(not mission or self.s["settings"]["assignment_mode"] == "controlled", "Explicit mission requires controlled assignment mode.")
        require(not mission or tid != "all", "Pick one team for a controlled mission.")
        tids = sorted(self.s["teams"]) if tid == "all" else [tid]
        for team_id in tids:
            self.team(team_id)
        if mission:
            self.mission(mission)
            require(mission in self.eligible(tid), "Requested mission is not eligible.")
        def change():
            lines = []
            for team_id in tids:
                team = self.team(team_id)
                if team["active"]:
                    lines.append(f"{team_id}: already active {team['active']}")
                    continue
                if "maze" in team["completed"]:
                    lines.append(f"{team_id}: finished")
                    continue
                result = self._attempt(team_id, mission or None)
                if result.startswith("waiting"):
                    entry = next((e for e in self.s["waiting"] if e["team"] == team_id), None)
                    if entry is None:
                        self.s["waiting"].append({"team": team_id, "mission": mission or None})
                    elif mission:
                        entry["mission"] = mission
                lines.append(f"{team_id}: {result}")
            return "\n".join(lines)
        return self.tx("assign", f"team={tid}; mission={mission or 'auto'}", change)

    def dispatch(self):
        def change():
            lines = []
            for entry in list(self.s["waiting"]):
                result = self._attempt(entry["team"], entry["mission"])
                lines.append(f"{entry['team']}: {result}")
            return "\n".join(lines) or "No waiting teams."
        return self.tx("dispatch", "FIFO waiting list; blocked requests do not block others", change)

    def complete(self, tid, mission=""):
        team = self.team(tid)
        active = team["active"]
        require(active is not None, "Team has no active mission; duplicate completion is not allowed.")
        require(not mission or mission == active, f"Active mission is {active}, not {mission}.")
        def change():
            team["completed"].append(active)
            team["score"] += self.mission(active)["points"]
            team["active"] = None
            return f"{tid}: completed {active}; +{self.mission(active)['points']} points; total={team['score']}. Capacity released. Use assign or dispatch; no automatic follow-up."
        return self.tx("complete", f"team={tid}; mission={active}", change)

    def configure(self, option, value):
        require(option in ("assignment_mode", "seed", "min_main"), "Unknown setting.")
        settings = copy.deepcopy(self.s["settings"])
        settings[option] = value
        if option == "seed":
            settings["draw"] = 0
        def change():
            self.s["settings"] = settings
            return f"{option}={value}. Existing active allocations unchanged."
        return self.tx("configure", f"{option}={value}", change)

    def resource(self, mid, capacity=None, enabled=None):
        mission = self.mission(mid)
        if capacity is not None:
            integer(capacity, 1, 2000, "Capacity")
            require(capacity >= self.occupied(mid), "Capacity cannot be below active allocations.")
        if enabled is not None:
            require(type(enabled) is bool, "Enabled must be boolean.")
            require(enabled or mid not in ("warehouse", "maze"), "Intro/finale cannot be disabled.")
            require(enabled or self.occupied(mid) == 0, "Cannot disable an active mission.")
            require(enabled or not any(e["mission"] == mid for e in self.s["waiting"]), "Cannot disable a mission explicitly requested by a waiting team; select another mission first.")
        def change():
            if capacity is not None:
                mission["capacity"] = capacity
            if enabled is not None:
                mission["enabled"] = enabled
            return f"{mid}: capacity={mission['capacity']}; enabled={mission['enabled']}. Run dispatch to retry waiting teams."
        return self.tx("resource", f"{mid}; capacity={capacity}; enabled={enabled}", change)

    def reset(self, confirm):
        require(confirm == "RESET", "Reset requires the exact confirmation RESET.")
        def change():
            new = fresh(self.s["catalog"])
            self.s.clear()
            self.s.update(new)
            return "Event reset: roster, teams, scores, queue and settings cleared; current catalog/capacities retained. Prior full state is in .bak until next save."
        return self.tx("reset", "explicit RESET confirmation", change)

    def status(self):
        lines = [f"{self.s['catalog']['event']} | mode={self.s['settings']['assignment_mode']} | min_main={self.s['settings']['min_main']} | players={len(self.s['roster'])} | teams={len(self.s['teams'])}"]
        for tid, t in sorted(self.s["teams"].items()):
            names = ", ".join(self.s["roster"][p] for p in t["players"])
            lines.append(f"{tid} | {names} | active={t['active'] or '-'} | completed={','.join(t['completed']) or '-'} | score={t['score']}")
        lines.append("Waiting: " + (", ".join(f"{e['team']}:{e['mission'] or 'auto'}" for e in self.s["waiting"]) or "none"))
        return "\n".join(lines)

    def leaderboard(self):
        ordered = sorted(self.s["teams"].items(), key=lambda item: (-item[1]["score"], item[0]))
        return "\n".join(f"{i}. {tid} {team['score']} points" for i, (tid, team) in enumerate(ordered, 1)) or "No teams."
