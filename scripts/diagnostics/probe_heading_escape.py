"""Fixed-heading physics diagnosis at a training stall; no navigation scores.

This deliberately bypasses the experimental depth guard, commits only native
primitives and reads native path length after STOP. It never uses pose, navmesh
or evaluation feedback to choose an action. Do not convert the best probe angle
for one episode into a navigation rule.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from navcode.artifacts.provenance import archive_package_sources
from navcode.benchmark import BenchmarkEpisode, make_config
from navcode.control.rgbd import calibration
from navcode.control.geometry import heading_clearances


parser = argparse.ArgumentParser()
parser.add_argument("run")
parser.add_argument("--output", required=True)
parser.add_argument("--angles", default="-60,-30,0,30,60")
parser.add_argument("--steps", type=int, default=3)
args = parser.parse_args()
if not 1 <= args.steps <= 4:
    raise ValueError("probe steps must be 1..4")
source, output = Path(args.run), Path(args.output)
meta = json.loads((source/"provenance.json").read_text())
if meta["split"] != "train":
    raise ValueError("physics diagnosis requires a training episode")
events = [json.loads(line) for line in (source/"trace.jsonl").read_text().splitlines()]
stall = next(row["payload"] for row in events if row["kind"] == "LOCAL_MOTION_RESOLVED"
             and row["payload"]["status"] == "VISUALLY_STALLED")
end_seq = int(stall["final_obs_id"].rsplit(":", 1)[1])
prefix = [row["payload"]["action"] for row in events if row["kind"] == "ACTION_COMMITTED"
          and row["payload"]["action_seq"] <= end_seq]
angles = [int(value) for value in args.angles.split(",")]
if len(angles) > 9 or any(abs(angle) > 180 for angle in angles):
    raise ValueError("invalid bounded heading list")
output.mkdir(parents=True, exist_ok=False)
hashes = archive_package_sources(output/"implementation")
(output/"probe_source.py").write_text(Path(__file__).read_text())
(output/"provenance.json").write_text(json.dumps({"source": str(source), "implementation_sha256": hashes,
                                               "angles": angles, "steps": args.steps}, indent=2))
episode = BenchmarkEpisode(make_config(meta["suite"], meta["split"], rgbd=True,
                                      episode_ids=[meta["episode_id"]]), rgbd=True)
results = []
try:
    params = calibration(episode.config)
    turn_angle = episode.config.SIMULATOR.TURN_ANGLE
    if any(angle % turn_angle for angle in angles):
        raise ValueError("headings must align with native turn increments")
    for angle in angles:
        task, obs = episode.reset()
        receipts = []
        def step(action):
            global obs
            before = obs["rgb"].astype(float)
            receipt, obs = episode.step(f"probe-{len(receipts)}", action)
            receipts.append(receipt)
            return float(np.mean(np.abs(obs["rgb"].astype(float)-before)))
        for action in prefix:
            step(action)
        for _ in range(abs(angle)//turn_angle):
            step("TURN_LEFT" if angle < 0 else "TURN_RIGHT")
        Image.fromarray(obs["rgb"]).save(output/f"heading_{angle}_before.png")
        probes = []
        for _ in range(args.steps):
            rays = heading_clearances(obs["depth"], **params)
            center = next(ray for ray in rays if ray["bearing_deg"] == 0)
            probes.append({"center_depth_before": center, "forward_rgb_change": step("MOVE_FORWARD")})
        Image.fromarray(obs["rgb"]).save(output/f"heading_{angle}_after.png")
        step("STOP")
        results.append({"relative_heading_deg": angle, "probes": probes, "actions": receipts,
                        "native_total_path_length": episode.evaluate()["metrics"]["path_length"]})
        (output/"summary.json").write_text(json.dumps({
            "kind": "fixed_heading_physics_diagnostic_not_navigation_evaluation",
            "source": str(source), "results": results}, indent=2))
        print(angle, results[-1]["native_total_path_length"],
              [round(row["forward_rgb_change"], 3) for row in probes], flush=True)
finally:
    episode.close()
