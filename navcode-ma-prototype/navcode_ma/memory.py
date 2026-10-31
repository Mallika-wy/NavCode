"""Canonical, episode-isolated append-only events and revocable evidence."""
from dataclasses import asdict
import json
from pathlib import Path

from .contracts import EvidenceClaim, Event, Observation


class EpisodeMemory:
    def __init__(self, episode_id: str):
        self.episode_id = episode_id
        self.events: list[Event] = []
        self.observations: dict[str, Observation] = {}
        self._claims: dict[str, list[EvidenceClaim]] = {}

    def append(self, kind: str, payload: dict) -> Event:
        item = Event(len(self.events) + 1, self.episode_id, kind, dict(payload))
        self.events.append(item)
        return item

    def observe(self, obs: Observation) -> None:
        if obs.obs_id in self.observations:
            raise ValueError(f"Duplicate observation id: {obs.obs_id}")
        self.observations[obs.obs_id] = obs
        self.append("OBSERVATION", {"obs_id": obs.obs_id, "step": obs.step_index})

    def frame(self, obs_id: str) -> Observation:
        # No filesystem/path lookup; all observations scoped to this memory instance.
        return self.observations[obs_id]

    def latest(self) -> Observation:
        return next(reversed(self.observations.values()))

    def recall(self, query: str = "", limit: int = 5) -> list[dict]:
        if not 1 <= limit <= 20:
            raise ValueError("recall limit must be 1..20")
        q = query.lower()
        results = [
            {"obs_id": o.obs_id, "summary": o.visual_hint}
            for o in self.observations.values()
            if not q or q in o.visual_hint.lower()
        ]
        return results[-limit:]

    def recent_actions(self, limit: int = 8) -> tuple[str, ...]:
        return tuple(e.payload["action"] for e in self.events if e.kind == "ACTION")[-limit:]

    def propose_claim(self, claim_id: str, proposition: str, verdict: str,
                      evidence_obs_ids: tuple[str, ...]) -> EvidenceClaim:
        if verdict not in ("SUPPORTED", "UNCERTAIN", "RETRACTED"):
            raise ValueError(verdict)
        if not evidence_obs_ids or any(i not in self.observations for i in evidence_obs_ids):
            raise ValueError("Claim needs evidence from current episode")
        old = self._claims.get(claim_id, [])
        revision = len(old) + 1
        claim = EvidenceClaim(claim_id, proposition, verdict, evidence_obs_ids,
                              revision, old[-1].revision if old else None)
        self._claims.setdefault(claim_id, []).append(claim)
        self.append("EVIDENCE_REVISION", asdict(claim))
        return claim

    def claim_history(self, claim_id: str) -> tuple[EvidenceClaim, ...]:
        return tuple(self._claims.get(claim_id, []))

    def latest_claim(self, claim_id: str) -> EvidenceClaim | None:
        entries = self._claims.get(claim_id, [])
        return entries[-1] if entries else None

    def agent_context(self, instruction: str, state: dict, policy_revision: int) -> dict:
        return {
            "instruction": instruction,
            "policy_revision": policy_revision,
            "state": dict(state),
            "recent_events": [e.to_json() for e in self.events[-8:]],
            "keyframes": self.recall("door", limit=5),
            "available_recall": True,
        }

    def export(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as stream:
            for event in self.events:
                stream.write(json.dumps(event.to_json(), ensure_ascii=False) + "\n")
