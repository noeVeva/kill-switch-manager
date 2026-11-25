"""Executable stdlib tests; all mutable event states live in temporary directories."""
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine import Event, OrganizerError, Store, fresh, read_json, validate_catalog, validate_state
from killswitch import Console, MODULES


class EventTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "state.json"
        self.store = Store(self.path)
        self.e = Event(self.store)

    def players(self, count=12, size=3):
        self.e.add_players([(f"P{i:02d}", f"Player {i} 测试") for i in range(count)])
        self.e.form_teams(size=size, seed=42)

    def intro_done(self, count=12, size=3):
        self.players(count, size)
        self.e.assign()
        for tid in self.e.s["teams"]:
            self.e.complete(tid, "warehouse")

    def test_balanced_seeded_reproducible_teams(self):
        self.players(17, 4)
        original = copy.deepcopy(self.e.s["teams"])
        sizes = [len(t["players"]) for t in original.values()]
        self.assertLessEqual(max(sizes) - min(sizes), 1)
        self.assertLessEqual(max(sizes), 4)
        self.e.form_teams(size=4, seed=42)
        self.assertEqual(original, self.e.s["teams"])
        self.e.form_teams(size=4, seed=43)
        self.assertNotEqual(original, self.e.s["teams"])

    def test_unicode_and_duplicate_player_validation_atomic(self):
        self.e.add_players([("P1", "يوسف Zoë")])
        old = copy.deepcopy(self.e.s)
        with self.assertRaisesRegex(OrganizerError, "Duplicate"):
            self.e.add_players([("P2", "New"), ("P1", "Collision")])
        self.assertEqual(old, self.e.s)
        with self.assertRaises(OrganizerError):
            self.e.add_players([("bad id", "Bad")])
        with self.assertRaises(OrganizerError):
            self.e.add_players([("P2", "\x1b[31m")])

    def test_csv_import_and_collision_all_or_nothing(self):
        self.e.import_roster(ROOT / "examples/roster.csv")
        self.assertEqual(len(self.e.s["roster"]), 12)
        self.assertIn("يوسف منصور", self.e.s["roster"].values())
        before = copy.deepcopy(self.e.s)
        with self.assertRaises(OrganizerError):
            self.e.import_roster(ROOT / "examples/roster.csv")
        self.assertEqual(before, self.e.s)
        bad = Path(self.tmp.name) / "bad.csv"
        for content in ("name,id\nA,P1\n", "id,name\nP1,One\nP1,Two\n", "id,name\nP1,One,extra\n", "id,name\nP1\n"):
            bad.write_text(content, encoding="utf-8")
            with self.assertRaises(OrganizerError):
                self.e.import_roster(bad)

    def test_shared_first_then_divergent_branches(self):
        self.players()
        self.e.assign()
        self.assertEqual({t["active"] for t in self.e.s["teams"].values()}, {"warehouse"})
        for tid in self.e.s["teams"]:
            self.e.complete(tid)
        self.e.assign()
        assigned = [t["active"] for t in self.e.s["teams"].values()]
        self.assertEqual(len(set(assigned)), 4)
        self.assertNotIn("maze", assigned)
        self.assertNotIn("warehouse", assigned)
        self.assertTrue(all(self.e.occupied(mid) <= m["capacity"] for mid, m in self.e.missions.items()))

    def test_random_assignment_seed_resume_reproducibility(self):
        self.intro_done()
        checkpoint = copy.deepcopy(self.e.s)
        self.e.assign()
        assigned = {tid: t["active"] for tid, t in self.e.s["teams"].items()}
        self.store.state = checkpoint
        self.store.save()
        resumed = Event(Store(self.path))
        resumed.assign()
        self.assertEqual(assigned, {tid: t["active"] for tid, t in resumed.s["teams"].items()})

    def test_intro_capacity_wait_and_dispatch(self):
        self.players(6, 3)
        self.e.resource("warehouse", capacity=1)
        result = self.e.assign()
        self.assertIn("waiting", result)
        self.assertEqual(self.e.occupied("warehouse"), 1)
        self.assertEqual(len(self.e.s["waiting"]), 1)
        self.e.complete("T001")
        self.e.dispatch()
        self.assertEqual(self.e.team("T002")["active"], "warehouse")
        self.assertEqual(self.e.s["waiting"], [])

    def test_all_branch_capacity_full_wait_and_retry(self):
        self.intro_done(39, 3)  # 13 teams, 12 main resource slots.
        self.e.assign()
        self.assertEqual(len(self.e.s["waiting"]), 1)
        waiting = self.e.s["waiting"][0]["team"]
        released = self.e.team("T001")["active"]
        self.e.complete("T001")
        self.e.dispatch()
        self.assertEqual(self.e.team(waiting)["active"], released)
        self.assertFalse(self.e.s["waiting"])

    def test_controlled_capacity_prerequisites_and_wait(self):
        self.players(6, 3)
        self.e.configure("assignment_mode", "controlled")
        with self.assertRaises(OrganizerError):
            self.e.assign("T001", "maze")
        with self.assertRaises(OrganizerError):
            self.e.assign("T001", "quadruped")
        self.e.assign()  # controlled still uses shared intro.
        for tid in self.e.s["teams"]:
            self.e.complete(tid)
        self.e.assign("T001", "quadruped")
        self.e.assign("T002", "quadruped")
        self.assertEqual(self.e.team("T002")["active"], None)
        self.assertEqual(self.e.s["waiting"], [{"team": "T002", "mission": "quadruped"}])
        with self.assertRaises(OrganizerError):
            self.e.resource("quadruped", enabled=False)
        self.e.complete("T001")
        self.e.dispatch()
        self.assertEqual(self.e.team("T002")["active"], "quadruped")

    def test_controlled_auto_branch_waits_for_organizer(self):
        self.intro_done(3, 3)
        self.e.configure("assignment_mode", "controlled")
        self.e.assign()
        self.assertEqual(self.e.team("T001")["active"], None)
        self.assertIn("organizer", self.e.dispatch())
        self.e.assign("T001", "humanoid")
        self.assertEqual(self.e.team("T001")["active"], "humanoid")
        self.assertEqual(self.e.s["waiting"], [])

    def test_score_release_and_duplicate_completion(self):
        self.players(3, 3)
        self.e.assign()
        self.e.complete("T001", "warehouse")
        self.assertEqual(self.e.team("T001")["score"], 100)
        self.assertEqual(self.e.occupied("warehouse"), 0)
        with self.assertRaisesRegex(OrganizerError, "duplicate"):
            self.e.complete("T001", "warehouse")
        self.e.assign()
        active = self.e.team("T001")["active"]
        with self.assertRaises(OrganizerError):
            self.e.complete("T001", "warehouse")
        self.e.complete("T001", active)
        self.assertEqual(self.e.team("T001")["score"], 100 + self.e.mission(active)["points"])
        self.assertNotIn(active, self.e.eligible("T001"))

    def test_finale_gating_default_and_full_progression(self):
        self.intro_done(3, 3)
        self.assertNotIn("maze", self.e.eligible("T001"))
        for i in range(3):
            self.e.assign()
            self.assertNotEqual(self.e.team("T001")["active"], "maze")
            self.e.complete("T001")
        self.assertIn("maze", self.e.eligible("T001"))
        self.e.assign()
        self.assertEqual(self.e.team("T001")["active"], "maze")
        self.e.complete("T001")
        self.assertEqual(self.e.eligible("T001"), [])
        self.assertIn("finished", self.e.assign())
        self.assertIn("points", self.e.leaderboard())

    def test_threshold_configuration_and_no_retroactive_invalid_finale(self):
        self.intro_done(3, 3)
        self.e.configure("min_main", 1)
        self.e.assign()
        self.e.complete("T001")
        self.e.assign()
        self.assertEqual(self.e.team("T001")["active"], "maze")
        with self.assertRaises(OrganizerError):
            self.e.configure("min_main", 3)
        self.assertEqual(self.e.s["settings"]["min_main"], 1)
        for invalid in (0, 13, "3", True):
            with self.assertRaises(OrganizerError):
                self.e.configure("min_main", invalid)

    def test_capacity_and_enable_guards(self):
        self.players(6, 3)
        self.e.assign()
        with self.assertRaises(OrganizerError):
            self.e.resource("warehouse", capacity=1)
        with self.assertRaises(OrganizerError):
            self.e.resource("warehouse", enabled=False)
        for tid in self.e.s["teams"]:
            self.e.complete(tid)
        self.e.configure("assignment_mode", "controlled")
        self.e.assign("T001", "medical")
        with self.assertRaises(OrganizerError):
            self.e.resource("medical", enabled=False)
        self.e.complete("T001")
        self.e.resource("medical", enabled=False)
        self.assertNotIn("medical", self.e.eligible("T002"))

    def test_disable_cannot_make_finale_unreachable(self):
        mains = [mid for mid, m in self.e.missions.items() if m["kind"] == "main"]
        for mid in mains[:-3]:
            self.e.resource(mid, enabled=False)
        with self.assertRaisesRegex(OrganizerError, "reachable"):
            self.e.resource(mains[-3], enabled=False)
        self.assertTrue(self.e.mission(mains[-3])["enabled"])

    def test_regeneration_confirmation_and_roster_freeze(self):
        self.players()
        with self.assertRaises(OrganizerError):
            self.e.add_players([("P100", "Late")])
        self.e.assign()
        old = copy.deepcopy(self.e.s["teams"])
        with self.assertRaisesRegex(OrganizerError, "REGENERATE"):
            self.e.form_teams(seed=9)
        self.assertEqual(old, self.e.s["teams"])
        self.e.form_teams(seed=9, confirm="REGENERATE")
        self.assertTrue(all(t["active"] is None and not t["completed"] for t in self.e.s["teams"].values()))

    def test_controlled_organizer_formation_and_validation(self):
        self.e.add_players([("A", "A"), ("B", "B"), ("C", "C")])
        for invalid in ("One=A,B;Two=B", "One=A,B", "One=A;One=B,C", "all=A,B,C", "One=A=B"):
            with self.assertRaises(OrganizerError):
                self.e.form_teams(formation="controlled", mapping=invalid)
        self.e.form_teams(formation="controlled", mapping="Alpha=A,C;Beta=B")
        self.assertEqual(self.e.team("Alpha")["players"], ["A", "C"])
        self.assertEqual(self.e.s["settings"]["assignment_mode"], "random")

    def test_save_reload_and_backup(self):
        self.players()
        before = self.path.read_bytes()
        self.e.assign()
        self.assertEqual(Path(str(self.path) + ".bak").read_bytes(), before)
        restored = Event(Store(self.path))
        self.assertEqual(restored.s, self.e.s)
        self.assertEqual(restored.s["audit"][-1]["action"], "assign")

    def test_reset_requires_confirmation_and_backup(self):
        self.players()
        before = self.path.read_bytes()
        with self.assertRaises(OrganizerError):
            self.e.reset("yes")
        self.e.reset("RESET")
        self.assertFalse(self.e.s["roster"])
        self.assertFalse(self.e.s["teams"])
        self.assertEqual(Path(str(self.path) + ".bak").read_bytes(), before)
        self.assertEqual(self.e.s["audit"][-1]["action"], "reset")

    def test_stale_writer_rejected_and_transaction_rolled_back(self):
        second = Event(Store(self.path))
        self.e.add_players([("A", "First")])
        with self.assertRaisesRegex(OrganizerError, "changed on disk"):
            second.add_players([("B", "Second")])
        self.assertFalse(second.s["roster"])
        second.store.reload()
        self.assertIn("A", second.s["roster"])

    def test_invalid_reload_preserves_memory_and_disk(self):
        self.players()
        valid_memory = copy.deepcopy(self.e.s)
        for invalid in ("{broken", '{"schema_version":1,"schema_version":1}', "[]", "null"):
            self.path.write_text(invalid)
            with self.assertRaises(OrganizerError):
                self.store.reload()
            self.assertEqual(self.e.s, valid_memory)
            self.assertEqual(self.path.read_text(), invalid)

    def test_invalid_state_variants_rejected(self):
        self.players(6, 3)
        self.e.assign()
        original = copy.deepcopy(self.e.s)
        mutations = [
            lambda s: s.update(schema_version=99),
            lambda s: s["settings"].update(seed=-1),
            lambda s: s["teams"]["T001"].update(score=999),
            lambda s: s["teams"]["T001"].update(active="maze"),
            lambda s: s["teams"]["T001"].update(completed=["quadruped"]),
            lambda s: s["teams"]["T001"]["players"].append(s["teams"]["T002"]["players"][0]),
            lambda s: s.update(waiting=[{"team": "missing", "mission": None}]),
            lambda s: s["catalog"]["missions"][0].update(capacity=1),
            lambda s: s["teams"]["T001"].update(active=[]),
        ]
        for mutate in mutations:
            state = copy.deepcopy(original)
            mutate(state)
            with self.subTest(mutate=mutate):
                with self.assertRaises(OrganizerError):
                    validate_state(state)

    def test_invalid_catalog_and_cycles_rejected(self):
        original = copy.deepcopy(self.e.s["catalog"])
        mutations = [
            lambda c: c["missions"][1].update(id="warehouse"),
            lambda c: c["missions"][1].update(capacity=0),
            lambda c: c["missions"][1].update(prerequisites=["warehouse", "missing"]),
            lambda c: c["missions"][1].update(prerequisites=["warehouse", "humanoid"]),
            lambda c: c["missions"][0].update(enabled=False),
        ]
        original["missions"][2]["prerequisites"].append("quadruped")
        for mutate in mutations:
            state = copy.deepcopy(original)
            mutate(state)
            with self.assertRaises(OrganizerError):
                validate_catalog(state)

    def test_advanced_dependency_eligibility(self):
        cat = self.e.s["catalog"]
        next(m for m in cat["missions"] if m["id"] == "cpu_rings")["prerequisites"].append("quadruped")
        self.store.save()
        self.intro_done(3, 3)
        self.assertNotIn("cpu_rings", self.e.eligible("T001"))
        self.e.configure("assignment_mode", "controlled")
        self.e.assign("T001", "quadruped")
        self.e.complete("T001")
        self.assertIn("cpu_rings", self.e.eligible("T001"))

    def test_console_invalid_inputs_no_traceback_or_repeat(self):
        output = io.StringIO()
        c = Console(self.e, stdout=output)
        lines = ["run", "use missing", "set size 2", "show nonsense", "audit nope", "show options extra", "reset yes", "use teams/create", "set size nope", "set size 0", "set formation other", "set missing value", 'set seed "unterminated', "use roster/add", "run", "set id X", 'set name "Zoë Test"', "run", "", "run", "!whoami", "exit extra"]
        for line in lines:
            c.onecmd(line)
        self.assertEqual(self.e.s["roster"], {"X": "Zoë Test"})
        self.assertGreater(output.getvalue().count("Error:"), 10)
        self.assertNotIn("Traceback", output.getvalue())
        self.assertIn("progress/complete", c.complete_use("progress", "", 0, 0))
        c.onecmd("back")
        self.assertEqual(c.prompt, "killswitch > ")


class AppTests(unittest.TestCase):
    def cli(self, *args, input=""):
        return subprocess.run([sys.executable, str(ROOT / "killswitch.py"), *map(str, args)], cwd=ROOT,
                              input=input, capture_output=True, text=True, timeout=15)

    def test_help_smoke(self):
        result = self.cli("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--state", result.stdout)
        self.assertIn("--catalog", result.stdout)

    def test_documented_walkthrough_real_subprocess(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / "demo.json"
            result = self.cli("--state", state, input=(ROOT / "examples/walkthrough.txt").read_text())
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("Error:", result.stdout)
            self.assertNotIn("Traceback", result.stdout + result.stderr)
            event = Event(Store(state))
            self.assertEqual(event.s["settings"]["assignment_mode"], "controlled")
            self.assertEqual(event.team("T001")["active"], "quadruped")
            self.assertEqual(len(event.team("T001")["completed"]), 2)
            self.assertIn("State reloaded and validated", result.stdout)

    def test_full_event_console_queue_and_finale(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / "full.json"
            result = self.cli("--state", state, input=(ROOT / "examples/full-event.txt").read_text())
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("Error:", result.stdout)
            event = Event(Store(state))
            self.assertEqual(event.team("T001")["completed"], ["warehouse", "quadruped", "humanoid", "drones", "maze"])
            self.assertEqual(event.team("T001")["score"], 1200)
            self.assertEqual(event.team("T002")["score"], 300)
            self.assertFalse(event.s["waiting"])
            self.assertIn("waiting: no eligible free mission", result.stdout)

    def test_invalid_startup_no_traceback_or_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / "bad.json"
            state.write_text("{broken")
            result = self.cli("--state", state)
            self.assertEqual(result.returncode, 2)
            self.assertIn("Error:", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(state.read_text(), "{broken")

    def test_bad_catalog_and_existing_catalog_override(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / "state.json"
            cat = Path(temp) / "catalog.json"
            cat.write_text("{}")
            bad = self.cli("--state", state, "--catalog", cat)
            self.assertEqual(bad.returncode, 2)
            self.assertFalse(state.exists())
            Store(state)
            override = self.cli("--state", state, "--catalog", ROOT / "catalog.json")
            self.assertEqual(override.returncode, 2)
            self.assertIn("new state", override.stderr)

    def test_module_reference_matches_implemented_interface(self):
        self.assertEqual(len(MODULES), 11)
        self.assertTrue(all("description" in module for module in MODULES.values()))
        for module in MODULES.values():
            for option in module["options"].values():
                self.assertIn("default", option)
                self.assertIn("type", option)
                self.assertIn("required", option)


if __name__ == "__main__":
    unittest.main(verbosity=2)
