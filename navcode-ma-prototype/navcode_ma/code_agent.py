"""Backend protocol + deterministic mock for program generation and repair."""
from typing import Protocol
from .contracts import ProgramArtifact
from .policy_templates import FIRST_POLICY, REPAIR_POLICY


class CodeAgentBackend(Protocol):
    def generate(self, context: dict) -> ProgramArtifact: ...
    def repair(self, context: dict, event: dict) -> ProgramArtifact: ...


class MockCodeAgent:
    def __init__(self):
        self.calls = 0

    def generate(self, context: dict) -> ProgramArtifact:
        self.calls += 1
        return ProgramArtifact(1, FIRST_POLICY, "first_policy")

    def repair(self, context: dict, event: dict) -> ProgramArtifact:
        self.calls += 1
        return ProgramArtifact(2, REPAIR_POLICY, "goal_reinspection")
