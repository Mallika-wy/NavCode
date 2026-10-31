"""Mock Vision Agent: bounded visual investigation + explicit evidence provenance."""
from .contracts import PerceptionResult, PerceptionTask
from .memory import EpisodeMemory


class MockVisionAgent:
    def __init__(self, fail_goal_once: bool = False):
        self.calls = 0
        self.fail_goal_once = fail_goal_once

    def investigate(self, task: PerceptionTask, memory: EpisodeMemory) -> PerceptionResult:
        self.calls += 1
        # Can recall old frames on demand; three recent images are NOT a memory limit.
        recalled = memory.recall("door", limit=5)
        memory.append("VISION_RECALL", {
            "request_id": task.request_id,
            "recalled_obs_ids": [x["obs_id"] for x in recalled],
        })
        obs = memory.frame(task.current_obs_id)
        evidence = tuple(dict.fromkeys([*task.history_obs_ids, obs.obs_id]))
        if task.kind == "VERIFY_TRANSITION":
            for door_id in ("door_a", "door_b"):
                if f"{door_id} crossed" in obs.visual_hint:
                    claim_id = f"crossed:{door_id}"
                    current = memory.latest_claim(claim_id)
                    if current is None or current.verdict != "SUPPORTED":
                        memory.propose_claim(claim_id, f"Passed {door_id}",
                                             "SUPPORTED", evidence)
                    return PerceptionResult(task.request_id, "VERIFIED", door_id,
                                            evidence, "Visual threshold transition in mock fixture")
            return PerceptionResult(task.request_id, "NOT_FOUND", None, evidence,
                                    "No supported threshold transition in provided mock frame")
        if task.kind == "VERIFY_GOAL":
            if self.fail_goal_once:
                self.fail_goal_once = False
                return PerceptionResult(task.request_id, "UNCERTAIN", None, evidence,
                                        "Synthetic ambiguous visual evidence: ask again")
            if "inside the intended room" in obs.visual_hint:
                memory.propose_claim("inside_goal_room", "Goal room visually identified",
                                     "SUPPORTED", evidence)
                return PerceptionResult(task.request_id, "VERIFIED", "goal_room", evidence,
                                        "Synthetic goal room visual evidence")
            return PerceptionResult(task.request_id, "NOT_FOUND", None, evidence,
                                    "Goal room not identified")
        return PerceptionResult(task.request_id, "UNCERTAIN", None, evidence,
                                "Unsupported visual question in mock backend")
