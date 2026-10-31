---
name: route-following
description: Choose local routes consistent with an ordered instruction and visible scene.
---

# Connect language, observations and local motion

Interpret the current clause in the context of the original route and preceding
supported stages. Maintain a working hypothesis for the intended passage and its
landmarks. A prior report is a hypothesis with a source frame; current evidence
and execution can contradict it.

## Select a route before a floor dot

Locate the relevant doorway, corridor, aisle or approach region in the current
image. Inspect which available candidate points head toward it. Yellow dots only
represent locally visible ground. A rug point in front of furniture is not a
route to a doorway at the edge of the image.

If the useful passage is outside the candidate headings, provide no target and
suggest turning toward the passage. Reassess from the new view. If no current
route is visible, choose an observation that can resolve the ambiguity rather
than repeatedly moving toward a nearby wall. Do not pretend that glass, a mirror
or a closed door is an entrance.

When a target is useful but the predicate remains unmet, return REFUTED with the
current candidate. Match its short W label to this image only. Candidate depth
and execution checks still apply; you cannot guarantee a reachable route.

## Keep a compact route account

Use route_memory, when supplied, to retain the latest supported stage, recently
considered passages and failed attempts. Bearings belong to their source views.
Do not assume a remembered left/right bearing remains valid after rotation.
Recall an earlier authorized frame only when it can resolve a concrete question.

R2R/RxR are route-following tasks: prioritize the specified sequence over unrelated
novel rooms. If a chosen passage is contradicted, reconsider a previously observed
route consistent with the instruction. Avoid an indefinite left/right scan cycle.
Read blocked-motion after repeated refusal or no visual progress. Read verification
when deciding whether a stage or the final destination is established.
