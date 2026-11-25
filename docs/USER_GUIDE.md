---
lang: en
papersize: a4
header-includes:
  - |
    \usepackage{xcolor,titlesec,fancyhdr,fvextra}
    \definecolor{navy}{HTML}{112A40}
    \definecolor{teal}{HTML}{087E8B}
    \titleformat{\section}{\Large\bfseries\color{navy}}{}{0pt}{}
    \titleformat{\subsection}{\large\bfseries\color{teal}}{}{0pt}{}
    \titlespacing*{\section}{0pt}{0pt}{12pt}
    \titlespacing*{\subsection}{0pt}{13pt}{6pt}
    \pagestyle{fancy}
    \fancyhf{}
    \fancyhead[L]{\small\color{teal} KILL SWITCH MANAGER}
    \fancyhead[R]{\small ORGANIZER USER GUIDE}
    \fancyfoot[L]{\footnotesize Local records / single organizer}
    \fancyfoot[R]{\thepage}
    \setlength{\headheight}{15pt}
    \fvset{fontsize=\small}
    \AtBeginDocument{\RecustomVerbatimEnvironment{verbatim}{Verbatim}{breaklines=true,fontsize=\small}}
---

\thispagestyle{empty}
\vspace*{1.5cm}
```{=latex}
{\color{teal}\Large LOCAL EVENT OPERATIONS}
```

\vspace{0.6cm}
```{=latex}
{\color{navy}\fontsize{35}{41}\selectfont\bfseries Kill Switch\\Manager}
```

\vspace{0.6cm}
```{=latex}
{\Large Organizer user guide}
```

**A separate guide to the completed Python implementation**

By Wassim Oukoudda · StyxSec × Oblivion

\vspace{1cm}
Manage a roster, form random teams, allocate missions without resource collisions, verify progress and retain local event records. The contextual console uses a simple **select → configure → inspect → run** pattern familiar from module-oriented consoles; it has no offensive functionality.

**No installation or third-party Python packages are needed.** Python 3.9+ is the stated compatibility target; the implementation was tested on Linux with Python 3.11.15. Other Python versions and operating systems are not separately certified.

\vfill
This software manages **organizer records only**. It does not build or host playable labs, validate flags, run attacks, control devices or provision infrastructure. All bundled challenge descriptions concern fictional isolated scenarios or offline artifacts still to be authored.

\newpage

# 1 / Executive Summary: start here

## Unpack and launch

Extract `kill-switch-manager.zip` using your archive application. On Linux, an equivalent terminal workflow is:

```sh
unzip kill-switch-manager.zip
cd kill-switch-manager
python3 --version
python3 killswitch.py --help
python3 killswitch.py
```

No `pip install` is required: only the Python standard library is used. The default launch creates `event-state.json` beside `killswitch.py` if absent, or **resumes it if present**. It is not a fresh-event command when that file already exists.

For a clean practice event, choose a filename that does not yet exist:

```sh
python3 killswitch.py --state practice-event.json
```

Relative paths resolve from the current working directory. Run the examples from the extracted project folder so `examples/roster.csv` resolves correctly. A nonexistent **state file** is created; a nonexistent CSV or catalog path is an error. Keep the containing directory private and writable.

## Know the prompt

The base prompt is `killswitch >`. After `use roster/import`, it becomes `killswitch (roster/import) >`.

1. `show modules` lists the available operations.
2. `use <module>` selects one and initializes its default options.
3. `set <option> <value>` changes an option; quote multiword values.
4. `show options` inspects the current values and requirements.
5. `run` executes the operation; successful mutations auto-save.
6. `back` leaves the module and clears its options.

Type one command per line; the guide omits prompts so examples are easy to paste. Console commands are **not shell commands**. Tab completion for modules, options and selected values depends on terminal `readline` availability. Plain typed commands remain the portable approach.

\newpage

# 2 / Five-minute quickstart: form and start

Launch with a new `practice-event.json` as described on the previous page. The bundled roster contains twelve fictional participants, including Unicode names. The following is the tested walkthrough's opening sequence.

```text
show modules
use roster/import
set path examples/roster.csv
run
use teams/create
set size 3
set seed 42
show options
run
use missions/assign
run
status
```

**Expected milestones on the tested runtime:** the import reports twelve players; formation reports four balanced teams with size range 3–3; `T001`, `T002`, `T003` and `T004` all receive `warehouse`. No team has points yet. The normal event policy remains random formation—participants do not select teammates.

The `seed 42` here applies to **team formation only**. The event's assignment seed is still the default `2041`. Team balancing is by participant count, not skill or experience.

## Before recording completion

In a real event, first inspect the team's actual challenge proof outside this software. `progress/complete` records your assertion that the proof is valid; it does not inspect a submitted flag or grade an artifact.

For this practice walkthrough, the next page simulates those organizer decisions. It is a scheduling demonstration, not evidence that the fictional participants solved a playable lab.

**Already used this filename?** Exit and choose a different nonexistent `--state` path. Do not reset a real event simply to replay the quickstart.

\newpage

# 3 / Five-minute quickstart: branch and inspect

Continue in the same practice console. Options persist while staying in a module, so the `mission warehouse` guard below also applies to the other three completions.

```text
use progress/complete
set team T001
set mission warehouse
run
set team T002
run
set team T003
run
set team T004
run
use missions/assign
run
status
leaderboard
show settings
back
```

The actual bundled transcript shows the following first branch allocation under Python 3.11.15:

| Team | Active branch | Completed | Points |
|:--|:--|:--|--:|
| T001 | `elevator` | `warehouse` | 100 |
| T002 | `drones` | `warehouse` | 100 |
| T003 | `blind_spot` | `warehouse` | 100 |
| T004 | `vehicle` | `warehouse` | 100 |

The four branches differ because the default capacity is one concurrent team per branch. A mission can be used by another team later; uniqueness is not promised across the whole event. `leaderboard` sorts equal scores by team ID, not speed.

Use `status`, `show challenges` and `show queue` for routine checks. Successful completions release capacity but **never automatically assign the next mission**. Select `missions/assign` for idle teams or `queue/dispatch` for teams already waiting.

The complete tested input is `examples/walkthrough.txt`; its transcript is `artifacts/walkthrough-transcript.txt`. Later walkthrough steps demonstrate controlled assignment and save/reload.

\newpage

# 4 / Scheduling without surprises

## Shared entry, twelve branches, one finale

Every later mission in the supplied catalog requires `warehouse`. The twelve main branches all require only that introduction; they are alternatives, not a forced sequence. `maze` additionally requires **three distinct completed main missions** by default. Warehouse is excluded from that count.

A team has at most one active mission. Completed missions cannot be assigned or scored again. Completing `maze` finishes that team's progression. In random mode, a free eligible Maze is preferred; if it is occupied, another eligible free main branch may be assigned instead.

## Random versus controlled mission assignment

Random is the default. Selection uses eligible free mission IDs; it cannot overbook a full branch. `team all` is processed in sorted team-ID order, which makes runs reproducible but is **not a lottery-fair priority system**.

Controlled mode lets an organizer request a particular eligible mission for one team. It does not bypass prerequisites, completion, enable state or capacity. Generic controlled requests still assign the common warehouse, but after that they wait for the organizer to choose a branch.

## Waiting and capacity release

A blocked assignment records one waiting entry per team. An explicit controlled request remembers its mission. `queue/dispatch` retries existing waiting entries in FIFO order, skipping blocked requests so they do not block everyone behind them. It does not enqueue idle teams.

After a completion or capacity increase, dispatch is **manual**:

```text
show queue
use queue/dispatch
run
status
```

Mode changes leave active allocations intact. Explicit queued mission requests remain explicit and are honored even after a mode switch; generic requests follow the current mode. A new explicit assignment request can replace a team's queued mission. An empty mission request does not reliably clear an existing explicit queued target; choose another eligible explicit mission when changing that target.

\newpage

# 5 / Organizer overrides and event settings

## Select a controlled mission

For an idle team that has completed the warehouse, switch the event mode, inspect eligibility and request a branch:

```text
use event/config
set option assignment_mode
set value controlled
run
eligible T001
use missions/assign
set team T001
set mission quadruped
show options
run
```

If the branch is full, the team waits for that mission. To return to normal randomized assignment, select `event/config`, set `option assignment_mode`, set `value random` and `run`. This does not reroute active teams or erase explicit queued requests.

## Configure the finale threshold or assignment seed

```text
use event/config
set option min_main
set value 3
run
use event/config
set option seed
set value 2041
run
```

`min_main` must be at least one and no greater than the enabled reachable main-mission count. Changes that would make recorded finale activity premature are rejected. In a smaller custom catalog, a fresh/reset state uses the lesser of three and the reachable enabled main count.

Setting the assignment seed resets the persisted draw counter to zero. Reproduce a run using the same catalog, roster, team formation seed, assignment seed, Python runtime and **same command/order history**. Save/resume retains the draw counter. Team formation uses its own independent seed. Seeded pseudorandomness is reproducible, not cryptographic randomness; a seed alone does not establish fairness.

\newpage

# 6 / Resources and team formation overrides

## Set resource limits deliberately

```text
use resources/config
set mission quadruped
set capacity 4
show options
run
use queue/dispatch
run
```

This example, also used in the tested walkthrough, explicitly permits four simultaneous teams on the branch. Default capacities are warehouse `2000`, all main branches `1`, and Maze `1`. These are proposed organizer defaults, not claims about real lab capacity. Increase them only if separately authored resources can support that load.

`enabled false` disables an unused main mission; `enabled true` re-enables it. Capacity cannot drop below current occupancy. Intro and finale cannot be disabled. Disabling an active or explicitly queued mission is rejected, as are changes that make the finale unreachable. `resources/config` requires at least one of `capacity` or `enabled` to be set.

Disabling branches may still strand a particular team that has already completed the remaining enabled choices. Re-enable an uncompleted branch or reduce `min_main` if validation permits; there is no capacity or prerequisite bypass.

## Controlled formation is a separate override

`formation` in `teams/create` is unrelated to `assignment_mode`. Random formation is the normal no-self-selection rule. The organizer may explicitly supply a complete mapping for an exception. In a separate fresh practice event containing exactly players `P01` through `P04`, this mapping is valid:

```text
use teams/create
set formation controlled
set mapping "T001=P01,P02;T002=P03,P04"
show options
run
```

Every roster ID must occur exactly once. Quote the whole mapping; do not add spaces inside IDs. `size` does not constrain controlled mapping sizes. This four-player example is **not** valid for the twelve-player bundled roster. The roster freezes once teams exist; adding players then requires an explicit destructive fresh-start decision, not a silent import.

\newpage

# 7 / Global command reference

The following commands are implemented. Except where shown, do not append arguments. Type them at either the base or module prompt.

- **`help [command]`** — show command help; `help run` explains execution.
- **`show [topic]`** — topic is `modules` (default), `challenges`, `options`, `roster`, `teams`, `queue` or `settings`. Challenges show mission IDs, proposed points, occupancy, enable state and prerequisites; teams shows status.
- **`modules` / `challenges`** — aliases for the matching `show` topics.
- **`use <module>`** — select a module and reset its options to defaults, even when selecting the same module again.
- **`set <option> <value>`** — configure the current module. Quote multiword text and paths, for example `set name "Amina Haddad"`. Use `set mission ""` to clear an optional mission value. Type/range/enum checks happen immediately; business rules are checked when running.
- **`run`** — validate required values and execute the selected module. Successful mutations auto-save and audit. A printed `Error:` leaves event state unchanged; inspect and correct the input before proceeding.
- **`back`** — clear module selection and its options.
- **`status` / `leaderboard`** — show event progress or scores without selecting a module.
- **`eligible <team>`** — list prerequisite-eligible missions and occupancy. Includes full missions; eligibility is not the same as immediate availability. An active or finished team has no eligible next missions.
- **`audit [count]`** — display recent audit entries; default `20`, integer range `1..20000`. Entries include UTC time, organizer actor, action and detail. Plaintext logs are not tamper-proof.
- **`save`** — explicit atomic save; also updates the one-generation `.bak`. Normally unnecessary because mutations auto-save.
- **`reload`** — validate and reload disk state. Failure preserves current memory and disk bytes.
- **`reset RESET`** — destructive exact-confirmation reset; see Section 11.
- **`exit` / `quit` / EOF** — leave without an extra write. Committed changes are already saved.
- **Empty line** — no-op; it never repeats the previous mutation.

Options persist after `run` while remaining in a module, **except confirmation options**, which clear after successful execution. Selecting any module again resets all its option values. There is no shell execution, undo, score export or completion-correction command.

\newpage

# 8 / Module options: roster and teams

**Notation:** “empty” means the default empty string. Required values must be supplied before `run`. All eleven modules are listed across Sections 8–10.

## `roster/add`

Add one player; no teams may already exist.

- **`id`** — required string, default empty. Case-sensitive ASCII ID, 1–40 letters/digits/underscore/hyphen; first character alphanumeric. Player IDs must be unique. In controlled team mappings, the team ID `all` is reserved.
- **`name`** — required string, default empty. Printable Unicode display name, maximum 160 characters; quote multiword names. Duplicate display names are allowed.

## `roster/import`

Atomically import a UTF-8 CSV, optionally with a UTF-8 BOM. Exact header order is `id,name`. Imported IDs must not duplicate existing or imported IDs. On any error, no players from that import are added.

- **`path`** — required path string, default empty. Maximum CSV size 1 MiB; maximum total roster 2000 players. Run before forming teams.

```csv
id,name
P01,Amina Haddad
P02,Sam Okafor
```

## `teams/create`

Form teams from the complete roster. Random formation sorts player IDs, seeded-shuffles them and distributes round-robin into `ceil(players / size)` teams, numbered `T001` onward. Sizes differ by at most one and do not exceed `size`.

- **`size`** — integer, default `3`, range `1..2000`. Random formation's maximum team size; ignored for controlled mapping.
- **`seed`** — integer, default `2041`, range `0..9223372036854775807`. Formation seed only.
- **`formation`** — enum `random` (default) or `controlled`.
- **`mapping`** — string, default empty. Required for controlled formation: `T001=P01,P02;T002=P03,P04`. Every roster ID exactly once; quote the full value. Must be empty for random formation.
- **`confirm`** — enum empty (default) or exact `REGENERATE`. Required if any active assignment, completion or waiting entry exists. Regeneration deletes **all teams'** activity and scores; see Section 11.

\newpage

# 9 / Module options: missions and progress

## `missions/assign`

Assign or enqueue idle teams; active and finished teams are not given another mission. All allocations obey eligibility, enable state and capacity.

- **`team`** — string, default `all`; otherwise an existing team ID. `all` uses stable sorted team order.
- **`mission`** — string, default empty for automatic choice. A mission ID may be requested only in controlled assignment mode, for one team, not `all`. A full eligible request queues; an ineligible explicit request errors.

In random mode, an empty mission value selects an eligible free choice. In controlled mode, an empty mission value after the warehouse waits for organizer selection. To reuse a module after an explicit request, remember that the mission option persists until cleared or the module is selected again.

## `progress/complete`

Record **manually verified** completion of the team's active mission. Award the catalog points once and release capacity; do not auto-assign or auto-enqueue a follow-up.

- **`team`** — required string, default empty; one existing team ID.
- **`mission`** — optional string, default empty. If supplied, must match the current active mission; this is a safety guard. Empty uses the active mission.

A team without an active mission cannot be completed again. This prevents duplicate scoring, but does not independently establish that the proof was correct.

## `queue/dispatch`

**No options.** Select the module and `run`. Retry waiting entries in FIFO order, skipping blocked ones. No waiting entries means `No waiting teams.` Idle teams not already queued are unaffected.

## `event/status`

**No options.** Select and `run`, or type `status`. Shows player/team counts, assignment mode, finale threshold, names, active mission, completion history, points and waiting list.

## `event/leaderboard`

**No options.** Select and `run`, or type `leaderboard`. Sorts total points descending, then team ID ascending. It is not a completion-time ranking.

\newpage

# 10 / Module options: configuration and reset

## `event/config`

Change one scheduling setting; existing active allocations remain intact.

- **`option`** — enum, default `assignment_mode`; choices `assignment_mode`, `seed`, `min_main`.
- **`value`** — required string, default `random`. For `assignment_mode`: `random` or `controlled`. For `seed`: integer text in `0..9223372036854775807`, resetting draw to zero. For `min_main`: integer text in `1..enabled reachable main count`.

When changing the option from `assignment_mode` to a numeric setting, also change `value`: its default `random` is not a valid number. Validation rejects unreachable or retroactively invalid finale thresholds.

## `resources/config`

Change a mission's capacity and/or enabled state.

- **`mission`** — required string, default empty; existing mission ID.
- **`capacity`** — optional integer, default empty = unchanged; range `1..2000`. Cannot be lower than active occupancy.
- **`enabled`** — enum empty (default = unchanged), `true` or `false`.

At least one of capacity/enabled must be supplied. Warehouse and Maze cannot be disabled. No disabling active missions or missions explicitly requested by waiting teams. Reachability and recorded finale activity are validated; invalid changes roll back. Dispatch existing waiting teams explicitly after changing resources.

## `event/reset`

Clear the event, not the challenge catalog or current resource configuration.

- **`confirm`** — required enum, default empty; set exact uppercase `RESET` to execute. Clears after successful execution.

```text
use event/reset
set confirm RESET
show options
run
```

**Destructive:** removes roster, teams, scores, completions, assignments, waiting and prior audit history. Scheduling settings return to random mode, seed `2041`, draw zero and `min_main = min(3, reachable enabled main count)`. Embedded catalog, capacities and enabled states remain. A new reset audit entry begins the log. Make a separately named backup first.

\newpage

# 11 / Destructive actions: stop and back up

## Team regeneration is not an edit

If teams have activity, `teams/create` refuses to run without `confirm REGENERATE`. With that confirmation it erases **all teams'** scores, completions, active assignments and queue, then reforms teams. The roster and scheduling settings remain; existing audit history is retained and regeneration is logged. Without activity, teams can be reformed without the confirmation.

Example for deliberately restarting activity while retaining the roster:

```text
use teams/create
set size 3
set seed 42
set confirm REGENERATE
show options
run
```

This is not a way to add a late player: the roster remains frozen because teams exist. There is no nondestructive roster-edit, reassignment-cancel, undo or completion-correction command.

## Full event reset

`reset RESET` is the short form of the `event/reset` module. It additionally clears the roster and old audit history and resets scheduling settings; resource changes are retained. To restore the supplied original catalog/resource defaults, create a **new nonexistent state path** using the original catalog instead of assuming reset restores everything.

## One-generation backup is not an archive

Before overwriting an existing state, the previous valid bytes go to `<state>.bak`. Any next successful save or mutation replaces that backup, including an explicit `save`. Exit does not write, so it preserves the current `.bak`. After reset, the previous complete event is recoverable from `.bak` only until another successful write replaces it.

For important checkpoints, exit the only organizer process and copy the state to a separately named file outside the project before reopening it. Preserve both current state and `.bak` before any recovery attempt. A generic additional `save` is **not** the first step in recovery; it may destroy the backup you need.

\newpage

# 12 / Persistence, restart and safe recovery

## What survives a restart

Successful mutations fully validate, auto-save atomically through a same-directory temporary file, synchronize it and replace the JSON file. State size is limited to 8 MiB. Newly written state files use POSIX mode `0600`; parent-directory permissions remain your responsibility.

The file embeds its authoritative catalog, settings and random draw counter, roster, teams, chronological completions, derived scores, waiting list and audit. Editing the source `catalog.json` does **not** update an existing event. For an independently prepared custom catalog and a new state only:

```sh
python3 killswitch.py --state custom-event.json --catalog catalog.json
```

Custom catalogs must pass validation, including prerequisite and reachability checks. Existing states cannot be silently overridden with `--catalog`. Raw state edits during an event are unsupported; no migration facility is supplied.

## Recover without overwriting the original

1. Stop **all** organizer processes using the event. Do not run reset.
2. Copy both the damaged current file and its `.bak` to separately named files in a private recovery folder. Keep the originals untouched.
3. Make a further working copy of the backup. Launch against that copy, for example `python3 killswitch.py --state ../recovery/backup-check.json`. **Ensure this file exists** first: an absent path creates a new event rather than validating a backup.
4. If startup succeeds, inspect `status`, `leaderboard`, `show settings` and relevant `audit` records, then `exit` without mutations.
5. Only after validation, and with all processes stopped, replace the intended event file offline using the verified copy. Preserve the pre-recovery originals separately, then restart one organizer.

Malformed JSON/catalogs fail without silent overwrite. Failed `reload` keeps the current in-memory snapshot and leaves disk untouched. A stale-write error requires resolving who owns the current file, backing it up and deliberately reloading or restarting—not repeatedly trying to save an obsolete snapshot.

\newpage

# 13 / Troubleshooting and security boundaries

## Common problems

- **CSV rejected:** use the exact `id,name` header, UTF-8 encoding, two well-formed columns and nonempty valid IDs/names. Unicode names are supported. Duplicate IDs, including collisions with already imported players, reject the whole import; duplicate display names are allowed. Limits are 1 MiB CSV and 2000 total players.
- **File not found:** check the current project directory and spelling; quote paths with spaces. A missing parent directory or unwritable state location prevents saving.
- **Full queue / no free mission:** inspect `show challenges`, `show queue` and `eligible T001`. Verify completions first, release capacity through legitimate completion and run `queue/dispatch`. Increase capacity only when actual separately prepared resources allow it.
- **No eligible mission:** an active/finished team has no next assignment. Otherwise check prerequisites, enabled branches, previous completions and `min_main`. In controlled mode after the intro, choose an explicit eligible mission.
- **Wrong mission guard:** `progress/complete` retains `mission` while staying in the module. Clear it with `set mission ""` or set it to the actual active mission. Do not clear it merely to conceal a mistaken team selection.
- **Error after `run`:** inspect the message and `status`. Printed errors do not mutate event state. Interactive exit code `0` alone does not prove every command succeeded. Startup validation errors exit `2`; Ctrl-C outside a command exits `130`.
- **Invalid state:** use the copy-and-validate recovery process, never reset or overwrite the original to suppress an error.

## Single-organizer, local-only trust model

Use **one organizer process per state**. SHA-256 stale-writer detection catches sequential conflicting writes or deletion, but there is no interprocess lock and simultaneous writes can race. This is not a multi-user database. Tested persistence relies on local filesystem behavior.

There is no authentication, encryption or role enforcement. Organizer authority is an operational assumption. Anyone with terminal/filesystem access can modify records; the audit is plaintext, capped at 20000 entries and not tamper-proof. Keep state and backups private, obtain appropriate participant consent and apply a retention policy; names are personal data.

No network listeners/calls, shell execution, exploit execution, flag checking, automatic grading, infrastructure provisioning, timers, GUI, score export, external integrations, workshop selection or attack/defense management are implemented. Linux is the tested platform; `readline` completion and shell commands may need adjustment elsewhere.

\newpage

# 14 / Catalog reference and proposed defaults

These planning defaults are supplied by `catalog.json`, not numerical facts from the original brief. Every mission starts enabled. All twelve main branches require `warehouse`; `maze` also requires the configured main-completion threshold, default three.

| Mission ID | Role / difficulty | Points | Capacity |
|:--|:--|--:|--:|
| `warehouse` | Introductory | 100 | 2000 |
| `quadruped` | Main / intermediate | 200 | 1 |
| `humanoid` | Main / intermediate | 200 | 1 |
| `drones` | Main / intermediate | 200 | 1 |
| `medical` | Main / intermediate | 200 | 1 |
| `vehicle` | Main / intermediate | 200 | 1 |
| `industrial_arm` | Main / intermediate | 200 | 1 |
| `elevator` | Main / advanced | 300 | 1 |
| `plant` | Main / advanced | 300 | 1 |
| `cctv` | Main / intermediate | 200 | 1 |
| `cpu_rings` | Main / advanced | 300 | 1 |
| `blind_spot` | Main / intermediate | 200 | 1 |
| `through_walls` | Main / advanced | 300 | 1 |
| `maze` | Finale | 500 | 1 |

Default team size is three. Formation and assignment seeds each start at `2041`, independently; assignment mode starts `random`. Repeated assignments cannot score a mission twice. Scores are the sum of completed catalog missions, not speed bonuses; a team may earn more points by completing additional branches before the finale when eligible and available.

The catalog contains descriptions only: no actual flags, pcaps, datasets, firmware images, containers, vulnerable services or simulated process implementations. The tower and plant are separate stages. Negative CPU rings are narrative shorthand; Blind Spot is intermittent docking, not permanent air-gapping; Through the Walls uses synthetic CSI/RSSI, not live people tracking.

\newpage

# 15 / Tests, demonstrations and evidence

From the extracted `kill-switch-manager` folder:

```sh
python3 -m unittest discover -s tests -v
python3 examples/run_demo.py
```

Or run the bundled Linux reproduction entrypoint:

```sh
sh entrypoint.sh
```

The completed implementation's recorded test output is **30 tests, zero failures, OK**, in 4.001 seconds on Linux / Python 3.11.15. An independent extraction of the earlier runtime archive also reran **30/30** successfully (3.972 seconds). These are recorded observations, not a guarantee for an untested platform or a claim of comprehensive security certification.

Tests cover balanced/reproducible formation, Unicode/duplicate CSV handling, random/controlled allocation, intro and branch capacity, queues/retry, manual completion/scoring, duplicate prevention, finale gating, confirmations, save/reload/backup/stale writes, invalid inputs and real console subprocess walkthroughs. Test source is `tests/test_organizer.py`; evidence is under `artifacts/`.

## Replay the bundled inputs

Only use new nonexistent paths; redirection replays organizer assertions:

```sh
python3 killswitch.py --state replay-walkthrough.json < examples/walkthrough.txt
python3 killswitch.py --state replay-full-event.json < examples/full-event.txt
```

The first recorded run forms four teams, assigns distinct branches and later switches to controlled mode: final scores `T001=400`, others `100`; T001 is active on `quadruped`. Save/reload succeeds. The full-event input uses two one-player teams, warehouse capacity one, queue dispatch, controlled quadruped capacity one and a complete finale route. Its recorded final scores are **T001=1200, T002=300**, with no waiting entries.

`examples/run_demo.py` uses temporary state paths and regenerates only its designated demo artifacts; it never loads your event state. `artifacts/*-state.json` are generated fictional demo states, not fresh starters. `starter/event-state.json` is empty. The actual transcripts, interface reference and test output support this guide; no command or lab outcome is inferred from an imaginary session.

\newpage

# 16 / Recommendations: at-the-desk checklist

## Before the event

- Keep this guide separate from the player-facing challenge presentation.
- Prepare and test the actual challenge artifacts independently.
- Publish team, progression, scoring, scope and resource rules.
- Confirm Python, the private writable state location and a backup plan.
- Launch one organizer process with a deliberate state filename.
- Import the roster **before** forming teams; inspect the roster for correctness.
- Use random formation and random mission assignment as the default rules.

## During play

1. Use `status`, `show challenges` and `show queue` to understand the current state.
2. Verify the team's proof outside the tool before `progress/complete`.
3. Run `missions/assign` for idle teams or `queue/dispatch` for existing waiting teams.
4. Review `show options` before every destructive or controlled operation.
5. Never use reset or team regeneration as a quick correction to a live event.
6. Make separately named private checkpoint copies; `.bak` holds only one generation.

## Handover or close

Exit the only running process, preserve state and backup copies securely, and document which event filename is authoritative. Do not give players local access to organizer records. Resume with the same `--state` path when needed; a new filename means a separate event, not a continuation.

**References / documentation basis.** Verified against `killswitch.py`, relevant `engine.py` state-machine operations, `artifacts/interface-reference.json`, `catalog.json`, the actual walkthrough/full-event inputs and transcripts, the 30-test report and the implementation handoff. This guide documents the completed record-management implementation only; optional workshop and attack/defense ideas from the original brief are not implemented features.
