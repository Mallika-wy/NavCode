from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class Observation:
    obs_id: str
    step_index: int
    # Fixture only. Real adapters MUST send image references/bytes, not oracle tags.
    visual_hint: str


@dataclass(frozen=True)
class Task:
    instruction: str
    language: str = "en"
    benchmark: str = "mock_vln"


@dataclass(frozen=True)
class PerceptionTask:
    request_id: str
    kind: Literal["VERIFY_TRANSITION", "VERIFY_GOAL", "DESCRIBE_SCENE"]
    current_obs_id: str
    instruction: str
    stage: str
    history_obs_ids: tuple[str, ...]
    recent_action_ids: tuple[str, ...]


@dataclass(frozen=True)
class PerceptionResult:
    request_id: str
    status: Literal["VERIFIED", "NOT_FOUND", "UNCERTAIN", "NEED_MORE_VIEW"]
    landmark_id: str | None
    evidence_obs_ids: tuple[str, ...]
    explanation: str


@dataclass(frozen=True)
class EvidenceClaim:
    claim_id: str
    proposition: str
    verdict: Literal["SUPPORTED", "UNCERTAIN", "RETRACTED"]
    evidence_obs_ids: tuple[str, ...]
    revision: int
    replaces_revision: int | None = None


@dataclass(frozen=True)
class Event:
    event_id: int
    episode_id: str
    kind: str
    payload: dict[str, Any]

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProgramArtifact:
    revision: int
    source: str
    template_name: str


@dataclass
class EpisodeResult:
    episode_id: str
    terminal: str
    actions: list[str]
    policy_revisions: int
    perception_calls: int
    code_agent_calls: int
    # Evaluation only: NEVER inserted into agent / policy / perception context.
    mock_success: bool
    state: dict[str, Any] = field(default_factory=dict)
