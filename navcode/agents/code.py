"""Compile and repair long-lived Python policies."""
import json
from pathlib import Path

from navcode.agents.prompts import CODE_SYSTEM
from navcode.agents.protocol import parse_json, validate_program

class CodeAgent:
    def __init__(self, api, output, system=CODE_SYSTEM, image_provider=None, include_initial_image=False,
                 recorded_initial=None, skills=None):
        self.api = api
        self.output = Path(output)
        self.revision = 0
        self.history = []
        self.system = system
        self.image_provider = image_provider
        self.attempts = 0
        self.include_initial_image = include_initial_image
        self.recorded_initial = recorded_initial
        self.submission_origin = "live_model"
        self.skills = skills

    def compile(self, task, capabilities, state, evidence, failure=None):
        if self.revision == 0 and self.recorded_initial is not None and failure is None:
            artifact = {k: self.recorded_initial[k] for k in ("source", "rationale")}
            validate_program(artifact["source"])
            self.revision = 1
            self.submission_origin = "recorded_initial_model_artifact"
            (self.output/"policy_v1.py").write_text(artifact["source"])
            self.history.append(artifact)
            return artifact["source"]
        self.submission_origin = "live_model"
        context = {"task": task, "capabilities": capabilities, "state": state,
                   "evidence": evidence[-4:], "failure": failure,
                   "previous_programs": self.history[-1:]}
        images = self.image_provider() if (failure or self.include_initial_image) and self.image_provider else []
        if self.skills is not None:
            self.skills.read("policy-writing", reason="entry")
            if failure:
                self.skills.read("state-repair", reason="policy_revision")
        for turn in range(3 if self.skills is not None else 1):
            remaining_calls = self.api.max_calls - self.api.calls_used if hasattr(self.api, "calls_used") else None
            reads_open = turn < 2 and (remaining_calls is None or remaining_calls >= 2)
            if self.skills is not None:
                context.update(self.skills.context(), skill_reads_open=reads_open)
            if hasattr(self.api, "calls_used") and self.api.calls_used >= self.api.max_calls:
                raise RuntimeError("code model call budget exhausted")
            self.attempts += 1
            result = self.api.generate(self.system, json.dumps(context), images=images,
                                       max_tokens=3000 if self.system != CODE_SYSTEM else 2200)
            artifact = parse_json(result["text"])
            if artifact.get("tool") == "read_skill" and self.skills is not None:
                if not reads_open:
                    raise ValueError("code skill-read budget exhausted")
                self.skills.read(artifact.get("name"))
                continue
            break
        if not isinstance(artifact.get("source"), str):
            raise ValueError("missing Python policy source")
        validate_program(artifact["source"])
        self.revision += 1
        (self.output / f"policy_v{self.revision}.py").write_text(artifact["source"])
        self.history.append(artifact)
        return artifact["source"]
