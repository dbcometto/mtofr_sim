# Style Migration

What it takes to bring the existing code in line with `style.md`.  The code predates `style.md`, which was adopted on 2026-11-19 (see `notes.md`); until this migration is done, new and touched code follows `style.md` and untouched code may not.  Counts are from a grep audit on that date.



## Suggested Order

1. One package per pass (`database/`, `capability/`, `condition/`, `clock/`, `backseater/`, `world/`, `viz/`, `maps/`, then `world/anywhere/platforms/interface/`, `world/ground_plane/platforms/bicycle_ugv/`, then `main.py`, `missions.py`, `scripts/`, `tests/`), running the full suite after each.
2. Within a pass, keep comment/whitespace-only changes (separators, `NOTE`/`TODO`, units) in a separate diff from anything that changes names or behavior (constants, renames, loop rewrites), so each diff is easy to review.
3. Leave `assistant_prompt.py`'s system prompt text alone (user hand-edited); only its surrounding code is in scope.



## 1. Section Separators

The code uses a two-tier convention; `style.md` has four tiers with fixed trailing blank lines.  77 separators in 17 source files (incl. `main.py`) (most in `mission_editor/window.py` 11, `bicycle_ugv/frontseater.py` 11, `assistant_tools.py` 8, `viz/dashboard.py` 7, `interface/frontseater.py` 6), plus 2 test files.

| Today | Becomes | Blank lines after the section |
|---|---|---|
| `#==========# X #==========#` at file level | major: 3-line `#====...====#` (40 `=`) box with `# X` | 7 |
| `#=====# X #=====#` inside a class/function | semi-major: `#===============# X #===============#` | 5 |
| `#-----# X #-----#` (minor) | minor: `#----------# X #----------#` | 3 |
| a plain `# Step` comment opening a block of statements | substep (unchanged form) | 2 |

- A few file-level headers sit inside a class today (e.g. `interface/frontseater.py`'s `#==========# Window wiring #==========#`); map by position (inside a class -> semi-major), not by today's marker.
- Long sentence-style headers (`missions.py`, e.g. `split: independent per-platform loops, ...`) fit the major box; keep the explanation as a comment under it.
- Files with no sections today don't need them added unless they're long enough to benefit.



## 2. Comments

- **`NOTE`/`TODO` markers**: none exist yet.  Explanatory "why" comments recording design history (e.g. `mpc.py`'s `maxiter` rationale, `main.py`'s Windows spawn guard, `world.py`'s fault isolation) become `NOTE` comments; known gaps recorded only in `roadmap.md` (e.g. MPC worker has no timeout, `_check_binding_types` duplicating `find_binding_problems`) get a `TODO` at the code site.
- **Units and frames inline**: add where missing, chiefly `maps/ground_map.py` (pixels vs meters, world frame +y up vs image rows), `bicycle_ugv/` (m, m/s, rad), `clock/clock.py` (seconds, local vs peer frame), `missions.py` coordinates (m, world frame).
- **Commented-out code**: none found; keep it that way, or pair any future instance with a `NOTE`/`TODO`.
- **Comment, don't restate**: several long docstrings narrate history ("increment 2", "per CLAUDE.md's ..."); trim them to the current why and leave history to `notes.md`.



## 3. Magic Numbers and Config Sections

- Most module-level tunables are already `ALL_CAPS` constants (e.g. `LIVE_KNOWLEDGE_REFRESH_MS`, `EVENT_POLL_MS`, `UNDO_HISTORY_LIMIT`, `LAYOUT_ITERATIONS`, `agent/config.py`).  Gather each module's constants into a config section at the top.
- In-function numeric literals to lift into named constants, by rough count: `mission_editor/window.py` ~82, `missions.py` ~36 (mission coordinates and tolerances, which are data and can stay inline), `viz/dashboard.py` ~27, `viz/mission_graph_view.py` ~25, `assistant_window.py` ~18, `bicycle_ugv/mpc.py` ~8 (incl. `options={"maxiter": 20}`), plus a few each in `plane_plotter.py`, `ground_map.py`, `bicycle_ugv/frontseater.py`, `platform_overview_view.py`, `bicycle_ugv/hardware.py`, `clock/clock.py`.
- Tk padding/size literals (`padx=4`, `pady=6`, column widths) are the bulk: a few shared `PAD_*`/width constants per window cover most of them.



## 4. Other Rules

- **`continue`/`break`**: 10 in `src/` + `main.py` (`world.py` 2, `mission_graph_view.py` 2, one each in `backseater.py`, `agent.py`, `serialization.py`, `mpc.py`, `main.py`), plus `scripts/mpc_profile.py`.  Rewrite where a condition or helper reads as clearly; keep the rest.
- **Shadowed built-ins**: `KnowledgeDatabase.declare(self, key, type, ...)` (`database/knowledge.py`) shadows `type`; rename to `entry_type` (matching `Backseater.declare_knowledge_key`) and update callers.  Re-check locals during each pass.
- **Unused imports**: no linter is installed; check each file during its pass (or install `pyflakes` temporarily).
- **Argument/return ordering**: check related signatures share an order, e.g. `(key, value, timestamp, origin_platform_id)` across the three databases, and `(platform_id, ...)` first across platform-keyed helpers.
- **Docstrings**: every function needs at least one line; fill gaps found while passing through each file.
- **Names**: replace any cryptic or opaque names found (style rule 6); common short forms are fine.
