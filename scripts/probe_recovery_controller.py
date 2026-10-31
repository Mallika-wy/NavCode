"""Test generic sensor-selected recovery at a recorded training stall; no API."""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from navcode.benchmark import BenchmarkEpisode, make_config
from navcode.control.rgbd import DepthController, calibration, ground_candidates

parser = argparse.ArgumentParser()
parser.add_argument("run")
parser.add_argument("--output", required=True)
args = parser.parse_args()
run, output = Path(args.run), Path(args.output)
output.mkdir(parents=True, exist_ok=False)
meta = json.loads((run/"provenance.json").read_text())
events = [json.loads(l) for l in (run/"trace.jsonl").read_text().splitlines()]
stall = next(e["payload"] for e in events if e["kind"] == "LOCAL_MOTION_RESOLVED" and e["payload"]["status"] == "VISUALLY_STALLED")
seq = int(stall["final_obs_id"].rsplit(":", 1)[1])
prefix = [e["payload"]["action"] for e in events if e["kind"] == "ACTION_COMMITTED" and e["payload"]["action_seq"] <= seq]
ep = BenchmarkEpisode(make_config(meta["suite"], meta["split"], rgbd=True,
                                  episode_ids=[meta["episode_id"]]), rgbd=True)
log = []
try:
    task, obs = ep.reset()
    params = calibration(ep.config)
    def commit(op_id, action):
        global obs
        receipt, obs = ep.step(op_id, action)
        log.append({"kind": "ACTION_COMMITTED", "payload": receipt})
        return receipt
    def snapshot():
        obs_id = f"{ep.epoch}:{ep.broker.sequence}"
        candidates, _ = ground_candidates(obs["depth"], params, ep.config.SIMULATOR.TURN_ANGLE, obs_id)
        return {"obs_id": obs_id, "rgb": obs["rgb"], "depth": obs["depth"], "candidates": candidates}
    for i, action in enumerate(prefix):
        commit(f"prefix-{i}", action)
    Image.fromarray(obs["rgb"]).save(output/"before.png")
    ctl = DepthController(params, ep.config.SIMULATOR.TURN_ANGLE, ep.config.SIMULATOR.FORWARD_STEP_SIZE,
                          snapshot, commit, lambda kind, payload: log.append({"kind": kind, "payload": payload}))
    rounds = []
    for index in range(2):
        recovery = ctl.recover()
        current = snapshot()
        Image.fromarray(obs["rgb"]).save(output/f"after_recovery_{index}.png")
        selected = min(current["candidates"], key=lambda c: abs(c["bearing_deg"]), default=None)
        movement = (ctl.move(selected["candidate_id"], current["obs_id"], 3) if selected else
                    {"status": "NO_VISIBLE_GROUND", "nominal_commanded_advance_m": 0})
        rounds.append({"recovery": recovery, "route_probe": movement})
        Image.fromarray(obs["rgb"]).save(output/f"after_forward_{index}.png")
        if movement["status"] == "PARTIAL" and movement["nominal_commanded_advance_m"] >= .75:
            break
    commit("probe-stop", "STOP")
    report = {"kind": "generic_controller_recovery_probe_not_navigation_score", "source_run": str(run),
              "rounds": rounds, "native_total_path_length": ep.evaluate()["metrics"]["path_length"]}
    (output/"result.json").write_text(json.dumps(report, indent=2))
    (output/"trace.jsonl").write_text("\n".join(json.dumps(e) for e in log)+"\n")
    print(json.dumps(report, indent=2))
finally:
    ep.close()
