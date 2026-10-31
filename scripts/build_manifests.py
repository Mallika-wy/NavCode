"""Fix scene-balanced, trajectory-disjoint subsets without looking at outcomes."""
import gzip
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "third_party/VLN-CE/data/datasets"
OUTPUT = ROOT / "experiments/manifests"


def build(suite, split, count, seed=20261031):
    relative = (f"R2R_VLNCE_v1-3_preprocessed/{split}/{split}.json.gz" if suite == "r2r"
                else f"RxR_VLNCE_v0/{split}/{split}_guide.json.gz")
    path = DATA / relative
    with gzip.open(path, "rt") as stream:
        episodes = json.load(stream)["episodes"]
    rng = random.Random(seed)
    rng.shuffle(episodes)
    buckets = defaultdict(list)
    seen_trajectories = set()
    for episode in episodes:
        language = episode["instruction"].get("language") or "en"
        if suite == "rxr" and language not in ("en-US", "en-IN"):
            continue
        trajectory = str(episode["trajectory_id"])
        scene = Path(episode["scene_id"]).stem
        key = (scene, trajectory)
        if key in seen_trajectories:
            continue
        seen_trajectories.add(key)
        buckets[scene].append({"episode_id": str(episode["episode_id"]),
                               "trajectory_id": trajectory, "scene": scene,
                               "language": language})
    scenes = sorted(buckets)
    rng.shuffle(scenes)
    selected = []
    while len(selected) < count:
        progressed = False
        for scene in scenes:
            if buckets[scene]:
                selected.append(buckets[scene].pop())
                progressed = True
                if len(selected) == count:
                    break
        if not progressed:
            raise RuntimeError("not enough unique trajectories")
    result = {"suite": suite, "split": split, "seed": seed,
              "purpose": "development" if split == "train" else "held_out_do_not_tune",
              "selection": "seeded shuffle, one instruction per trajectory, scene round robin; no metrics used",
              "dataset": str(path.relative_to(ROOT)),
              "dataset_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "episodes": selected}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    target = OUTPUT / f"{suite}_{split}_{count}.json"
    if target.exists():
        if json.loads(target.read_text()) != result:
            raise RuntimeError("refusing to change existing manifest")
    else:
        target.write_text(json.dumps(result, indent=2))
    print(f"{target.name}: {len(selected)} trajectories, {len(set(e['scene'] for e in selected))} scenes")


if __name__ == "__main__":
    for suite in ("r2r", "rxr"):
        build(suite, "train", 12)
        build(suite, "val_unseen", 30)
