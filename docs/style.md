# STYLE

This document describes the desired code style.


## General Guidelines

1. Keep things as simple as possible
2. Write pythonic code
3. No magic numbers
4. Prioritize readability and understandability -- limit use of continue and break
5. Comment for 'why' and flow, not 'what'.  Add `NOTE` comments inline or by themselves if more information should be recorded.  Add `TODO` comments when something is left undone.  Comment units and frames inline.
6. Use full word variable names, except for specific math equations (`dt`, `vx`, `vtheta`).  Common short forms (`env`, `dist`) are fine; avoid cryptic or opaque names (e.g. `q` for quality)
7. Every function needs at least a one-line docstring
8. Keep defaults matched
9. Define all config values in a config section at the top of a script or in a yaml file
10. Everything should have a single source of truth
11. Place duplicated code in a function or method, when the uses depend on the same source of truth
12. snake_case for variables and functions, CamelCase for classes, ALL_CAPS for constants and enums
13. Type hint when it improves readability, and always on public method signatures and dataclass-like fields
14. Maintain consistent variable ordering for both arguments and returns
15. Don't shadow built-ins
16. Remove unused imports
17. Blocks of code can be commented out if needed, and must be paired with a `NOTE` or `TODO`
18. Tag debug prints by layer (`print(f"[Backseater] ...")`, `[Frontseater]`, `[World]`), each gated by that layer's own `debug: bool = False` constructor flag, so a caller (e.g. `main.py`'s `DEBUG`) opts in per layer



## Tests

- Stdlib `unittest` only (no pytest), one flat `tests/` directory.
- Rule 7 applies to tests too: every `test_*` method and helper gets a one-line docstring saying what it verifies.
- Any test that constructs a `Frontseater` owning a real OS-level resource (currently `BicycleFrontseater`'s MPC worker process and queues) must tear it down explicitly with `tearDown()` or `self.addCleanup(frontseater.shutdown)` (`platform.shutdown` for a `Platform`), never relying on garbage collection: the whole suite runs in one process, where GC-timed cleanup can crash the interpreter.  A helper that builds the stack per test takes the `TestCase` (`self`) and registers the cleanup itself.
- Tests that open Tk windows skip when no display is available (`TK_AVAILABLE` guard).



## Specific Descriptions

Split major sections as
```python
#========================================#
# SECTION NAME
#========================================#

this_is_code()
```
and end the section with 7 newlines.


Split semi-major sections as
```python
#===============# SECTION #===============#

this_is_code()
```
and end the section with 5 newlines.


Split minor sections as
```python
#----------# SECTION #----------#

this_is_code()
```
and end the section with 3 newlines.

Split substeps with
```python
# Substep
this_is_code()
```
and end the section with 2 newlines.


## Note Format

Make each note under `notes.md` according to the template below, filling in the <blanks> as needed.  Keep contents as concise as possible, utilizing bullet or numbered lists.  Make the title short and specific.  Start the indexing from 1.  New notes are added to the top with the next integer index.

```markdown
## <INDEX> - <YYYY-MM-DD>: <Short title>
- Any decisions made
- What changed and why (minimum lines possible)
```

