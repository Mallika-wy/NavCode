---
name: blocked-motion
description: Respond to stalled or refused movement using fresh observations and bounded alternatives.
---

# Classify the execution feedback

| Feedback | Interpretation | Useful next decision |
|---|---|---|
| PARTIAL or some forward_with_visual_change | The view changed during part of the batch; arrival remains unproven | Inspect the post-move scene and refresh the local target |
| VISUALLY_STALLED or PREVIOUSLY_STALLED | Forward commands produced no useful new view at the stuck part | Change the approach; consider one bounded backoff probe |
| DEPTH_BLOCKED_OR_UNKNOWN | The controller cannot support the next step | Investigate another view or visible entrance; keep the geometric guard |
| NO_REAR_CLEARANCE or unchanged recovery | Backoff did not create a usable new view | Stop repeating retreat and investigate a different visible direction |
| RECOVERY_LIMIT | The episode's backoff allowance is spent | Use an alternative route/view or yield a checkpoint for review |

Commanded distance and image change are not measured world displacement. No
controller status establishes that a semantic stage is complete.

## Break the repeated approach

Compare the current image, the intended passage and the recent attempted bearing.
If the model keeps selecting floor toward a wall or furniture, look toward the
actual opening before proposing another target. Changing W labels or observation
IDs without changing the approach does not resolve the physical problem.

If a desired room is visible through an obstacle, preserve it as a clue and seek a
visible entrance or near corner. Inspect that new view before deciding where to
move next. Do not invent an off-screen point or assume that the target is absent.

A recovery probe and a view scan serve different purposes. Use a short recovery
for physical contact when evidence supports it; use a turn for missing visual
information. After either, obtain fresh evidence. Check if the decision yielded
new information; after a repeated unchanged result, change the hypothesis or
preserve state for program review within the remaining budget.
