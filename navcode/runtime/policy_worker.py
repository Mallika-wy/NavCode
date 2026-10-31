"""Executed ONLY inside the mount/PID/user/network-isolated bubblewrap worker."""
import json
import resource
import sys

resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))
resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))

incoming, outgoing = sys.stdin, sys.stdout


def emit(value):
    outgoing.write(json.dumps(value, allow_nan=False) + "\n")
    outgoing.flush()


class Nav:
    def __init__(self):
        self.sequence = 0

    def request(self, method, **params):
        self.sequence += 1
        emit({"kind": "rpc", "seq": self.sequence, "method": method, "params": params})
        line = incoming.readline(65537)
        response = json.loads(line)
        if response.get("seq") != self.sequence:
            raise RuntimeError("RPC sequence mismatch")
        if "error" in response:
            raise RuntimeError(response["error"])
        return response["result"]

    def observe(self):
        return self.request("observe")

    def perceive(self, contract):
        return self.request("perceive", contract=contract)

    def step(self, action, op_id):
        return self.request("step", action=action, op_id=op_id)

    def checkpoint(self, state):
        return self.request("checkpoint", state=state)

    def move_to_candidate(self, candidate_id, obs_id, max_steps=4):
        return self.request("move_to_candidate", candidate_id=candidate_id, obs_id=obs_id, max_steps=max_steps)

    def turn(self, degrees):
        return self.request("turn", degrees=degrees)

    def recover(self):
        return self.request("recover")


try:
    payload = json.loads(incoming.readline(65537))
    namespace = {"__name__": "policy"}
    exec(compile(payload["source"], "<generated-policy>", "exec"), namespace)
    # This is an OS-isolated Python runtime, not an AST or builtin sandbox.
    state = namespace["run"](Nav(), payload["state"])
    emit({"kind": "done", "state": state})
except BaseException as exc:
    emit({"kind": "exception", "error_type": type(exc).__name__, "error": str(exc)[:1000]})
