import pytest
from navcode.agents import VisionAgent
from navcode.agents import validate_program


def report(**updates):
    result = {"verdict": "SUPPORTED", "evidence_obs_ids": ["f1"],
              "rationale_summary": "visible evidence", "target_bearing_deg": 0,
              "forward_clear": True, "suggested_observation": "NONE"}
    result.update(updates)
    return result


def test_rejects_claims_from_uninspected_or_other_episode_frames():
    with pytest.raises(ValueError, match="actually inspected"):
        VisionAgent.validate(report(evidence_obs_ids=["other-episode:0"]), {"f1"})


@pytest.mark.parametrize("updates", [{"forward_clear": "true"}, {"target_bearing_deg": float("nan")},
                                    {"target_bearing_deg": True}, {"verdict": "VERIFIED"}])
def test_rejects_unsafe_perception_schema(updates):
    with pytest.raises(ValueError):
        VisionAgent.validate(report(**updates), {"f1"})


def test_vision_agent_actively_retrieves_history_before_reporting():
    class API:
        model = "recorded-test-model"
        calls = []
        def generate(self, system, user, images, max_tokens):
            import json
            self.calls.append(list(images))
            value = ({"tool": "recall", "obs_ids": ["f1"], "reason": "compare doorway"}
                     if len(self.calls) == 1 else report(evidence_obs_ids=["f0", "f1"]))
            return {"text": json.dumps(value), "usage": {}}
    api = API()
    events = []
    agent = VisionAgent(api, {"current": "current.png", "old": "old.png"},
                        lambda *event: events.append(event), "epoch")
    contract = {"episode_epoch": "epoch", "current_obs_id": "current", "request_id": "r1",
                "policy_revision": 2, "max_visual_turns": 2}
    result = agent.investigate(contract, {"instruction": "cross the doorway"}, [])
    assert api.calls == [["current.png"], ["current.png", "old.png"]]
    assert result["investigation_turns"] == 2
    assert result["policy_revision"] == 2
    assert result["evidence_obs_ids"] == ["current", "old"]
    assert events[0][0] == "VISION_TOOL"


def test_program_must_keep_perception_in_a_local_decision_loop():
    with pytest.raises(ValueError, match="long-lived"):
        validate_program("def run(nav, state):\n    nav.perceive({})\n    return state")
    validate_program("def run(nav, state):\n    for i in range(2):\n        nav.perceive({})\n    return state")


def test_textual_route_memory_uses_frame_aliases_without_claiming_images_were_seen():
    import json
    class API:
        model = "recorded-test-model"
        def generate(self, system, user, images, max_tokens):
            context = json.loads(user)
            memory = context["contract"]["route_memory"]
            assert memory["latest_execution"]["source_obs_id"] == "f0"
            assert memory["recent_investigations"][0]["evidence_obs_ids"] == ["f0"]
            assert memory["recent_investigations"][0]["epistemic_status"] == "fallible_model_report_after_runtime_checks"
            assert context["image_ids_in_order"] == ["f1"]
            return {"text": json.dumps(report(evidence_obs_ids=["f1"])), "usage": {}}
    agent = VisionAgent(API(), {"epoch:0": "old.png", "epoch:1": "now.png"}, lambda *a: None, "epoch")
    contract = {"episode_epoch": "epoch", "current_obs_id": "epoch:1", "request_id": "r1",
                "policy_revision": 1, "max_visual_turns": 1,
                "route_memory": {"latest_execution": {"source_obs_id": "epoch:0"},
                                 "recent_investigations": [{"evidence_obs_ids": ["epoch:0"],
                                     "epistemic_status": "fallible_model_report_after_runtime_checks"}]}}
    result = agent.investigate(contract, {}, [])
    assert result["evidence_obs_ids"] == ["epoch:1"]


def test_bad_vision_tool_schema_is_repaired_in_vision_session():
    class API:
        model = "recorded-test-model"
        calls = 0
        def generate(self, system, user, images, max_tokens):
            import json
            self.calls += 1
            if self.calls == 1:
                value = {"tool": "crop", "obs_id": "f0", "box": [500, 300, 1000, 900]}
            else:
                assert "invalid crop bounds" in user
                value = report(evidence_obs_ids=["f0"], verdict="UNKNOWN", forward_clear=False)
            return {"text": json.dumps(value), "usage": {}}
    events = []
    agent = VisionAgent(API(), {"current": "no_image_read_required.png"},
                        lambda *e: events.append(e), "epoch")
    result = agent.investigate({"episode_epoch": "epoch", "current_obs_id": "current",
                                "request_id": "r", "policy_revision": 1, "max_visual_turns": 2}, {}, [])
    assert result["verdict"] == "UNKNOWN"
    assert events[0][0] == "VISION_TOOL_ERROR"
    assert len(agent.reports) == 1


def test_rejected_code_does_not_consume_a_policy_revision_or_execute_on_host(tmp_path):
    import json
    from navcode.agents import CodeAgent
    class API:
        calls = []
        def generate(self, system, user, **kwargs):
            self.calls.append(kwargs)
            source = ("def wrong(): pass" if len(self.calls) == 1 else
                      "raise RuntimeError('must never run on host')\n"
                      "def run(nav, state):\n    for i in range(2):\n        nav.perceive({})\n    return state")
            return {"text": json.dumps({"source": source})}
    api = API()
    agent = CodeAgent(api, tmp_path, image_provider=lambda: ["current_rgb.png"])
    with pytest.raises(ValueError, match="must define run"):
        agent.compile({}, {}, {}, [])
    assert agent.revision == 0 and agent.attempts == 1
    source = agent.compile({}, {}, {}, [], failure="invalid prior program")
    assert "must never run on host" in source
    assert agent.revision == 1 and agent.attempts == 2
    assert (tmp_path/"policy_v1.py").exists()
    assert api.calls[0]["images"] == []
    assert api.calls[1]["images"] == ["current_rgb.png"]
