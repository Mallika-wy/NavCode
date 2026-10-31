---
name: verification
description: Check stage crossing and final placement with explicit visual evidence.
---

# Verify the requested condition

For VISIBLE, establish whether the requested landmark is visible now. For SPATIAL,
establish the robot's current relation to the landmark or room. A sofa across a
room can be visible while the robot is not beside it.

For TRANSITION, compare distinct stage-start and current images, alongside actual
forward commands with visual change. Identify the relevant opening or landmark
in both views and explain which spatial relation changed. A rotation, a requested
move, or an unrelated advance cannot by itself show that a doorway was crossed.

Current-position predicates need current-image evidence. Skill text and earlier
reports do not count as images. If the required relation is unresolved, return
UNKNOWN or REFUTED with a useful target/view suggestion. A necessary-condition
runtime check passing does not independently verify the semantic claim.

Before final completion, check the destination clause and requested orientation
or neighboring features in the original instruction. Use the actual VLN-CE stop
contract rather than adopting another benchmark's distance or mandatory contact
procedure. No goal-distance oracle is provided. If fresh images disprove an old
claim, explicitly identify that claim for withdrawal and explain the evidence.
