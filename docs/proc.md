# Process

This document defines the operating process.

## Overall Flow

1. Receive the mission - ensure you have a clear understanding of the goal, constraints, and purpose.  Interview the user on any questions, before planning and again whenever a decision comes up mid-implementation that the user hasn't already settled (naming, scope, library choices).  Don't guess on ambiguous or high-blast-radius decisions.
2. Plan - think big-picture about what needs to be done, then create a checklist of steps, and get it approved by the user.  Build a task list with the todo/task tool. Update it as each item starts and finishes, and don't batch updates at the end.
3. Execute - make changes in large diffs so the user can read and approve.  Use the Edit/Write tools rather than scripts, so every change shows up as a diff.
4. Review - check the checklist, make sure everything is done
5. Test - write tests (stdlib `unittest`, in `tests/`) whenever worthwhile, alongside the change rather than as a deferred phase.  Keep the existing suite passing.  Before handing back, run the full suite (`.venv\Scripts\python.exe -m unittest discover -s tests`) and smoke-test the actual behavior, not just "tests pass".  The user runs the slow real-model (Ollama) tests.
6. Document - keep `spec.md` updated with a current architecture overview, `notes.md` updated with the design history, and `roadmap.md` updated with the build order, open items, and known issues, when needed.
7. Stop - wait for feedback at the end of a batch of changes rather than continuing on to unrequested follow-on work.



## Specific Notes

- I will handle all git operations -- never ask to commit or push, never use git tools, and never add or commit files
- Be prepared to defend why the implementation is done the way it is -- keep it simple, easy to understand, but effective
- Prioritize short summaries in `notes.md`, and keep `spec.md` as concise as possible
- The mission-editor assistant's system prompt (`assistant_prompt.py`) is hand-edited by the user: don't rewrite it unasked, and don't write tests that assert its wording
