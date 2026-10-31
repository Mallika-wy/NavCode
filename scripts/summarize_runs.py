"""Summarize persisted API results; missing usage/cost stays unknown."""
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
totals = defaultdict(lambda: {"attempts": 0, "ok": 0, "errors": 0,
                              "reported_tokens": 0, "unknown_usage_attempts": 0})
for path in sorted((ROOT / "experiments").rglob("*.json")):
    data = json.loads(path.read_text())
    if not all(k in data for k in ("attempt", "status", "model")):
        continue
    row = totals[data["model"]]
    row["attempts"] += 1
    usable = data["status"] == "ok" and bool((data.get("text") or "").strip()) and data.get("finish_reason") != "length"
    row["ok" if usable else "errors"] += 1
    tokens = (data.get("usage") or {}).get("total_tokens")
    if tokens is None:
        row["unknown_usage_attempts"] += 1
    else:
        row["reported_tokens"] += tokens
report = {"models": dict(totals), "actual_cost_rmb": None,
          "note": "Reported token totals exclude calls with missing usage. Actual cost/remaining RMB unknown; API key alone does not supply management credentials."}
(ROOT / "experiments/api_usage_summary.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
