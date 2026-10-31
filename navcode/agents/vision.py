"""Bounded visual investigation with authorized frame retrieval and crops."""
import json
import math
from pathlib import Path
from uuid import uuid4

from PIL import Image

from navcode.agents.prompts import VISION_SYSTEM, VISION_FINAL_SYSTEM
from navcode.agents.protocol import parse_json

class VisionAgent:
    def __init__(self, api, frames, event, epoch, system=VISION_SYSTEM, final_system=VISION_FINAL_SYSTEM,
                 skills=None):
        self.api = api
        self.frames = frames
        self.event = event
        self.epoch = epoch
        self.reports = []
        self.system, self.final_system = system, final_system
        self.skills = skills

    def investigate(self, contract, task, recent_actions):
        if contract["episode_epoch"] != self.epoch:
            raise ValueError("cross-episode perception request")
        if self.skills is not None:
            self.skills.read("route-following", reason="entry")
            feedback = contract.get("local_motion_feedback", {}).get("status")
            if feedback in ("VISUALLY_STALLED", "PREVIOUSLY_STALLED", "DEPTH_BLOCKED_OR_UNKNOWN",
                            "NO_REAR_CLEARANCE", "REAR_DEPTH_BLOCKED", "RECOVERY_LIMIT"):
                self.skills.read("blocked-motion", reason="execution_feedback")
        # Model-visible aliases avoid copying long opaque epoch hashes. The
        # trusted mapping is local to this episode and every result is remapped.
        aliases = {f"f{i}": obs_id for i, obs_id in enumerate(self.frames)}
        inverse = {v: k for k, v in aliases.items()}
        available = list(aliases)
        current = contract["current_obs_id"]
        current_alias = inverse[current]
        seen = {current_alias}
        images = [self.frames[current]]
        image_ids = [current_alias]
        tools = []
        model_contract = dict(contract, current_obs_id=current_alias)
        if "route_memory" in contract:
            def alias_memory(value):
                if isinstance(value, dict):
                    return {k: alias_memory(v) for k, v in value.items()}
                if isinstance(value, list):
                    return [alias_memory(v) for v in value]
                return inverse.get(value, value) if isinstance(value, str) else value
            model_contract["route_memory"] = alias_memory(contract["route_memory"])
        start = contract.get("stage_start_obs_id")
        if start in inverse:
            model_contract["stage_start_obs_id"] = inverse[start]
            if start != current:
                images.append(self.frames[start])
                image_ids.append(inverse[start])
                seen.add(inverse[start])
        prior_reports = []
        for previous in self.reports[-1:]:
            item = {k: previous[k] for k in ("claim_id", "verdict", "evidence_obs_ids", "current_obs_id")}
            item["predicate"] = previous.get("predicate")
            item["evidence_obs_ids"] = [inverse[i] for i in previous["evidence_obs_ids"] if i in inverse]
            item["current_obs_id"] = inverse.get(previous["current_obs_id"])
            prior_reports.append(item)
        for turn in range(contract["max_visual_turns"]):
            context = {"contract": model_contract,
                       "task": {k: task[k] for k in ("instruction", "language") if k in task},
                       "authorized_history": available,
                       "image_ids_in_order": image_ids,
                       "recent_actions": recent_actions[-16:], "tool_history": tools,
                       "remaining_turns": contract["max_visual_turns"] - turn,
                       "previous_investigation": prior_reports}
            if self.skills is not None:
                context.update(self.skills.context())
            final_turn = turn + 1 == contract["max_visual_turns"]
            response = self.api.generate(self.final_system if final_turn else self.system,
                                         json.dumps(context), images, max_tokens=1000)
            try:
                result = parse_json(response["text"])
                if "tool" in result:
                    if turn + 1 == contract["max_visual_turns"]:
                        break
                    if result["tool"] == "read_skill" and self.skills is not None:
                        self.skills.read(result.get("name"))
                    elif result["tool"] == "recall":
                        ids = result.get("obs_ids", [])
                        if not isinstance(ids, list) or not ids or len(ids) > 2:
                            raise ValueError("recall requires 1..2 history IDs")
                        if any(i not in aliases for i in ids):
                            raise ValueError("unauthorized frame requested")
                        image_ids = list(dict.fromkeys([current_alias] + ids))
                        images = [self.frames[aliases[i]] for i in image_ids]
                        seen.update(image_ids)
                    elif result["tool"] == "crop":
                        obs_id, box = result.get("obs_id"), result.get("box")
                        if obs_id not in aliases or not isinstance(box, list) or len(box) != 4:
                            raise ValueError("invalid crop")
                        if not all(type(x) in (int, float) and math.isfinite(x) for x in box):
                            raise ValueError("invalid crop coordinates")
                        if not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1):
                            raise ValueError("invalid crop bounds")
                        with Image.open(self.frames[aliases[obs_id]]) as image:
                            w, h = image.size
                            crop = image.crop((int(box[0]*w), int(box[1]*h),
                                               max(int(box[0]*w)+1, int(box[2]*w)),
                                               max(int(box[1]*h)+1, int(box[3]*h))))
                            path = Path(self.frames[aliases[obs_id]]).parent / f"crop_{uuid4().hex}.png"
                            crop.save(path)
                        image_ids = [current_alias, obs_id]
                        images = [self.frames[current], path]
                        seen.add(obs_id)
                    else:
                        raise ValueError("unknown visual tool")
                    tools.append(result)
                    self.event("VISION_TOOL", result)
                    continue
                self.validate(result, seen)
            except (ValueError, TypeError, KeyError) as exc:
                feedback = {"tool_error": str(exc), "instruction": "Correct the schema or return UNKNOWN; no action occurred."}
                tools.append(feedback)
                self.event("VISION_TOOL_ERROR", feedback)
                continue
            result["evidence_obs_ids"] = [aliases[i] for i in result["evidence_obs_ids"]]
            result.update({k: contract[k] for k in (
                "request_id", "episode_epoch", "policy_revision", "current_obs_id")})
            result["claim_id"] = f"claim-{len(self.reports) + 1}"
            result["predicate"] = contract.get("predicate")
            result["model_id"] = self.api.model
            result["usage"] = response["usage"]
            result["investigation_turns"] = turn + 1
            retracted = result.get("retract_claim_ids", [])
            known_claims = {r["claim_id"] for r in self.reports}
            if not isinstance(retracted, list) or any(c not in known_claims for c in retracted):
                raise ValueError("cannot retract an unknown or cross-episode claim")
            self.reports.append(result)
            self.event("PERCEPTION_RESOLVED", result)
            for claim_id in retracted:
                self.event("CLAIM_RETRACTED", {"claim_id": claim_id, "by_claim": result["claim_id"],
                                               "evidence_obs_ids": result["evidence_obs_ids"],
                                               "reason": result["rationale_summary"]})
            return result
        result = {"verdict": "UNKNOWN", "evidence_obs_ids": [current],
                  "rationale_summary": "investigation tool budget exhausted",
                  "target_bearing_deg": None, "forward_clear": False,
                  "suggested_observation": "NONE",
                  **{k: contract[k] for k in ("request_id", "episode_epoch", "policy_revision", "current_obs_id")},
                  "claim_id": f"claim-{len(self.reports)+1}", "model_id": self.api.model}
        self.reports.append(result)
        self.event("PERCEPTION_RESOLVED", result)
        return result

    @staticmethod
    def validate(result, seen):
        if result.get("verdict") not in ("SUPPORTED", "REFUTED", "UNKNOWN", "NEED_MORE_VIEW"):
            raise ValueError("invalid perception verdict")
        ids = result.get("evidence_obs_ids")
        if not isinstance(ids, list) or not ids or any(i not in seen for i in ids):
            raise ValueError("evidence must reference actually inspected frames")
        if not isinstance(result.get("rationale_summary"), str):
            raise ValueError("missing evidence rationale")
        bearing = result.get("target_bearing_deg")
        if bearing is not None and (type(bearing) not in (float, int) or not math.isfinite(bearing) or abs(bearing) > 90):
            raise ValueError("invalid target bearing")
        if type(result.get("forward_clear")) is not bool:
            raise ValueError("forward_clear must be a boolean")
        if result.get("suggested_observation") not in ("LEFT", "RIGHT", "NONE"):
            raise ValueError("invalid suggested observation")
