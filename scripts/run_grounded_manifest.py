"""Run fixed training manifest entries without rewriting or silently resuming runs."""
import argparse
import hashlib
import json
import os
import statistics
import subprocess
import sys
from pathlib import Path

from navcode.artifacts.provenance import package_source_hashes, verify_package_sources

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--manifest", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--count", type=int, default=3)
parser.add_argument("--start", type=int, default=0)
parser.add_argument("--model", default="qwen3.8-omni-flash")
args = parser.parse_args()
manifest_path = Path(args.manifest)
manifest = json.loads(manifest_path.read_text())
if manifest["purpose"] != "development" or manifest["split"] != "train":
    raise ValueError("this development launcher does not permit held-out tuning")
if args.start < 0 or args.count <= 0 or args.start+args.count > len(manifest["episodes"]):
    raise ValueError("invalid manifest selection")
output = Path(args.output)
output.mkdir(parents=True, exist_ok=False)
selected = manifest["episodes"][args.start:args.start+args.count]
sources = package_source_hashes()
(output/"batch.json").write_text(json.dumps({
    "manifest": str(manifest_path), "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    "episodes": selected, "model": args.model, "source_sha256": sources,
    "parent_pid": os.getpid(), "purpose": "fixed_training_development_batch"}, indent=2))
results = []
for episode in selected:
    verify_package_sources(sources)
    episode_id = episode["episode_id"]
    destination = output/episode_id
    cmd = [sys.executable, "-m", "navcode.runners.grounded", "--suite", manifest["suite"],
           "--episode-id", episode_id, "--model", args.model, "--output", str(destination)]
    with (output/f"{episode_id}.log").open("w") as stream:
        process = subprocess.Popen(cmd, stdout=stream, stderr=subprocess.STDOUT, cwd=ROOT)
        (output/"current_process.json").write_text(json.dumps({"pid": process.pid, "episode_id": episode_id, "command": cmd}))
        code = process.wait()
    if code or not (destination/"result.json").exists():
        raise RuntimeError(f"episode {episode_id} process failed ({code}); inspect its log before restarting")
    result = json.loads((destination/"result.json").read_text())
    results.append({"episode_id": episode_id, "agent_success": result["agent_success"],
                    "outcome": result["outcome"], "forced_stop": result["forced_stop"],
                    "metrics": result["metrics"], "agent_actions": result["agent_actions"],
                    "wall_time_s": result["wall_time_s"], "policy_revisions": result["policy_revisions"]})
    summary = {"kind": "training_development_not_held_out", "suite": manifest["suite"],
               "model": args.model, "controller": result.get("agent_capabilities", {}).get("controller", "sensor_only_depth_guard_v1"), "sensor_track": "RGB-D",
               "completed": len(results), "planned": len(selected), "episodes": results,
               "agent_success_rate": statistics.mean(r["agent_success"] for r in results),
               "mean_native_spl": statistics.mean(r["metrics"]["spl"] for r in results),
               "mean_ndtw": statistics.mean(r["metrics"]["ndtw"] for r in results)}
    (output/"summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(results[-1]), flush=True)
