"""Replay only pre-motion, model-generated initial policies for paired trials.

No result/metric file is read. Instruction, suite, compiler and initial RGB must
match, and the recorded policy must have been submitted before any movement.
"""
import hashlib
import json
from pathlib import Path

from PIL import Image

from navcode.agents.protocol import validate_program


def rgb_digest(path):
    with Image.open(path) as image:
        return hashlib.sha256(image.convert("RGB").tobytes()).hexdigest()


def load_initial_artifact(directory, task, initial_rgb, suite, code_model, split, episode_id):
    directory = Path(directory)
    provenance = json.loads((directory/"provenance.json").read_text())
    if (provenance.get("suite") != suite or provenance.get("code_model") != code_model
            or provenance.get("split") != split
            or str(provenance.get("episode_id")) != str(episode_id)
            or provenance.get("rgbd") is not True):
        raise ValueError("recorded suite/split/episode/compiler/sensor track does not match requested experiment")
    original_task = None
    submission = None
    with (directory/"trace.jsonl").open() as stream:
        for line in stream:
            event = json.loads(line)
            if event["kind"] == "EPISODE_START":
                original_task = event["payload"]
            if event["kind"] == "ACTION_COMMITTED":
                raise ValueError("initial artifact was preceded by committed motion")
            if event["kind"] == "POLICY_SUBMITTED":
                submission = event["payload"]
                break  # Never read later trajectories or evaluation outcomes.
    if submission is None or submission["revision"] != 1 or original_task is None:
        raise ValueError("no valid pre-motion initial policy")
    if any(original_task.get(k) != task.get(k) for k in ("instruction", "language")):
        raise ValueError("recorded instruction/language does not match current task")
    source = (directory/"policy_v1.py").read_text()
    if source != submission["source"]:
        raise ValueError("recorded source differs from submitted policy")
    if original_task["epoch"] in source:
        raise ValueError("recorded policy hardcodes original episode epoch")
    validate_program(source)
    digest = rgb_digest(initial_rgb)
    if digest != rgb_digest(directory/"frame_0000.png"):
        raise ValueError("initial RGB differs; refusing an unmatched paired trial")
    call = json.loads((directory/"code_calls_001.json").read_text())
    return {"source": source, "rationale": "paired replay of pre-motion model-generated policy",
            "origin": str(directory), "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "initial_rgb_sha256": digest, "original_compile_model": provenance["code_model"],
            "original_compile_usage": call.get("usage")}
