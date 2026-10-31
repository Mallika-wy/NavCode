import pytest
from navcode.runtime.sandbox import PolicyRuntime


def test_real_python_loop_can_only_use_granted_rpc():
    calls = []
    def handler(method, params):
        calls.append((method, params))
        return {"ok": True}
    state = PolicyRuntime().run('''
def run(nav, state):
    for i in range(3):
        nav.step("MOVE_FORWARD", "op-" + str(i))
    state["count"] = 3
    nav.checkpoint(state)
    return state
''', {}, handler)
    assert state == {"count": 3}
    assert [c[0] for c in calls] == ["step", "step", "step", "checkpoint"]


def test_worker_cannot_see_host_files_env_or_network():
    result = PolicyRuntime().run('''
def run(nav, state):
    import os, socket
    state["home_visible"] = os.path.exists("/home1/gmh")
    state["token_visible"] = "DMXAPI_TOKEN" in os.environ
    state["interfaces"] = [name for _, name in socket.if_nameindex()]
    state["host_visible"] = os.path.exists("/proc/1/root/home1/gmh")
    return state
''', {}, lambda *args: None)
    assert result == {"home_visible": False, "token_visible": False,
                      "interfaces": ["lo"], "host_visible": False}


def test_infinite_loop_is_terminated():
    with pytest.raises(TimeoutError):
        PolicyRuntime(timeout=0.3).run("def run(nav, state):\n    while True: pass", {}, lambda *a: None)


def test_forged_capability_is_rejected():
    with pytest.raises(ValueError, match="unauthorized"):
        PolicyRuntime().run('''
def run(nav, state):
    nav.request("get_ground_truth")
    return state
''', {}, lambda *a: None)


def test_patch_continues_checkpoint_without_replaying_committed_actions():
    from navcode.benchmark import ActionBroker
    class Env:
        episode_over = False
        actions = []
        def step(self, action):
            self.actions.append(action["action"])
            self.episode_over = action["action"] == "STOP"
            return {}
    env = Env()
    broker = ActionBroker(env, ["MOVE_FORWARD", "STOP"], "episode")
    checkpoint = {}
    def handler(method, params):
        if method == "step":
            return broker.step("episode", params["op_id"], params["action"])[0]
        if method == "checkpoint":
            checkpoint.update(params["state"])
            return {"saved": True}
        raise ValueError(method)
    with pytest.raises(RuntimeError, match="needs repair"):
        PolicyRuntime().run('''
def run(nav, state):
    nav.step("MOVE_FORWARD", "prefix")
    state["stage"] = 1
    nav.checkpoint(state)
    raise RuntimeError("needs repair")
''', {}, handler)
    state = PolicyRuntime().run('''
def run(nav, state):
    if state.get("stage", 0) == 0:
        nav.step("MOVE_FORWARD", "prefix")
    nav.step("MOVE_FORWARD", "suffix")
    nav.step("STOP", "done")
    return state
''', checkpoint, handler)
    assert state == {"stage": 1}
    assert env.actions == ["MOVE_FORWARD", "MOVE_FORWARD", "STOP"]
    assert broker.sequence == 3
