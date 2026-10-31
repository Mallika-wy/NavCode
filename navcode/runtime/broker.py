"""Single writer of committed environment actions, with epoch-scoped idempotency."""

class ActionBroker:
    """The sole env.step writer; op IDs are scoped to a fresh episode epoch."""

    def __init__(self, env, actions, epoch, budget=500):
        self._env = env
        self.actions = tuple(actions)
        self.epoch = epoch
        self.budget = budget
        self.committed = {}
        self.sequence = 0

    def step(self, epoch, op_id, action):
        if epoch != self.epoch:
            raise ValueError("stale episode epoch")
        if not isinstance(op_id, str) or not op_id:
            raise ValueError("nonempty operation ID required")
        if op_id in self.committed:
            previous, receipt, obs = self.committed[op_id]
            if previous != action:
                raise ValueError("operation ID reused with different payload")
            return receipt, obs
        if action not in self.actions:
            raise ValueError("unsupported primitive")
        if self._env.episode_over or self.sequence >= self.budget:
            raise RuntimeError("episode ended or action budget exhausted")
        obs = self._env.step({"action": action})
        self.sequence += 1
        receipt = {"epoch": epoch, "op_id": op_id, "action": action,
                   "action_seq": self.sequence,
                   "obs_id": f"{epoch}:{self.sequence}"}
        self.committed[op_id] = (action, receipt, obs)
        return receipt, obs
