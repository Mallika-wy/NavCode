"""Inspect legal rear RGB-D candidates after a recorded training action prefix."""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from navcode.benchmark import BenchmarkEpisode, make_config
from navcode.control.rgbd import calibration, ground_candidates, annotate_candidates

parser = argparse.ArgumentParser()
parser.add_argument("run")
parser.add_argument("--output", required=True)
args = parser.parse_args()
run, output = Path(args.run), Path(args.output)
output.mkdir(parents=True, exist_ok=False)
metadata = json.loads((run/"provenance.json").read_text())
events = [json.loads(l) for l in (run/"trace.jsonl").read_text().splitlines()]
stall = next(e["payload"] for e in events if e["kind"] == "LOCAL_MOTION_RESOLVED" and e["payload"]["status"] == "VISUALLY_STALLED")
sequence = int(stall["final_obs_id"].rsplit(":", 1)[1])
prefix = [e["payload"]["action"] for e in events if e["kind"] == "ACTION_COMMITTED" and e["payload"]["action_seq"] <= sequence]
ep = BenchmarkEpisode(make_config(metadata["suite"], metadata["split"], rgbd=True,
                                  episode_ids=[metadata["episode_id"]]), rgbd=True)
try:
    task, obs = ep.reset()
    seq = 0
    def step(action):
        global seq, obs
        _, obs = ep.step(f"rear-probe-{seq}", action)
        seq += 1
    for action in prefix:
        step(action)
    Image.fromarray(obs["rgb"]).save(output/"before.png")
    for _ in range(round(180/ep.config.SIMULATOR.TURN_ANGLE)):
        step("TURN_RIGHT")
    candidates, rays = ground_candidates(obs["depth"], calibration(ep.config),
                                          ep.config.SIMULATOR.TURN_ANGLE, f"{ep.epoch}:{seq}")
    annotate_candidates(Image.fromarray(obs["rgb"]), candidates).save(output/"rear_candidates.png")
    np.save(output/"rear_depth.npy", obs["depth"])
    step("STOP")
    report = {"kind": "rear_sensor_inspection_not_navigation", "candidates": candidates, "rays": rays}
    (output/"result.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
finally:
    ep.close()
