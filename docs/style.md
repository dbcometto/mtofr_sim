# STYLE

This document describes the desired code style.


## General Guidelines

1. Keep things as simple as possible
2. Write pythonic code
3. No magic numbers
4. Prioritize readability and understandability -- limit use of continue and break
5. Comment for 'why' and flow, not 'what'.  Add `NOTE` comments inline or by themselves if more information should be recorded.  Add `TODO` comments when something is left undone.  Comment units and frames inline.
6. Use full word variable names, except for specific math equations
7. Every function needs at least a one-line docstring
8. Keep defaults matched
9. Define all config values in a config section at the top of a script or in a yaml file
10. Everything should have a single source of truth
11. Place duplicated code in a function or method, when the uses depend on the same source of truth
12. snake_case for variables and functions, CamelCase for classes, ALL_CAPS for constants and enums
13. Type hint when it improves readability
14. Maintain consistent variable ordering for both arguments and returns
15. Don't shadow built-ins
16. Remove unused imports
17. Blocks of code can be commented out if needed, and must be paired with a `NOTE` or `TODO`



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

