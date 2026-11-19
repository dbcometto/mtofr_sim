# Process

This document defines the operating process.

## Overall Flow

1. Receive the mission - ensure you have a clear understanding of the goal, constraints, and purpose.  Interview the user on any questions.
2. Plan - think big-picture about what needs to be done, then create a checklist of steps, and get it approved by the user.  Build a task list with the todo/task tool. Update it as each item starts and finishes, and don't batch updates at the end.
3. Execute - make changes in large diffs so the user can read and approve
4. Review - check the checklist, make sure everything is done
5. Test - if the user approves, write tests to verify success (default for this project: NO TESTS, ONLY DO IF SPECIFIED).
6. Document - keep `spec.md` updated with a current architecture overview, and `notes.md` updated with the design history, when needed.  Update `to_hardware.md` with a list of references to the simulator code of any changes made that need to be implemented in the hardware version.



## Specific Notes

- I will handle all git operations -- never ask to commit or push
- Be prepared to defend why the implementation is done the way it is -- keep it simple, easy to understand, but effective
- Prioritize short summaries in `notes.md`, and keep `spec.md` as concise as possible





