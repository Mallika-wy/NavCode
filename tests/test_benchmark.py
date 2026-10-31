import numpy as np
import pytest
from navcode.benchmark import ActionBroker, filter_observation, make_config


class DummyEnv:
    episode_over = False
    calls = 0

    def step(self, action):
        self.calls += 1
        self.episode_over = action["action"] == "STOP"
        return {"rgb": np.zeros((2, 2, 3), dtype=np.uint8)}


def test_retry_is_idempotent_even_after_stop():
    env = DummyEnv()
    broker = ActionBroker(env, ["STOP", "MOVE_FORWARD"], "epoch")
    receipt, _ = broker.step("epoch", "op", "STOP")
    assert broker.step("epoch", "op", "STOP")[0] == receipt
    assert env.calls == 1
    with pytest.raises(ValueError, match="payload"):
        broker.step("epoch", "op", "MOVE_FORWARD")
    with pytest.raises(ValueError, match="stale"):
        broker.step("previous-episode", "new", "STOP")


def test_filter_drops_all_oracles_and_copies_sensor_arrays():
    raw = {"rgb": np.zeros((2, 2, 3)), "depth": np.ones((2, 2, 1)),
           "gps": [1, 2], "progress": 0.9, "shortest_path_sensor": 1,
           "goal": "private", "instruction": {"trajectory_id": 5}}
    obs = filter_observation(raw)
    assert set(obs) == {"rgb"}
    obs["rgb"][:] = 3
    assert not raw["rgb"].any()
    assert set(filter_observation(raw, rgbd=True)) == {"rgb", "depth"}


@pytest.mark.parametrize("suite,angle", [("r2r", 15), ("rxr", 30)])
def test_resolved_config_has_no_oracle_sensors(suite, angle):
    cfg = make_config(suite)
    assert cfg.TASK.SENSORS == []
    assert cfg.SIMULATOR.AGENT_0.SENSORS == ["RGB_SENSOR"]
    assert cfg.SIMULATOR.TURN_ANGLE == angle
    assert cfg.SIMULATOR.FORWARD_STEP_SIZE == 0.25


def test_action_budget_and_invalid_action_do_not_move():
    env = DummyEnv()
    broker = ActionBroker(env, ["MOVE_FORWARD"], "epoch", budget=1)
    with pytest.raises(ValueError):
        broker.step("epoch", "illegal", "TELEPORT")
    broker.step("epoch", "a", "MOVE_FORWARD")
    with pytest.raises(RuntimeError):
        broker.step("epoch", "b", "MOVE_FORWARD")
    assert env.calls == 1
