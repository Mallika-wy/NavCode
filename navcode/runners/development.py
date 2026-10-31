"""Bounded development runner: real generated policy + independent vision agent.

Never use single-episode development results as an unseen benchmark score.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from uuid import uuid4

from PIL import Image

from navcode.agents import CodeAgent, VisionAgent
from navcode.benchmark import BenchmarkEpisode, make_config
from navcode.models.api import ModelAPI, ModelAPIError
from navcode.runtime.sandbox import PolicyRuntime
from navcode.artifacts.provenance import archive_package_sources


class DevelopmentRun:
    def __init__(self, suite, episode_id, model, output, split="train", code_model="deepseek-v4.1-flash",
                 rgbd=False, max_contracts=12, max_vision_calls=16, action_budget=120, wall_budget=420):
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=False)
        self.suite, self.split = suite, split
        self.episode = BenchmarkEpisode(make_config(suite, split, rgbd=rgbd, episode_ids=[episode_id]), rgbd=rgbd)
        self.max_contracts, self.max_vision_calls = max_contracts, max_vision_calls
        self.action_budget, self.wall_budget = action_budget, wall_budget
        self.events = []
        self.frames = {}
        self.state = {}
        self.actions = []
        self.current_obs = None
        self.contracts = 0
        self.started = time.monotonic()
        self.model = model
        self.code_model = code_model
        archive = self.output / "implementation"
        archive.mkdir()
        sources = archive_package_sources(archive)
        (self.output / "provenance.json").write_text(json.dumps({
            "implementation_sha256": sources, "suite": suite, "split": split,
            "episode_id": str(episode_id), "vision_model": model, "code_model": code_model,
            "rgbd": rgbd, "max_contracts": max_contracts, "max_vision_calls": max_vision_calls,
            "action_budget": action_budget, "wall_budget": wall_budget}, indent=2))

    def event(self, kind, payload):
        record = {"event_seq": len(self.events), "kind": kind, "payload": payload,
                  "elapsed_s": time.monotonic() - self.started}
        self.events.append(record)
        with (self.output / "trace.jsonl").open("a") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")

    def public_capabilities(self):
        caps = self.episode.capabilities()
        return {k: caps[k] for k in ("actions", "forward_step_m", "turn_angle_deg", "sensor_track")}

    def create_code_agent(self):
        return CodeAgent(ModelAPI(self.code_model, self.output / "code_calls.jsonl", max_calls=2,
                                  timeout=150), self.output)

    def create_vision_agent(self):
        return VisionAgent(ModelAPI(self.model, self.output / "vision_calls.jsonl", max_calls=self.max_vision_calls),
                           self.frames, self.event, self.episode.epoch)

    def code_evidence(self):
        return self.vision.reports

    def frame(self, obs, seq):
        obs_id = f"{self.episode.epoch}:{seq}"
        path = self.output / f"frame_{seq:04}.png"
        Image.fromarray(obs["rgb"]).save(path)
        self.frames[obs_id] = path
        self.current_obs = obs_id
        self.event("OBSERVATION", {"obs_id": obs_id, "path": str(path), "sensor": "RGB"})

    def handle(self, method, params):
        if time.monotonic() - self.started > self.wall_budget:
            raise TimeoutError("episode wall-time budget exhausted")
        if method == "observe":
            return {"obs_id": self.current_obs, "epoch": self.episode.epoch,
                    "action_seq": self.episode.broker.sequence,
                    "remaining_actions": max(0, self.action_budget - self.episode.broker.sequence),
                    "turn_angle_deg": self.episode.config.SIMULATOR.TURN_ANGLE}
        if method == "checkpoint":
            state = params.get("state")
            if not isinstance(state, dict) or len(json.dumps(state, allow_nan=False)) > 16000:
                raise ValueError("invalid checkpoint")
            self.state = state
            self.event("CHECKPOINT", state)
            return {"saved": True}
        if method == "step":
            if self.episode.broker.sequence >= self.action_budget:
                raise RuntimeError("development action budget exhausted")
            old_seq = self.episode.broker.sequence
            receipt, obs = self.episode.step(params.get("op_id"), params.get("action"))
            if receipt["action_seq"] > old_seq:
                self.actions.append(receipt)
                self.event("ACTION_COMMITTED", receipt)
                self.frame(obs, receipt["action_seq"])
            return receipt
        if method == "perceive":
            if self.episode.ended or self.contracts >= self.max_contracts:
                raise RuntimeError("perception budget exhausted or episode ended")
            request = params.get("contract")
            if not isinstance(request, dict):
                raise ValueError("perception requires a contract")
            for field in ("stage_id", "task_span", "predicate"):
                if not isinstance(request.get(field), str) or not request[field] or len(request[field]) > 4000:
                    raise ValueError("invalid contract " + field)
            self.contracts += 1
            contract = {"request_id": uuid4().hex, "episode_epoch": self.episode.epoch,
                        "policy_revision": self.coder.revision, "operation_id": f"perceive-{self.contracts}",
                        "current_obs_id": self.current_obs,
                        "stage_id": request["stage_id"],
                        "task_span": (request["task_span"] if request["task_span"] in self.task["instruction"]
                                      else self.task["instruction"]),
                        "predicate": request["predicate"], "target_ref": None,
                        "evidence_before": [r["claim_id"] for r in self.vision.reports[-3:]],
                        "allowed_tools": ["recall", "crop"], "max_visual_turns": 2,
                        "max_images": 3, "deadline_ms": 130000,
                        "on_unknown": "REQUEST_VIEW"}
            self.event("PERCEPTION_REQUESTED", contract)
            result = self.vision.investigate(contract, self.task, self.actions)
            # Runtime is synchronous; still fail closed on stale returned evidence.
            if any(result[k] != contract[k] for k in (
                "episode_epoch", "policy_revision", "request_id", "current_obs_id")):
                raise ValueError("stale perception response")
            if result.get("retract_claim_ids"):
                raise RuntimeError("Evidence contradiction requires checkpoint review: " + json.dumps(result))
            return result
        raise ValueError("unsupported capability")

    def run(self):
        outcome = "INFRA_FAILURE"
        error = None
        forced_stop = False
        try:
            self.task, obs = self.episode.reset()
            self.frame(obs, 0)
            self.event("EPISODE_START", self.task)
            # Never send resolved config: Habitat mutates it to include initial
            # pose/scene. Explicitly selected public motion parameters only.
            public_caps = self.public_capabilities()
            self.coder = self.create_code_agent()
            self.vision = self.create_vision_agent()
            failure = None
            for _ in range(2):
                try:
                    source = self.coder.compile(self.task, public_caps, self.state, self.code_evidence(), failure)
                    self.event("POLICY_SUBMITTED", {"revision": self.coder.revision, "source": source,
                                                    "source_origin": self.coder.submission_origin})
                    self.state = PolicyRuntime(timeout=self.wall_budget).run(source, self.state, self.handle)
                    self.event("POLICY_RETURNED", self.state)
                    if self.episode.ended:
                        outcome = "AGENT_STOP" if self.actions[-1]["action"] == "STOP" else "ENV_TIMEOUT"
                        break
                    failure = "Policy returned without STOP: " + json.dumps(self.state)
                except Exception as exc:
                    failure = f"{type(exc).__name__}: {exc}"
                    self.event("POLICY_EXCEPTION", {"revision": self.coder.revision, "error": failure})
                    if isinstance(exc, ModelAPIError):
                        error = failure
                        outcome = "INFRA_FAILURE"
                        self.event("INFRA_FAILURE", {"error": failure})
                        break
                    if self.episode.ended:
                        outcome = "AGENT_STOP_WITH_POLICY_EXCEPTION"
                        error = failure
                        break
                if self.contracts >= self.max_contracts or self.episode.broker.sequence >= self.action_budget or self.vision.api.calls_used >= self.max_vision_calls:
                    outcome = "BUDGET_EXHAUSTED"
                    break
                self.event("NEEDS_REPLAN", {"reason": failure, "checkpoint": self.state})
            else:
                outcome = "REPAIR_EXHAUSTED"
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            self.event("INFRA_FAILURE", {"error": error})
        finally:
            if hasattr(self.episode, "broker"):
                if not self.episode.ended:
                    receipt, obs = self.episode.step("supervisor-final-stop", "STOP")
                    forced_stop = True
                    self.event("SUPERVISOR_FORCED_STOP", receipt)
                result = {"kind": "development_not_unseen_benchmark", "suite": self.suite,
                          "split": self.split, "model": self.model, "code_model": self.code_model,
                          "outcome": outcome,
                          "error": error, "forced_stop": forced_stop,
                          "policy_revisions": getattr(getattr(self, "coder", None), "revision", 0),
                          "code_agent_calls": getattr(getattr(self, "coder", None), "attempts", 0),
                          "perception_contracts": self.contracts,
                          "agent_actions": len(self.actions), "wall_time_s": time.monotonic() - self.started,
                          "capabilities": self.episode.capabilities(),
                          "agent_capabilities": self.public_capabilities(), "state": self.state,
                          **self.episode.evaluate()}
                result["agent_success"] = bool(result["metrics"].get("success")) and not forced_stop
                (self.output / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
                print(json.dumps({k: v for k, v in result.items() if k != "capabilities"}, indent=2))
            self.episode.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=["r2r", "rxr"], default="r2r")
    parser.add_argument("--episode-id", default="1")
    parser.add_argument("--split", choices=["train", "val_seen"], default="train")
    parser.add_argument("--model", default="qwen3.8-omni-flash")
    parser.add_argument("--code-model", default="deepseek-v4.1-flash")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    DevelopmentRun(args.suite, args.episode_id, args.model, args.output, args.split, args.code_model).run()


if __name__ == "__main__":
    main()
