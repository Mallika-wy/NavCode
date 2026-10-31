import pytest
from navcode_ma.memory import EpisodeMemory
from navcode_ma.contracts import Observation
from navcode_ma.runtime import TrustedFixtureRuntime, UntrustedPolicyError
from navcode_ma.policy_templates import FIRST_POLICY
from navcode_ma.supervisor import Supervisor, NavFacade
from navcode_ma.mock_env import MockRouteEnvironment
from navcode_ma.vision_agent import MockVisionAgent
from navcode_ma.contracts import Task


def test_two_agents_and_policy_complete_mock_route():
    s = Supervisor()
    result = s.run_episode("episode-a")
    assert result.mock_success is True
    assert result.terminal == "TASK_DONE"
    assert result.actions == ["FORWARD", "FORWARD", "FORWARD", "TURN_LEFT", "FORWARD", "STOP"]
    assert result.code_agent_calls == 1
    assert result.perception_calls >= 4
    assert result.state["seen_doors"] == ["door_a", "door_b"]
    assert len([e for e in s.memory.events if e.kind == "CHECKPOINT"]) == 2


def test_vision_uncertainty_wakes_code_agent_without_replaying_motion():
    s = Supervisor(vision_agent=MockVisionAgent(fail_goal_once=True))
    result = s.run_episode("episode-b")
    assert result.mock_success is True
    assert result.code_agent_calls == 2
    assert result.policy_revisions == 2
    assert result.actions == ["FORWARD", "FORWARD", "FORWARD", "TURN_LEFT", "FORWARD", "STOP"]
    assert len([e for e in s.memory.events if e.kind == "CODE_AGENT_WAKE"]) == 1


def test_claims_are_append_only_and_revisable():
    mem = EpisodeMemory("ep")
    mem.observe(Observation("f1", 1, "door evidence"))
    mem.observe(Observation("f2", 2, "contradictory door evidence"))
    a = mem.propose_claim("door_1", "crossed first door", "SUPPORTED", ("f1",))
    b = mem.propose_claim("door_1", "crossed first door", "RETRACTED", ("f2",))
    assert (a.revision, b.revision, b.replaces_revision) == (1, 2, 1)
    assert len(mem.claim_history("door_1")) == 2
    assert mem.latest_claim("door_1").verdict == "RETRACTED"


def test_episode_memory_disallows_foreign_observation():
    first = EpisodeMemory("a")
    second = EpisodeMemory("b")
    first.observe(Observation("a-1", 0, "door"))
    with pytest.raises(KeyError):
        second.frame("a-1")
    with pytest.raises(ValueError):
        second.propose_claim("door", "crossed", "SUPPORTED", ("a-1",))


def test_policy_rejects_arbitrary_generated_code():
    runtime = TrustedFixtureRuntime()
    runtime.validate(FIRST_POLICY)
    with pytest.raises(UntrustedPolicyError):
        runtime.validate('def run(nav, state, task):\n    __import__("os").system("whoami")\n')


def test_stale_frame_request_fails_and_never_moves():
    env = MockRouteEnvironment("ep")
    memory = EpisodeMemory("ep")
    facade = NavFacade(Task("demo"), env, memory, MockVisionAgent())
    with pytest.raises(ValueError, match="STALE_OBSERVATION"):
        facade.perceive("VERIFY_TRANSITION", "old-obs")
    assert env.actions == []


def test_vision_observation_does_not_step_environment():
    env = MockRouteEnvironment("ep")
    memory = EpisodeMemory("ep")
    facade = NavFacade(Task("demo"), env, memory, MockVisionAgent())
    result = facade.perceive("VERIFY_TRANSITION", facade.observe().obs_id)
    assert result.status == "NOT_FOUND"
    assert env.actions == []


def test_bounded_budget():
    env = MockRouteEnvironment("ep")
    memory = EpisodeMemory("ep")
    facade = NavFacade(Task("demo"), env, memory, MockVisionAgent(), max_actions=1)
    facade.step("FORWARD")
    with pytest.raises(RuntimeError, match="BUDGET_EXHAUSTED"):
        facade.step("FORWARD")
    assert env.actions == ["FORWARD"]
