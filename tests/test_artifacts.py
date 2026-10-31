import json
from types import SimpleNamespace as NS

import pytest
from PIL import Image

from navcode.artifacts.initial_policy import load_initial_artifact
from navcode.agents import CodeAgent


SOURCE = "def run(nav, state):\n    for i in range(2):\n        nav.perceive({})\n    return state\n"


def recording(tmp_path, *, motion_before=False):
    root = tmp_path/"original"
    root.mkdir()
    (root/"provenance.json").write_text(json.dumps({"suite": "r2r", "split": "train", "episode_id": "123", "rgbd": True, "code_model": "compiler"}))
    events = [{"kind": "EPISODE_START", "payload": {"instruction": "walk into room", "language": "en", "epoch": "original-epoch"}}]
    if motion_before:
        events.append({"kind": "ACTION_COMMITTED", "payload": {}})
    events.append({"kind": "POLICY_SUBMITTED", "payload": {"revision": 1, "source": SOURCE}})
    (root/"trace.jsonl").write_text("\n".join(map(json.dumps, events)) + "\n")
    (root/"policy_v1.py").write_text(SOURCE)
    (root/"code_calls_001.json").write_text(json.dumps({"usage": {"total_tokens": 100}}))
    Image.new("RGB", (10, 10), "white").save(root/"frame_0000.png")
    return root


def test_recording_matches_task_and_frame_without_reading_any_results(tmp_path):
    root = recording(tmp_path)
    task = {"instruction": "walk into room", "language": "en", "epoch": "new-epoch"}
    artifact = load_initial_artifact(root, task, root/"frame_0000.png", "r2r", "compiler", "train", "123")
    assert artifact["source"] == SOURCE
    assert artifact["original_compile_usage"] == {"total_tokens": 100}
    assert not (root/"result.json").exists()
    with pytest.raises(ValueError, match="instruction"):
        load_initial_artifact(root, dict(task, instruction="different"), root/"frame_0000.png", "r2r", "compiler", "train", "123")
    changed = tmp_path/"changed.png"
    Image.new("RGB", (10, 10), "black").save(changed)
    with pytest.raises(ValueError, match="initial RGB"):
        load_initial_artifact(root, task, changed, "r2r", "compiler", "train", "123")
    with pytest.raises(ValueError, match="episode"):
        load_initial_artifact(root, task, root/"frame_0000.png", "r2r", "compiler", "train", "456")


def test_repaired_or_motion_conditioned_policy_cannot_be_initial_cache(tmp_path):
    root = recording(tmp_path, motion_before=True)
    with pytest.raises(ValueError, match="preceded by committed motion"):
        load_initial_artifact(root, {"instruction": "walk into room", "language": "en"},
                              root/"frame_0000.png", "r2r", "compiler", "train", "123")


def test_cached_source_keeps_sandbox_path_and_does_not_fake_a_new_api_call(tmp_path):
    class API:
        calls = 0
        def generate(self, *args, **kwargs):
            self.calls += 1
            return {"text": json.dumps({"source": SOURCE})}
    api = API()
    agent = CodeAgent(api, tmp_path, recorded_initial={"source": SOURCE, "rationale": "recorded"})
    assert agent.compile({}, {}, {}, []) == SOURCE
    assert agent.attempts == 0 and api.calls == 0 and agent.revision == 1
    assert agent.submission_origin == "recorded_initial_model_artifact"
    agent.compile({}, {}, {}, [], failure="needs repair")
    assert api.calls == 1 and agent.attempts == 1 and agent.revision == 2
    assert (tmp_path/"policy_v2.py").exists()
