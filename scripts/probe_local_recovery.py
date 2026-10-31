"""Free, trusted primitive physics diagnostic; NOT a navigation benchmark.

Replay a recorded action prefix to its first visual stall, then compare fixed
local recovery motions. No world pose/navmesh/goal feedback controls the probes.
Native metrics are read only after STOP. This intentionally isolates primitive
physics from learned reasoning and the experimental depth guard.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from navcode.benchmark import BenchmarkEpisode, make_config

parser = argparse.ArgumentParser()
parser.add_argument("run")
parser.add_argument("--output", required=True)
args = parser.parse_args()
run, output = Path(args.run), Path(args.output)
output.mkdir(parents=True, exist_ok=False)
source_result = json.loads((run/"result.json").read_text())
events = [json.loads(l) for l in (run/"trace.jsonl").read_text().splitlines()]
stall = next(e["payload"] for e in events if e["kind"] == "LOCAL_MOTION_RESOLVED" and e["payload"]["status"] == "VISUALLY_STALLED")
sequence = int(stall["final_obs_id"].rsplit(":", 1)[1])
prefix = [e["payload"]["action"] for e in events if e["kind"] == "ACTION_COMMITTED" and e["payload"]["action_seq"] <= sequence]
episode = BenchmarkEpisode(make_config(source_result["suite"], source_result["split"], rgbd=True,
                                      episode_ids=[source_result["episode_id"]]), rgbd=True)
reports = []
try:
    for mode, escape_angle in [("retry_only", None), ("back", 180), ("back_left", 210), ("back_right", 150)]:
        task, obs = episode.reset()
        actions = []
        directory = output/mode
        directory.mkdir()
        def step(action):
            global obs
            receipt, new = episode.step(f"probe-{len(actions)}", action)
            actions.append(receipt)
            old = obs
            obs = new
            return float(np.mean(np.abs(old["rgb"].astype(float)-new["rgb"].astype(float))))
        for action in prefix:
            step(action)
        Image.fromarray(obs["rgb"]).save(directory/"before.png")
        before = obs["rgb"].copy()
        reverse_change = None
        turn_angle = episode.config.SIMULATOR.TURN_ANGLE
        if escape_angle is not None:
            count = round(escape_angle/turn_angle)
            for _ in range(count):
                step("TURN_RIGHT")
            reverse_change = step("MOVE_FORWARD")
            for _ in range(count):
                step("TURN_LEFT")
        Image.fromarray(obs["rgb"]).save(directory/"after_escape.png")
        changes = [step("MOVE_FORWARD") for _ in range(3)]
        Image.fromarray(obs["rgb"]).save(directory/"after_retry.png")
        after_change = float(np.mean(np.abs(before.astype(float)-obs["rgb"].astype(float))))
        step("STOP")
        metrics = episode.evaluate()["metrics"]
        report = {"mode": mode, "escape_angle_deg": escape_angle, "prefix_actions": len(prefix),
                  "reverse_rgb_change": reverse_change, "retry_forward_rgb_changes": changes,
                  "before_after_retry_rgb_change": after_change, "native_total_path_length": metrics["path_length"],
                  "actions": actions}
        (directory/"result.json").write_text(json.dumps(report, indent=2))
        reports.append(report)
        print(json.dumps({k:v for k,v in report.items() if k != "actions"}), flush=True)
finally:
    episode.close()
(output/"summary.json").write_text(json.dumps({"kind":"primitive_recovery_diagnostic_not_navigation_score",
                                              "source_run":str(run), "reports":reports}, indent=2))
