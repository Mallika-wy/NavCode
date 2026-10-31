---
name: policy-writing
description: Compile a durable NavCode RGB-D policy with explicit evidence and state.
---

# Policy contract

Generate concise Python `run(nav, state)`. Keep ordinary decisions in one loop
that directly calls `nav.perceive`. Preserve state with `nav.checkpoint(state)`.
Returning state without STOP asks the supervisor to review the unfinished task.

## Tools and signs

- `nav.observe()` supplies obs_id, epoch, action_seq, remaining_actions,
  remaining_contracts, turn_angle_deg and current candidates.
- `nav.perceive({stage_id, task_span, predicate, predicate_type})` returns a
  fallible evidence report with verdict, claim_id, current_obs_id,
  target_candidate_id and suggested_observation. Use an exact instruction span.
- `nav.move_to_candidate(handle, obs_id, max_steps=4)` attempts a bounded local
  move, with new depth checks after each primitive. Read its status and
  forward_with_visual_change. Nominal distance is a request, not measured travel.
- `nav.turn(degrees)` accepts [-90,90]. NEGATIVE is LEFT; POSITIVE is RIGHT.
  An instruction-directed 180-degree turn uses two 90-degree calls. Quantization
  follows the track. Refresh observation and targets after turning.
- `nav.recover()` is a local backoff probe, limited to two calls per episode.
  It restores the original commanded heading. Inspect again afterward.
- `nav.step("STOP", unique_op_id)` requires supported current final SPATIAL
  evidence. Other permitted primitive steps are turns; forward requires a target.

For an observation request, use a left turn for LEFT and a right turn for RIGHT.
Do not reverse these signs. Check the observation again after every local action.

## State and route

Derive a short ordered route with observable stage conditions. Do not turn on
episode entry when a turn is conditional on reaching a later landing or landmark.
Use VISIBLE for a visual prerequisite, SPATIAL for being inside/beside a place,
and TRANSITION for crossing/passing. End with a SPATIAL destination condition.
Advance only on supported evidence and retain its claim ID. Exhausted retries do
not complete stages. Persist stage IDs, order, counters and entry-turn flags.

Store a failed full observation-bound handle; W1 alone changes meaning in later
views. A repeated failure should change the approach or view, not just acquire a
fresh handle for the same failed direction. Consult blocked-motion when needed.
Read verification for uncertain crossing or arrival. Use state-repair when
continuing a checkpoint. Respect remaining budgets; preserve unfinished state
when a further decision would exceed them.
