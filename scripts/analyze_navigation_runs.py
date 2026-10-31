"""Post-episode diagnostics. Private metrics never enter online agent context."""
import argparse
import json
from collections import Counter
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("paths", nargs="+")
parser.add_argument("--output", required=True)
args = parser.parse_args()
rows = []
for directory in map(Path, args.paths):
    candidates = [directory] if (directory/"result.json").exists() else sorted(p.parent for p in directory.glob("*/result.json"))
    for run in candidates:
        result = json.loads((run/"result.json").read_text())
        if not (run/"trace.jsonl").exists():
            continue
        events = [json.loads(line) for line in (run/"trace.jsonl").read_text().splitlines()]
        counts = Counter(e["kind"] for e in events)
        actions = Counter(e["payload"]["action"] for e in events if e["kind"] == "ACTION_COMMITTED")
        local_status = Counter(e["payload"]["status"] for e in events if e["kind"] == "LOCAL_MOTION_RESOLVED")
        m = result["metrics"]
        success = bool(m["success"]) and not result.get("forced_stop", False)
        failure = ("none" if success else "wrong_or_premature_stop" if not result.get("forced_stop", False)
                   else "infrastructure" if result["outcome"] == "INFRA_FAILURE"
                   else "budget" if result["outcome"] == "BUDGET_EXHAUSTED" else "program_or_repair")
        rows.append({"run": str(run), "suite": result["suite"], "episode_id": result["episode_id"],
                     "agent_success": success, "outcome": result["outcome"], "failure": failure,
                     "metrics": m, "actions": dict(actions), "local_motion_status": dict(local_status),
                     "transition_gate_rejections": counts["TRANSITION_EVIDENCE_REJECTED"],
                     "vision_tools": counts["VISION_TOOL"], "vision_tool_errors": counts["VISION_TOOL_ERROR"],
                     "perception_contracts": counts["PERCEPTION_REQUESTED"],
                     "program_exceptions": [e["payload"] for e in events if e["kind"] == "POLICY_EXCEPTION"],
                     "wall_time_s": result["wall_time_s"]})
output = {"kind": "post_episode_training_diagnostics_not_formal_ablation", "episodes": rows,
          "failure_counts": dict(Counter(row["failure"] for row in rows))}
Path(args.output).write_text(json.dumps(output, indent=2))
for row in rows:
    print(row["suite"], row["episode_id"], row["failure"],
          f"PL={row['metrics']['path_length']:.2f} NE={row['metrics']['distance_to_goal']:.2f} nDTW={row['metrics']['ndtw']:.3f}",
          row["local_motion_status"])
