import json

import pytest

from navcode.agents.code import CodeAgent
from navcode.agents.vision import VisionAgent
from navcode.paths import PACKAGE_ROOT
from navcode.skills.registry import SkillRegistry


SOURCE = 'def run(nav, state):\n    state.setdefault("failed_handles", [])\n    for i in range(2):\n        nav.perceive({})\n    return state\n'


def test_role_catalog_and_resource_paths_are_allowlisted(tmp_path):
    vision = SkillRegistry(PACKAGE_ROOT/"skills", "vision")
    assert "route-following" in {r["name"] for r in vision.catalog()}
    for name in ("policy-writing", "../../.env", None):
        with pytest.raises(ValueError, match="authorized"):
            vision.read(name)
    root=tmp_path/"skills"
    root.mkdir()
    (tmp_path/"outside.md").write_text("not an authorized resource")
    (root/"catalog.json").write_text(json.dumps({"version":1,"skills":[{
        "name":"bad", "roles":["vision"], "description":"bad path", "entry":"../outside.md"}]}))
    with pytest.raises(ValueError, match="invalid skill resource"):
        SkillRegistry(root,"vision").read("bad")


def test_code_skill_read_is_counted_as_a_model_call_without_creating_a_revision(tmp_path):
    class API:
        calls=0
        def generate(self, system, user, **kwargs):
            self.calls += 1
            context=json.loads(user)
            names={s["name"] for s in context["loaded_skills"]}
            assert "policy-writing" in names
            if self.calls == 1:
                return {"text":json.dumps({"tool":"read_skill","name":"verification"})}
            assert "verification" in names
            return {"text":json.dumps({"source":SOURCE})}
    events=[]
    api=API()
    agent=CodeAgent(api,tmp_path,skills=SkillRegistry(PACKAGE_ROOT/"skills","code",lambda *e:events.append(e)))
    assert agent.compile({}, {}, {}, []) == SOURCE
    assert api.calls == agent.attempts == 2 and agent.revision == 1
    assert not (tmp_path/"policy_v2.py").exists()
    assert [e[1]["name"] for e in events] == ["policy-writing","verification"]


def test_repair_loads_state_migration_guidance_for_a_nonempty_checkpoint(tmp_path):
    class API:
        def generate(self, system, user, **kwargs):
            context=json.loads(user)
            assert context["state"] == {"stage":1}
            assert {s["name"] for s in context["loaded_skills"]} == {"policy-writing","state-repair"}
            return {"text":json.dumps({"source":SOURCE})}
    agent=CodeAgent(API(),tmp_path,skills=SkillRegistry(PACKAGE_ROOT/"skills","code"))
    agent.compile({}, {}, {"stage":1}, [], failure="KeyError: failed_handles")
    assert agent.revision == 1 and agent.attempts == 1


def test_last_code_call_is_reserved_for_source_and_exhaustion_does_not_inflate_usage(tmp_path):
    class API:
        max_calls=1
        calls_used=0
        def generate(self,system,user,**kwargs):
            assert json.loads(user)["skill_reads_open"] is False
            self.calls_used += 1
            return {"text":json.dumps({"source":SOURCE})}
    api=API()
    agent=CodeAgent(api,tmp_path,skills=SkillRegistry(PACKAGE_ROOT/"skills","code"))
    agent.compile({}, {}, {}, [])
    with pytest.raises(RuntimeError,match="call budget"):
        agent.compile({}, {}, {}, [],failure="another repair")
    assert api.calls_used == agent.attempts == 1


def test_skill_guidance_does_not_expand_vision_turn_or_image_permissions():
    class API:
        model="test"
        calls=0
        def generate(self,system,user,images,max_tokens):
            self.calls += 1
            context=json.loads(user)
            assert images == ["current.png"] and context["image_ids_in_order"] == ["f0"]
            if self.calls==1:
                return {"text":json.dumps({"tool":"read_skill","name":"verification"}),"usage":{}}
            assert "verification" in {s["name"] for s in context["loaded_skills"]}
            return {"text":json.dumps({"verdict":"REFUTED","evidence_obs_ids":["f0"],
                "rationale_summary":"not yet inside", "target_bearing_deg":None,
                "forward_clear":False,"suggested_observation":"LEFT"}),"usage":{}}
    api=API()
    agent=VisionAgent(api,{"epoch:0":"current.png"},lambda *e:None,"epoch",
                      skills=SkillRegistry(PACKAGE_ROOT/"skills","vision"))
    result=agent.investigate({"episode_epoch":"epoch","current_obs_id":"epoch:0",
                              "request_id":"r","policy_revision":1,"max_visual_turns":2}, {}, [])
    assert result["investigation_turns"] == api.calls == 2
    assert result["evidence_obs_ids"] == ["epoch:0"]


def test_blocked_feedback_loads_relevant_guidance_without_an_extra_model_call():
    class API:
        model="test"
        calls=0
        def generate(self,system,user,images,max_tokens):
            self.calls += 1
            assert {s["name"] for s in json.loads(user)["loaded_skills"]} == {"route-following","blocked-motion"}
            return {"text":json.dumps({"verdict":"UNKNOWN","evidence_obs_ids":["f0"],
                "rationale_summary":"need a new view","target_bearing_deg":None,
                "forward_clear":False,"suggested_observation":"LEFT"}),"usage":{}}
    api=API()
    agent=VisionAgent(api,{"epoch:0":"current.png"},lambda *e:None,"epoch",
                      skills=SkillRegistry(PACKAGE_ROOT/"skills","vision"))
    agent.investigate({"episode_epoch":"epoch","current_obs_id":"epoch:0",
                       "request_id":"r","policy_revision":1,"max_visual_turns":1,
                       "local_motion_feedback":{"status":"VISUALLY_STALLED"}}, {}, [])
    assert api.calls == 1
