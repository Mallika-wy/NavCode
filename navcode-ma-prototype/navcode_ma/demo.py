import argparse
import json
from dataclasses import asdict
from pathlib import Path
from .supervisor import Supervisor
from .vision_agent import MockVisionAgent


def main():
    parser = argparse.ArgumentParser(description="Synthetic multi-agent Code-as-Policies demo")
    parser.add_argument("--output", default="runs/demo")
    parser.add_argument("--inject-uncertain-goal", action="store_true")
    args = parser.parse_args()
    supervisor = Supervisor(vision_agent=MockVisionAgent(args.inject_uncertain_goal))
    result = supervisor.run_episode()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    supervisor.memory.export(out / "trace.jsonl")
    (out / "result.json").write_text(json.dumps(asdict(result), indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(asdict(result), indent=2, ensure_ascii=False))
    print(f"Trace: {out / 'trace.jsonl'}")


if __name__ == "__main__":
    main()
