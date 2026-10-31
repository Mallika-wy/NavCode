"""Explicit single-writer motion supervision and two-agent message routing."""
from .contracts import EpisodeResult, PerceptionTask, Task
from .memory import EpisodeMemory
from .mock_env import MockRouteEnvironment
from .code_agent import MockCodeAgent
from .runtime import TrustedFixtureRuntime
from .vision_agent import MockVisionAgent


class NavFacade:
    def __init__(self, task: Task, env: MockRouteEnvironment, memory: EpisodeMemory,
                 vision: MockVisionAgent, max_actions: int = 20):
        self._task = task
        self._env = env
        self._memory = memory
        self._vision = vision
        self._max_actions = max_actions
        self._terminated = False
        self._perception_id = 0
        self._last_observation_id = env.observe().obs_id
        memory.observe(env.observe())

    def observe(self):
        return self._memory.frame(self._last_observation_id)

    def perceive(self, kind: str, obs_id: str):
        if obs_id != self._last_observation_id:
            raise ValueError("STALE_OBSERVATION")
        if kind not in ("VERIFY_TRANSITION", "VERIFY_GOAL", "DESCRIBE_SCENE"):
            raise ValueError("INVALID_PERCEPTION_KIND")
        self._perception_id += 1
        history = list(self._memory.observations)[-3:-1]
        request = PerceptionTask(
            request_id=f"vision-{self._perception_id:03d}",
            kind=kind, current_obs_id=obs_id,
            instruction=self._task.instruction,
            stage="door_search" if kind == "VERIFY_TRANSITION" else "goal_verification",
            history_obs_ids=tuple(history),
            recent_action_ids=self._memory.recent_actions(),
        )
        self._memory.append("PERCEPTION_REQUEST", {"request_id": request.request_id,
                                                    "kind": kind,
                                                    "current_obs_id": obs_id})
        result = self._vision.investigate(request, self._memory)
        self._memory.append("PERCEPTION_RESULT", {"request_id": request.request_id,
                                                   "status": result.status,
                                                   "evidence_obs_ids": result.evidence_obs_ids})
        return result

    def step(self, action: str):
        if self._terminated:
            raise RuntimeError("EPISODE_ENDED")
        if len(self._env.actions) >= self._max_actions:
            raise RuntimeError("BUDGET_EXHAUSTED")
        obs = self._env.step(action)
        self._memory.append("ACTION", {"action_seq": len(self._env.actions), "action": action})
        self._memory.observe(obs)
        self._last_observation_id = obs.obs_id
        if action == "STOP":
            self._terminated = True
        return obs

    def stop(self):
        return self.step("STOP")

    def checkpoint(self, label: str, state: dict):
        self._memory.append("CHECKPOINT", {"label": label,
                                           "state": {k: list(v) if isinstance(v, list) else v
                                                     for k, v in state.items()}})


class Supervisor:
    def __init__(self, code_agent: MockCodeAgent | None = None,
                 vision_agent: MockVisionAgent | None = None):
        self.code_agent = code_agent or MockCodeAgent()
        self.vision_agent = vision_agent or MockVisionAgent()
        self.runtime = TrustedFixtureRuntime()
        self.memory: EpisodeMemory | None = None

    def run_episode(self, episode_id: str = "mock-demo") -> EpisodeResult:
        env = MockRouteEnvironment(episode_id)
        task = Task("Follow the hall, pass two different doors, turn left and enter the room")
        memory = EpisodeMemory(episode_id)
        self.memory = memory
        nav = NavFacade(task, env, memory, self.vision_agent)
        state: dict = {}
        artifact = self.code_agent.generate(memory.agent_context(task.instruction, state, 0))
        outcome: dict = {}
        for attempt in range(2):
            memory.append("PROGRAM_SUBMITTED", {"revision": artifact.revision,
                                                "template": artifact.template_name})
            outcome = self.runtime.execute(artifact.source, nav, state, task)
            memory.append("PROGRAM_RESULT", {"revision": artifact.revision, **outcome})
            if outcome["event"] == "TASK_DONE":
                break
            if outcome["event"] != "NEEDS_REPLAN" or attempt == 1:
                break
            context = memory.agent_context(task.instruction, state, artifact.revision)
            memory.append("CODE_AGENT_WAKE", {"reason": outcome.get("reason")})
            artifact = self.code_agent.repair(context, outcome)
        # Private mock scoring never made available to Agent or Policy.
        score = env.evaluate_private()
        memory.append("EPISODE_TERMINAL", {"terminal": outcome["event"]})
        return EpisodeResult(episode_id, outcome["event"], list(env.actions),
                             artifact.revision, self.vision_agent.calls,
                             self.code_agent.calls, score, dict(state))
