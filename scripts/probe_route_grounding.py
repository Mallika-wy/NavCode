"""Re-investigate saved training observations; never report navigation scores."""
import argparse
import json
from pathlib import Path

from navcode.agents import parse_json
from navcode.agents.prompts import GROUNDED_VISION_FINAL
from navcode.models.api import ModelAPI
from navcode.control.route_grounding import ROUTE_GROUNDING_GUIDANCE, ground_route_intent


parser = argparse.ArgumentParser()
parser.add_argument("run")
parser.add_argument("--attempts", default="6,7,8")
parser.add_argument("--output", required=True)
parser.add_argument("--model", default="qwen3.8-omni-flash")
args = parser.parse_args()
root, output = Path(args.run), Path(args.output)
provenance = json.loads((root/"provenance.json").read_text())
if provenance["split"] != "train":
    raise ValueError("diagnostic tuning requires training observations")
output.mkdir(parents=True, exist_ok=False)
requests = [json.loads(line) for line in (root/"vision_calls.jsonl").read_text().splitlines()]
attempts = [int(n) for n in args.attempts.split(",")]
api = ModelAPI(args.model, output/"vision_calls.jsonl", max_calls=len(attempts),
               json_output=args.model.startswith("qwen3.8-max"))
summary = []
for attempt in attempts:
    original = next(row for row in requests if row["attempt"] == attempt)
    context = json.loads(original["user"])
    context["remaining_turns"] = 1
    contract = context["contract"]
    response = api.generate(GROUNDED_VISION_FINAL + ROUTE_GROUNDING_GUIDANCE,
                            json.dumps(context), original["images"], max_tokens=1000)
    report = parse_json(response["text"])
    # Constants are native public track intrinsics, not oracle state.
    hfov, turn = (79, 30) if provenance["suite"] == "rxr" else (90, 15)
    candidates = [dict(c, label=c.get("label", c["candidate_id"])) for c in contract["candidates"]]
    applied = ground_route_intent(report, candidates, hfov, turn)
    summary.append({"original_attempt": attempt, "current_image_alias": contract["current_obs_id"],
                    "predicate": contract["predicate"], "report": report, "grounded": applied})
    (output/"summary.json").write_text(json.dumps({
        "kind": "training_observation_probe_not_navigation_evaluation", "source": str(root),
        "results": summary}, indent=2))
    print(json.dumps(summary[-1]), flush=True)
