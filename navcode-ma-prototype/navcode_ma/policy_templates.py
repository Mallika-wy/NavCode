"""Fixed, reviewed Python fixtures returned by a *mock* Code Agent.

Real generated Python MUST NOT be executed by this demonstration runner.
"""
FIRST_POLICY = '''def run(nav, state, task):
    seen = state.setdefault("seen_doors", [])
    for attempt in range(9):
        obs = nav.observe()
        evidence = nav.perceive("VERIFY_TRANSITION", obs.obs_id)
        if evidence.status == "VERIFIED":
            if evidence.landmark_id not in seen:
                seen.append(evidence.landmark_id)
                nav.checkpoint("door_verified", state)
        if len(seen) >= 2:
            nav.step("TURN_LEFT")
            nav.step("FORWARD")
            final_obs = nav.observe()
            goal = nav.perceive("VERIFY_GOAL", final_obs.obs_id)
            if goal.status == "VERIFIED":
                nav.stop()
                return {"event": "TASK_DONE"}
            return {"event": "NEEDS_REPLAN", "reason": "goal_uncertain"}
        nav.step("FORWARD")
    return {"event": "NEEDS_REPLAN", "reason": "search_exhausted"}
'''

REPAIR_POLICY = '''def run(nav, state, task):
    for attempt in range(2):
        obs = nav.observe()
        goal = nav.perceive("VERIFY_GOAL", obs.obs_id)
        if goal.status == "VERIFIED":
            nav.stop()
            return {"event": "TASK_DONE"}
    return {"event": "NEEDS_REPLAN", "reason": "still_uncertain"}
'''
