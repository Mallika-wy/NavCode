"""An intentionally synthetic route; absolutely NOT an R2R/RxR benchmark."""
from .contracts import Observation


class MockRouteEnvironment:
    """Forward through 2 doors -> left -> forward into goal room.

    Physical state is private. Agent receives only a synthetic visual fixture.
    """
    _VIEWS = {
        0: "long hallway, door visible in front",
        1: "door_a threshold has moved behind the camera; door_a crossed",
        2: "straight corridor, another door visible ahead",
        3: "door_b threshold has moved behind the camera; door_b crossed",
        4: "inside the intended room, furniture and room entrance behind",
    }

    def __init__(self, episode_id: str = "mock-episode"):
        self.episode_id = episode_id
        self._position = 0
        self._turned = False
        self._stopped = False
        self._ticks = 0
        self.actions: list[str] = []

    def observe(self) -> Observation:
        return Observation(f"{self.episode_id}:obs-{self._ticks:03d}",
                           self._ticks, self._VIEWS[self._position])

    def step(self, action: str) -> Observation:
        if self._stopped:
            raise RuntimeError("Episode already stopped")
        if action not in {"FORWARD", "TURN_LEFT", "STOP"}:
            raise ValueError("Unsupported mock action")
        self.actions.append(action)
        self._ticks += 1
        if action == "STOP":
            self._stopped = True
        elif action == "TURN_LEFT":
            if self._position == 3:
                self._turned = True
        elif action == "FORWARD":
            if self._position < 3:
                self._position += 1
            elif self._position == 3 and self._turned:
                self._position = 4
        return self.observe()

    def evaluate_private(self) -> bool:
        """Called only AFTER episode termination; never passed to either agent."""
        return self._position == 4 and self._turned and self._stopped
