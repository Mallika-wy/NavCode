---
name: state-repair
description: Repair policy behavior while preserving an existing checkpoint and history.
---

# Resume an existing program

Start from the supplied checkpoint and current RGB. Identify the specific failed
assumption using execution and applied evidence. The robot has already performed
the recorded actions. Continue from its present observation.

## Migrate state explicitly

The checkpoint can be nonempty while lacking fields introduced by the revision.
Initialize each new field before any read, independently of `if not state`.
For example, use `state.setdefault("failed_handles", [])` at function entry.
Inspect nested stage fields too. Do not assume the new revision's initialization
branch will run on old state.

Retain existing stage IDs, their predicates, order, accepted claims and completed
entry-turn flags. Do not replace the route list as a shortcut for resetting it.
New helper fields need defaults; any migration of existing progress needs an
explicit reason supported by evidence. Checkpoint the migrated state before
navigation. Newly written defaults must not mark unfinished stages complete.

## Correct the failure

A missing key needs state migration. Repeated physical stalls need a changed
approach. A depth refusal needs another legal view or local target, not removal
of the depth guard. A viewpoint that cannot establish completion needs additional
evidence. Preserve the outer decision loop and avoid replaying earlier movement.

Check that left remains negative, right remains positive, and every stored target
is refreshed after motion. Use current `remaining_contracts` and action budget.
Return the state dictionary itself when asking the supervisor for further review.
