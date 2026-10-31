"""RGB-D two-agent experiment with sensor-derived targets and transition gates."""
from __future__ import annotations

import argparse
import json
import math
import time
from uuid import uuid4

import numpy as np
from PIL import Image

from navcode.agents import CodeAgent, VisionAgent
from navcode.agents.prompts import GROUNDED_CODE_SYSTEM, GROUNDED_VISION_SYSTEM, GROUNDED_VISION_FINAL
from navcode.agents.prompts import SKILL_CODE_SYSTEM, SKILL_VISION_SYSTEM, SKILL_VISION_FINAL
from navcode.evidence.gates import transition_gate, check_stage_order
from navcode.artifacts.initial_policy import load_initial_artifact
from navcode.control.rgbd import DepthController, annotate_candidates, calibration, ground_candidates
from navcode.runners.development import DevelopmentRun
from navcode.models.api import ModelAPI
from navcode.control.route_grounding import ROUTE_GROUNDING_GUIDANCE, ground_route_intent
from navcode.skills.registry import SkillRegistry


class GroundedRun(DevelopmentRun):
    def __init__(self, suite, episode_id, model, output, split="train", code_model="deepseek-v4.1-flash",
                 max_contracts=24, max_vision_calls=32, initial_policy_run=None, recovery_enabled=True,
                 route_grounding=False, route_memory=False, skills_enabled=False):
        super().__init__(suite, episode_id, model, output, split, code_model, rgbd=True,
                         max_contracts=max_contracts, max_vision_calls=max_vision_calls,
                         action_budget=240, wall_budget=600)
        self.params = calibration(self.episode.config)
        self.recording_episode_id = episode_id
        self.initial_policy_run = initial_policy_run
        self.recovery_enabled = recovery_enabled
        self.route_grounding = route_grounding
        self.route_memory = route_memory
        self.skills_enabled = skills_enabled
        provenance = json.loads((self.output/"provenance.json").read_text())
        provenance.update(recovery_enabled=recovery_enabled, route_grounding=route_grounding,
                          route_memory=route_memory, skills_enabled=skills_enabled,
                          max_code_calls=4 if skills_enabled else 2,
                          controller_calibration=self.params)
        (self.output/"provenance.json").write_text(json.dumps(provenance, indent=2))
        self.in_recovery = False
        self.recovery_forward_seqs = set()
        self.last_local_motion = {}
        self.views = {}
        self.stages = {}
        self.accepted_stages = {}
        self.applied_reports = []
        self.visual_changed_forwards = []
        self.obs = None
        self.catalog = []
        self.blocked_streak = 0
        self.repair_triggered_revisions = set()
        self.look_counter = 0
        self.last_perception_key = None
        self.idle_perceptions = 0
        self.controller = DepthController(self.params, self.episode.config.SIMULATOR.TURN_ANGLE,
                                          self.episode.config.SIMULATOR.FORWARD_STEP_SIZE,
                                          self.snapshot, self.commit, self.event)

    def public_capabilities(self):
        return dict(super().public_capabilities(), controller="sensor_only_depth_guard_v5",
                    recovery_enabled=self.recovery_enabled, route_grounding=self.route_grounding,
                    route_memory=self.route_memory,
                    skills_enabled=self.skills_enabled,
                    policy_step_actions=["STOP", "TURN_LEFT", "TURN_RIGHT"],
                    max_contracts=self.max_contracts, action_budget=self.action_budget)

    def create_code_agent(self):
        recorded = None
        if self.initial_policy_run:
            recorded = load_initial_artifact(self.initial_policy_run, self.task,
                                              self.frames[self.current_obs], self.suite, self.code_model,
                                              self.split, self.recording_episode_id)
            (self.output/"initial_policy_origin.json").write_text(json.dumps(
                {k:v for k,v in recorded.items() if k not in ("source", "rationale")}, indent=2))
        skills = SkillRegistry(self.output/"implementation/skills", "code", self.event) if self.skills_enabled else None
        return CodeAgent(ModelAPI(self.code_model, self.output / "code_calls.jsonl", max_calls=4 if self.skills_enabled else 2,
                                  timeout=150, json_output=self.code_model.startswith("qwen3.8-max")),
                         self.output, system=SKILL_CODE_SYSTEM if self.skills_enabled else GROUNDED_CODE_SYSTEM,
                         image_provider=lambda: [self.frames[self.current_obs]], include_initial_image=True,
                         recorded_initial=recorded, skills=skills)

    def create_vision_agent(self):
        skills = SkillRegistry(self.output/"implementation/skills", "vision", self.event) if self.skills_enabled else None
        return VisionAgent(ModelAPI(self.model, self.output / "vision_calls.jsonl", max_calls=self.max_vision_calls,
                                     json_output=self.model.startswith("qwen3.8-max")),
                           self.views, self.event, self.episode.epoch,
                           system=(SKILL_VISION_SYSTEM if self.skills_enabled else GROUNDED_VISION_SYSTEM) + (ROUTE_GROUNDING_GUIDANCE if self.route_grounding else ""),
                           final_system=(SKILL_VISION_FINAL if self.skills_enabled else GROUNDED_VISION_FINAL) + (ROUTE_GROUNDING_GUIDANCE if self.route_grounding else ""),
                           skills=skills)

    def code_evidence(self):
        return self.applied_reports

    def frame(self, obs, seq):
        previous = self.obs
        super().frame(obs, seq)
        self.obs = obs
        if previous is not None and self.actions[-1]["action"] == "MOVE_FORWARD":
            change = float(np.mean(np.abs(obs["rgb"].astype(float)-previous["rgb"].astype(float))))
            self.visual_changed_forwards.append({"action_seq": seq, "image_change": change,
                                                  "purpose": "recovery" if self.in_recovery else "route"})
        np.save(self.output / f"depth_{seq:04}.npy", obs["depth"])
        self.catalog, rays = ground_candidates(obs["depth"], self.params,
                                               self.episode.config.SIMULATOR.TURN_ANGLE, self.current_obs)
        view_path = self.output / f"candidates_{seq:04}.png"
        annotate_candidates(Image.fromarray(obs["rgb"]), self.catalog).save(view_path)
        self.views[self.current_obs] = view_path
        self.event("GROUND_CANDIDATES", {"obs_id": self.current_obs, "candidates": self.catalog, "rays": rays})

    def snapshot(self):
        return {"obs_id": self.current_obs, "rgb": self.obs["rgb"], "depth": self.obs["depth"],
                "candidates": self.catalog}

    def commit(self, op_id, action):
        receipt = super().handle("step", {"op_id": op_id, "action": action})
        if self.in_recovery and action == "MOVE_FORWARD":
            self.recovery_forward_seqs.add(receipt["action_seq"])
        return receipt

    def handle(self, method, params):
        if method == "observe":
            return dict(super().handle(method, params), candidates=self.catalog,
                        remaining_contracts=max(0, self.max_contracts-self.contracts))
        if method == "move_to_candidate":
            chosen = next((c for c in self.catalog if c["candidate_id"] == params.get("candidate_id")), None) if self.route_memory else None
            result = self.controller.move(params.get("candidate_id"), params.get("obs_id"), params.get("max_steps", 4))
            no_progress = (result["forward_with_visual_change"] == 0 if "forward_with_visual_change" in result
                           else result["nominal_commanded_advance_m"] == 0 or result["status"] in ("VISUALLY_STALLED", "PREVIOUSLY_STALLED"))
            self.blocked_streak = self.blocked_streak + 1 if no_progress else 0
            self.last_local_motion = dict(result)
            if chosen:
                self.last_local_motion["attempted_bearing_deg"] = chosen["bearing_deg"]
            return result
        if method == "recover":
            if not self.recovery_enabled:
                return {"status": "UNSUPPORTED", "view_changed": False, "purpose": "collision_recovery"}
            self.in_recovery = True
            try:
                result = self.controller.recover()
            finally:
                self.in_recovery = False
            self.blocked_streak = 0 if result["view_changed"] else self.blocked_streak + 1
            self.last_local_motion = result
            return result
        if method == "turn":
            degrees = params.get("degrees")
            if type(degrees) not in (int, float) or not math.isfinite(degrees) or abs(degrees) > 90:
                raise ValueError("relative turn must be finite and within [-90,90]")
            step_angle = self.episode.config.SIMULATOR.TURN_ANGLE
            count = int(math.floor(abs(degrees)/step_angle + .5))
            self.look_counter += 1
            for i in range(count):
                self.commit(f"look-{self.look_counter}-{i}", "TURN_RIGHT" if degrees > 0 else "TURN_LEFT")
            return {"degrees_committed": (1 if degrees >= 0 else -1)*count*step_angle,
                    "final_obs_id": self.current_obs}
        if method == "step":
            if params.get("action") == "MOVE_FORWARD":
                raise ValueError("RGB-D forward motion requires a current ground target and depth controller")
            if params.get("action") not in ("STOP", "TURN_LEFT", "TURN_RIGHT"):
                raise ValueError("level-camera depth controller does not admit tilt or other policy step actions")
            if params.get("action") == "STOP":
                latest = self.applied_reports[-1] if self.applied_reports else {}
                if (latest.get("verdict") != "SUPPORTED" or latest.get("predicate_type") != "SPATIAL"
                        or latest.get("current_obs_id") != self.current_obs):
                    raise ValueError("STOP requires current supported SPATIAL goal evidence")
            return super().handle(method, params)
        if method != "perceive":
            return super().handle(method, params)
        if time.monotonic()-self.started > self.wall_budget:
            raise TimeoutError("episode wall budget exhausted")
        if self.episode.ended or self.contracts >= self.max_contracts:
            raise RuntimeError("perception budget exhausted or episode ended")
        request = params.get("contract")
        if not isinstance(request, dict):
            raise ValueError("missing perception contract")
        for field in ("stage_id", "task_span", "predicate"):
            if not isinstance(request.get(field), str) or not request[field] or len(request[field]) > 4000:
                raise ValueError("invalid " + field)
        kind = request.get("predicate_type")
        if kind not in ("TRANSITION", "SPATIAL", "VISIBLE"):
            raise ValueError("predicate_type must be TRANSITION, SPATIAL or VISIBLE")
        check_stage_order(request["stage_id"], self.stages, self.accepted_stages)
        key = (request["stage_id"], self.current_obs)
        self.idle_perceptions = self.idle_perceptions + 1 if key == self.last_perception_key else 1
        self.last_perception_key = key
        if (self.blocked_streak >= 2 or self.idle_perceptions >= 4) and self.coder.revision not in self.repair_triggered_revisions:
            self.repair_triggered_revisions.add(self.coder.revision)
            reason = ("same stage and observation requested four times without an action"
                      if self.idle_perceptions >= 4 else "two local targets committed no forward motion")
            self.blocked_streak = 0
            self.idle_perceptions = 0
            self.last_perception_key = None
            self.event("NO_PROGRESS_REPAIR_REQUESTED", {"stage_id": request["stage_id"],
                                                       "reason": reason})
            raise RuntimeError("NEEDS_REPLAN: " + reason + "; inspect current RGB and revise failed-target bookkeeping/view/route logic; keep completed stages and actual position")
        stage = self.stages.setdefault(request["stage_id"], {"obs_id": self.current_obs,
                                                             "action_seq": self.episode.broker.sequence})
        recent = [a for a in self.actions if a["action_seq"] > stage["action_seq"]]
        self.contracts += 1
        contract = {"request_id": uuid4().hex, "episode_epoch": self.episode.epoch,
                    "policy_revision": self.coder.revision, "operation_id": f"perceive-{self.contracts}",
                    "current_obs_id": self.current_obs, "stage_start_obs_id": stage["obs_id"],
                    "stage_id": request["stage_id"], "predicate": request["predicate"],
                    "predicate_type": kind,
                    "task_span": request["task_span"] if request["task_span"] in self.task["instruction"] else self.task["instruction"],
                    "candidates": [dict({k: v for k, v in c.items() if k not in ("obs_id", "candidate_id")},
                                        candidate_id=c["label"]) for c in self.catalog],
                    "local_motion_feedback": {k:v for k,v in self.last_local_motion.items() if k in (
                        "status", "purpose", "nominal_commanded_advance_m", "view_changed")},
                    "motion_since_stage": {"forward_commands": sum(a["action"] == "MOVE_FORWARD" and a["action_seq"] not in self.recovery_forward_seqs for a in recent),
                                           "forward_with_visual_change": sum(a["action_seq"] > stage["action_seq"] and a["image_change"] >= .2 and a.get("purpose") != "recovery"
                                                                             for a in self.visual_changed_forwards)},
                    "allowed_tools": ["recall", "crop"], "max_visual_turns": min(2, self.max_vision_calls-self.vision.api.calls_used),
                    "max_images": 3, "deadline_ms": 130000, "on_unknown": "REQUEST_VIEW"}
        if contract["max_visual_turns"] <= 0:
            raise RuntimeError("visual call budget exhausted")
        if self.route_memory:
            contract["route_memory"] = self.build_route_memory()
        if self.skills_enabled:
            contract["allowed_tools"].append("read_skill")
        self.event("PERCEPTION_REQUESTED", contract)
        report = self.vision.investigate(contract, self.task, self.actions)
        if any(report[k] != contract[k] for k in ("episode_epoch", "policy_revision", "request_id", "current_obs_id")):
            raise ValueError("stale visual evidence")
        applied, rejected = transition_gate(report, contract)
        if self.route_grounding:
            applied = ground_route_intent(applied, self.catalog, self.params["hfov_deg"],
                                          self.episode.config.SIMULATOR.TURN_ANGLE)
            self.event("ROUTE_INTENT_GROUNDED", {k: applied.get(k) for k in (
                "claim_id", "current_obs_id", "route_anchor", "route_anchor_bearing_deg",
                "target_candidate_id", "route_grounding_status", "suggested_observation")})
        applied = dict(applied, predicate_type=kind, stage_id=request["stage_id"])
        label_to_handle = {c["label"]: c["candidate_id"] for c in self.catalog}
        applied["target_label"] = applied.get("target_candidate_id")
        applied["target_candidate_id"] = label_to_handle.get(applied.get("target_candidate_id"))
        if rejected:
            self.event("TRANSITION_EVIDENCE_REJECTED" if kind == "TRANSITION" else "CURRENT_EVIDENCE_REJECTED",
                       {"claim_id": report["claim_id"], "reason": rejected})
        self.applied_reports.append(applied)
        self.event("EVIDENCE_APPLIED", applied)
        if applied["verdict"] == "SUPPORTED":
            self.accepted_stages[request["stage_id"]] = applied["claim_id"]
        if report.get("retract_claim_ids"):
            for stage_id, claim_id in list(self.accepted_stages.items()):
                if claim_id in report["retract_claim_ids"]:
                    del self.accepted_stages[stage_id]
            raise RuntimeError("Evidence contradiction requires program review: " + json.dumps(report))
        return applied

    def build_route_memory(self):
        """Bounded, fallible records from this episode; no evaluator state."""
        def summary(report):
            item = {k: report.get(k) for k in (
                "claim_id", "stage_id", "predicate", "predicate_type", "verdict",
                "current_obs_id", "evidence_obs_ids", "route_anchor",
                "route_grounding_status", "suggested_observation", "retract_claim_ids")}
            item["rationale_summary"] = report.get("rationale_summary", "")[:450]
            item["epistemic_status"] = "fallible_model_report_after_runtime_checks"
            item["active_stage_support"] = report.get("claim_id") in accepted
            return item
        accepted = set(self.accepted_stages.values())
        return {"accepted_stage_evidence": [summary(r) for r in self.applied_reports if r.get("claim_id") in accepted][-4:],
                "recent_investigations": [summary(r) for r in self.applied_reports[-4:]],
                "latest_execution": {k: v for k, v in self.last_local_motion.items() if k in (
                    "source_obs_id", "final_obs_id", "status", "purpose", "attempted_bearing_deg",
                    "forward_with_visual_change", "nominal_commanded_advance_m", "view_changed")},
                "guidance": "Reports are fallible. Recheck hypotheses against current images and execution. Bearings refer to the source view, not the current heading. Do not retry a blocked approach without a changed view or route. Completed stages are supported claims, not ground truth."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=["r2r", "rxr"], default="r2r")
    parser.add_argument("--episode-id", default="1")
    parser.add_argument("--split", choices=["train", "val_seen"], default="train")
    parser.add_argument("--model", default="qwen3.8-omni-flash")
    parser.add_argument("--code-model", default="deepseek-v4.1-flash")
    parser.add_argument("--max-contracts", type=int, default=24)
    parser.add_argument("--max-vision-calls", type=int, default=32)
    parser.add_argument("--output", required=True)
    parser.add_argument("--initial-policy-run")
    parser.add_argument("--no-recovery", action="store_true")
    parser.add_argument("--route-grounding", action="store_true")
    parser.add_argument("--route-memory", action="store_true")
    parser.add_argument("--skills", action="store_true")
    args = parser.parse_args()
    GroundedRun(args.suite, args.episode_id, args.model, args.output, args.split, args.code_model,
                args.max_contracts, args.max_vision_calls, args.initial_policy_run, not args.no_recovery,
                args.route_grounding, args.route_memory, args.skills).run()


if __name__ == "__main__":
    main()
