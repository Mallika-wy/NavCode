"""Habitat 0.1.7 adapter. Only evaluator code can access metrics/episode GT.

Upstream dataset and measures are loaded verbatim without its training-only
package initializer (which eagerly imports every neural trainer).
"""
from __future__ import annotations

import hashlib
import importlib
import json
import sys
import types
from pathlib import Path
from uuid import uuid4

import numpy as np

from navcode.runtime.broker import ActionBroker

from navcode.paths import PROJECT_ROOT

ROOT = PROJECT_ROOT
UPSTREAM = ROOT / "third_party/VLN-CE"


def load_extensions():
    if "habitat_extensions" not in sys.modules:
        package = types.ModuleType("habitat_extensions")
        package.__path__ = [str(UPSTREAM / "habitat_extensions")]
        sys.modules["habitat_extensions"] = package
    for name in ("task", "measures"):
        importlib.import_module("habitat_extensions." + name)
    from habitat_extensions.config.default import get_extended_config
    return get_extended_config


def make_config(suite="r2r", split="train", rgbd=False, episode_ids=None):
    if suite not in ("r2r", "rxr"):
        raise ValueError(suite)
    filename = "vlnce_task.yaml" if suite == "r2r" else "rxr_vlnce_english_task.yaml"
    cfg = load_extensions()(str(UPSTREAM / "habitat_extensions/config" / filename))
    cfg.defrost()
    cfg.SEED = 0
    cfg.DATASET.SPLIT = split
    cfg.DATASET.DATA_PATH = str(UPSTREAM / cfg.DATASET.DATA_PATH)
    cfg.DATASET.SCENES_DIR = str(UPSTREAM / cfg.DATASET.SCENES_DIR)
    if episode_ids is not None:
        cfg.DATASET.EPISODES_ALLOWED = list(map(str, episode_ids))
    # Text comes from episode.instruction.instruction_text. No oracle sensors,
    # no RxR BERT features are needed for a text-conditioned model.
    cfg.TASK.SENSORS = []
    cfg.SIMULATOR.AGENT_0.SENSORS = ["RGB_SENSOR"] + (["DEPTH_SENSOR"] if rgbd else [])
    cfg.TASK.NDTW.GT_PATH = str(UPSTREAM / cfg.TASK.NDTW.GT_PATH)
    cfg.TASK.NDTW.SPLIT = split
    cfg.TASK.SDTW.SPLIT = split
    cfg.ENVIRONMENT.ITERATOR_OPTIONS.SHUFFLE = False
    cfg.ENVIRONMENT.ITERATOR_OPTIONS.MAX_SCENE_REPEAT_STEPS = -1
    cfg.freeze()
    return cfg




def filter_observation(raw, rgbd=False):
    """Explicit allowlist: no pose, goal, progress, instruction metadata or GT."""
    result = {"rgb": np.array(raw["rgb"], copy=True)}
    if rgbd:
        result["depth"] = np.array(raw["depth"], copy=True)
    return result


class BenchmarkEpisode:
    def __init__(self, config, rgbd=False):
        import habitat
        self.config = config
        self.rgbd = rgbd
        self._env = habitat.Env(config=config)

    def reset(self):
        raw = self._env.reset()
        self.epoch = uuid4().hex
        self.broker = ActionBroker(self._env, self.config.TASK.POSSIBLE_ACTIONS, self.epoch)
        instruction = self._env.current_episode.instruction
        self.task = {"instruction": instruction.instruction_text,
                     "language": getattr(instruction, "language", None) or "en",
                     "epoch": self.epoch}
        return dict(self.task), filter_observation(raw, self.rgbd)

    def step(self, op_id, action):
        receipt, raw = self.broker.step(self.epoch, op_id, action)
        return receipt, filter_observation(raw, self.rgbd)

    @property
    def ended(self):
        return self._env.episode_over

    def evaluate(self):
        if not self.ended:
            raise RuntimeError("metrics are private until episode terminates")
        return {"episode_id": str(self._env.current_episode.episode_id),
                "metrics": self._env.get_metrics()}

    def capabilities(self):
        cfg = self.config
        return {"config_sha256": hashlib.sha256(cfg.dump().encode()).hexdigest(),
                "resolved_config": cfg.dump(),
                "actions": list(cfg.TASK.POSSIBLE_ACTIONS),
                "forward_step_m": cfg.SIMULATOR.FORWARD_STEP_SIZE,
                "turn_angle_deg": cfg.SIMULATOR.TURN_ANGLE,
                "max_steps": cfg.ENVIRONMENT.MAX_EPISODE_STEPS,
                "task_sensors": list(cfg.TASK.SENSORS),
                "sim_sensors": list(cfg.SIMULATOR.AGENT_0.SENSORS),
                "sensor_track": "RGB-D" if self.rgbd else "RGB",
                "success_distance_m": cfg.TASK.SUCCESS_DISTANCE}

    def close(self):
        self._env.close()


def smoke(suite, split, output, rgbd=False):
    from PIL import Image
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    episode = BenchmarkEpisode(make_config(suite, split, rgbd=rgbd), rgbd=rgbd)
    try:
        task, obs = episode.reset()
        Image.fromarray(obs["rgb"]).save(output / "initial.png")
        if rgbd:
            np.save(output / "initial_depth.npy", obs["depth"])
        events = []
        for i, action in enumerate(["TURN_LEFT", "TURN_RIGHT", "MOVE_FORWARD", "STOP"]):
            receipt, obs = episode.step(f"smoke-{i}", action)
            events.append(receipt)
        Image.fromarray(obs["rgb"]).save(output / "final.png")
        result = {"kind": "infrastructure_smoke_not_navigation_baseline", "suite": suite,
                  "split": split, "task": task, "capabilities": episode.capabilities(),
                  "events": events, **episode.evaluate()}
        (output / "result.json").write_text(json.dumps(result, indent=2))
        return {k: result[k] for k in ("suite", "split", "episode_id", "metrics")}
    finally:
        episode.close()


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=["r2r", "rxr"], required=True)
    parser.add_argument("--split", default="train")
    parser.add_argument("--output", required=True)
    parser.add_argument("--rgbd", action="store_true")
    args = parser.parse_args()
    print(json.dumps(smoke(args.suite, args.split, args.output, args.rgbd), indent=2))


if __name__ == "__main__":
    main()
