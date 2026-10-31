import numpy as np
import pytest

from navcode.control.rgbd import DepthController, ground_candidates
from navcode.evidence.gates import transition_gate, check_stage_order
from navcode.runners.grounded import GroundedRun


PARAMS = dict(hfov_deg=90, camera_height=1.25, agent_height=1.5,
              radius=.1, min_depth=0, max_depth=10, normalized=False)


def floor_and_wall():
    down = (np.arange(100)[:, None]+.5-50)/50
    return np.broadcast_to(np.minimum(3., 1.4/np.maximum(.01, down)), (100, 100)).copy()


def test_candidates_are_visible_floor_patches_bound_to_actual_observation():
    candidates, _ = ground_candidates(floor_and_wall(), PARAMS, 15, "episode:0")
    assert candidates
    for c in candidates:
        assert c["obs_id"] == "episode:0"
        assert c["kind"] == "visible_ground_target"
        assert .5 < c["optical_depth_m"] < 2.9
        x, y = c["pixel_xy"]
        assert 0 < x < 1 and .5 < y < 1
    rxr, _ = ground_candidates(floor_and_wall(), PARAMS, 30, "episode:0")
    assert all(c["bearing_deg"] % 30 == 0 for c in rxr)
    next_candidates, _ = ground_candidates(floor_and_wall(), PARAMS, 15, "episode:1")
    assert candidates[0]["label"] == next_candidates[0]["label"]
    assert candidates[0]["candidate_id"] != next_candidates[0]["candidate_id"]


def test_narrow_clearance_uses_actual_body_radius_and_detects_center_obstacles():
    from navcode.control.geometry import heading_clearances
    params = dict(PARAMS, radius=.18)
    depth = floor_and_wall()
    depth[70:73, 73:76] = .5  # lateral x~=0.24m; outside 0.18m body + 0.03m margin
    old = heading_clearances(depth, **params, lateral_margin_m=.08)[2]
    current = heading_clearances(depth, **params)[2]
    assert old["visible_obstacle_clearance_m"] == pytest.approx(.5)
    assert current["visible_obstacle_clearance_m"] > 2
    depth[70:73, 49:52] = .5  # same obstacle in actual body corridor must still block
    blocked = heading_clearances(depth, **params)[2]
    assert blocked["visible_obstacle_clearance_m"] == pytest.approx(.5)


def test_stale_or_fabricated_target_never_commits_motion():
    state = {"obs_id": "now", "candidates": [], "depth": floor_and_wall()}
    actions = []
    controller = DepthController(PARAMS, 15, .25, lambda: state,
                                 lambda *a: actions.append(a), lambda *a: None)
    with pytest.raises(ValueError, match="stale"):
        controller.move("W1", "old", 4)
    with pytest.raises(ValueError, match="catalog"):
        controller.move("invented", "now", 4)
    assert actions == []


@pytest.mark.parametrize("bearing,expected", [(30, ["TURN_RIGHT", "TURN_RIGHT"]), (0, ["MOVE_FORWARD"])])
def test_guard_rechecks_new_depth_after_turn_and_each_forward(bearing, expected):
    state = {"obs_id": "e:0", "depth": floor_and_wall(),
             "rgb": np.zeros((10, 10, 3)), "candidates": [
                 {"candidate_id": "W1", "bearing_deg": bearing, "optical_depth_m": 1.7}]}
    actions = []
    def commit(op_id, action):
        actions.append(action)
        state["obs_id"] = "e:" + str(len(actions))
        # New sensor sees a close wall. The controller must NOT reuse old floor.
        state["depth"] = np.full((100, 100), .35)
        state["rgb"] = state["rgb"] + 1
        return {"action_seq": len(actions)}
    controller = DepthController(PARAMS, 15, .25, lambda: state, commit, lambda *a: None)
    result = controller.move("W1", "e:0", 4)
    assert actions == expected
    assert result["status"] == "DEPTH_BLOCKED_OR_UNKNOWN"
    assert result["final_obs_id"] == state["obs_id"]


@pytest.mark.parametrize("forwards,changed,ids,accepted", [
    (0, 0, ["a", "b"], False), (3, 0, ["a", "b"], False),
    (3, 2, ["b"], False), (3, 2, ["a", "b"], True)])
def test_transition_gate_requires_motion_and_comparison(forwards, changed, ids, accepted):
    report = {"verdict": "SUPPORTED", "evidence_obs_ids": ids, "rationale_summary": "test evidence"}
    contract = {"predicate_type": "TRANSITION", "stage_start_obs_id": "a", "current_obs_id": "b",
                "motion_since_stage": {"forward_commands": forwards, "forward_with_visual_change": changed}}
    result, reason = transition_gate(report, contract)
    assert (result["verdict"] == "SUPPORTED") == accepted
    assert (reason is None) == accepted
    assert report["verdict"] == "SUPPORTED"  # Original report is never overwritten.


def test_stage_cannot_be_skipped_on_scan_exhaustion_or_after_revoked_predecessor():
    check_stage_order("first", {}, {})
    with pytest.raises(ValueError, match="without accepted evidence"):
        check_stage_order("second", {"first": {}}, {})
    check_stage_order("second", {"first": {}}, {"first": "claim-1"})
    with pytest.raises(ValueError, match="first"):
        check_stage_order("second", {"first": {}, "second": {}}, {})


def test_old_room_image_cannot_prove_current_goal_proximity():
    report = {"verdict": "SUPPORTED", "evidence_obs_ids": ["old"], "rationale_summary": "near goal"}
    applied, reason = transition_gate(report, {"predicate_type": "SPATIAL", "current_obs_id": "now"})
    assert applied["verdict"] == "REFUTED"
    assert "current-frame" in reason


def test_identical_frame_loop_yields_to_code_agent_without_spending_another_vision_call():
    import time
    from types import SimpleNamespace as NS
    run = GroundedRun.__new__(GroundedRun)
    run.started = time.monotonic()
    run.wall_budget = 100
    run.episode = NS(ended=False)
    run.contracts, run.max_contracts = 0, 24
    run.stages, run.accepted_stages = {"S": {}}, {}
    run.current_obs = "frame"
    run.last_perception_key, run.idle_perceptions = ("S", "frame"), 3
    run.blocked_streak = 0
    run.coder = NS(revision=1)
    run.repair_triggered_revisions = set()
    events = []
    run.event = lambda *e: events.append(e)
    with pytest.raises(RuntimeError, match="NEEDS_REPLAN"):
        run.handle("perceive", {"contract": {"stage_id": "S", "predicate": "near rug",
                                             "task_span": "walk on rug", "predicate_type": "SPATIAL"}})
    assert events[0][0] == "NO_PROGRESS_REPAIR_REQUESTED"
    assert run.contracts == 0
    assert not run.episode.ended
    assert run.idle_perceptions == 0  # The repaired worker gets a chance to act.


def test_identical_stalled_view_is_not_retried_under_a_new_observation_handle():
    state = {"obs_id": "e:0", "depth": floor_and_wall(), "rgb": np.zeros((10, 10, 3)),
             "candidates": [{"candidate_id": "e:0/W1", "bearing_deg": 0, "optical_depth_m": 1.7}]}
    actions = []
    def commit(op_id, action):
        actions.append(action)
        state["obs_id"] = "e:1"
        state["candidates"] = [{"candidate_id": "e:1/W1", "bearing_deg": 0, "optical_depth_m": 1.7}]
        return {"action_seq": 1}
    controller = DepthController(PARAMS, 15, .25, lambda: state, commit, lambda *a: None)
    first = controller.move("e:0/W1", "e:0", 4)
    assert first["status"] == "VISUALLY_STALLED"
    again = controller.move("e:1/W1", "e:1", 4)
    assert again["status"] == "PREVIOUSLY_STALLED"
    assert actions == ["MOVE_FORWARD"]


def test_stalled_command_does_not_reset_no_progress_just_because_it_requested_distance():
    from types import SimpleNamespace as NS
    run = GroundedRun.__new__(GroundedRun)
    run.blocked_streak = 0
    run.route_memory = False
    run.controller = NS(move=lambda *a: {"status": "VISUALLY_STALLED", "nominal_commanded_advance_m": .25})
    run.handle("move_to_candidate", {"candidate_id": "target", "obs_id": "now"})
    run.handle("move_to_candidate", {"candidate_id": "target", "obs_id": "next"})
    assert run.blocked_streak == 2


def test_partial_progress_then_stall_is_not_reported_as_entirely_motionless():
    from types import SimpleNamespace as NS
    run = GroundedRun.__new__(GroundedRun)
    run.route_memory = False
    run.blocked_streak = 1
    run.controller = NS(move=lambda *a: {"status": "VISUALLY_STALLED", "nominal_commanded_advance_m": .5,
                                        "forward_with_visual_change": 1})
    run.handle("move_to_candidate", {"candidate_id": "target", "obs_id": "now"})
    assert run.blocked_streak == 0


def test_controller_records_partial_visual_progress_before_final_stall():
    state = {"obs_id": "e:0", "depth": floor_and_wall(), "rgb": np.zeros((10, 10, 3)),
             "candidates": [{"candidate_id": "e:0/W1", "bearing_deg": 0, "optical_depth_m": 1.7}]}
    actions = []
    def commit(op_id, action):
        actions.append(action)
        state["obs_id"] = "e:" + str(len(actions))
        if len(actions) == 1:
            state["rgb"] += 2
        return {"action_seq": len(actions)}
    controller = DepthController(PARAMS, 15, .25, lambda: state, commit, lambda *a: None)
    result = controller.move("e:0/W1", "e:0", 4)
    assert result["status"] == "VISUALLY_STALLED"
    assert result["forward_with_visual_change"] == 1
    assert result["nominal_commanded_advance_m"] == .5


def test_policy_cannot_tilt_camera_under_level_camera_geometry_assumption():
    run = GroundedRun.__new__(GroundedRun)
    with pytest.raises(ValueError, match="does not admit tilt"):
        run.handle("step", {"action": "LOOK_DOWN", "op_id": "tilt"})


def test_recovery_selects_clearer_rear_side_restores_heading_and_is_bounded(monkeypatch):
    import navcode.control.rgbd as module
    state = {"obs_id": "e:0", "rgb": np.zeros((10, 10, 3)), "depth": np.ones((10, 10)), "candidates": []}
    actions = []
    def commit(op_id, action):
        actions.append((op_id, action))
        state["obs_id"] = "e:" + str(len(actions))
        if action == "MOVE_FORWARD":
            state["rgb"] += 2
        return {"action_seq": len(actions)}
    rays = [{"bearing_deg": b, "visible_obstacle_clearance_m": 2 if b == -30 else 1,
             "floor_support_pixels": 0} for b in [-30, 0, 30]]
    monkeypatch.setattr(module, "heading_clearances", lambda *args, **kwargs: rays)
    controller = DepthController(PARAMS, 30, .25, lambda: state, commit, lambda *a: None)
    first = controller.recover()
    assert first["selected_rear_bearing_deg"] == -30
    assert first["floor_unobserved_during_probe"] and first["view_changed"]
    second = controller.recover()
    assert second["selected_rear_bearing_deg"] == 30
    assert second["forward_commands"] == 2
    count = len(actions)
    assert controller.recover()["status"] == "RECOVERY_LIMIT"
    assert len(actions) == count
    assert len({op for op, _ in actions}) == len(actions)
    assert sum(30 if action == "TURN_RIGHT" else -30 if action == "TURN_LEFT" else 0 for _, action in actions) == 0


def test_recovery_without_rear_clearance_never_commits_forward(monkeypatch):
    import navcode.control.rgbd as module
    state = {"obs_id": "e:0", "rgb": np.zeros((10, 10, 3)), "depth": np.ones((10, 10)), "candidates": []}
    actions = []
    def commit(op_id, action):
        actions.append(action)
        return {}
    monkeypatch.setattr(module, "heading_clearances", lambda *args, **kwargs: [
        {"bearing_deg": b, "visible_obstacle_clearance_m": .2, "floor_support_pixels": 0} for b in [-30, 0, 30]])
    controller = DepthController(PARAMS, 30, .25, lambda: state, commit, lambda *a: None)
    result = controller.recover()
    assert result["status"] == "NO_REAR_CLEARANCE"
    assert "MOVE_FORWARD" not in actions
    assert actions.count("TURN_LEFT") == actions.count("TURN_RIGHT")


def test_visible_floor_beyond_two_meters_can_support_one_short_step():
    # RxR regression: floor visible only at ~2.3m produced valid candidates,
    # while an inconsistent 2m guard horizon blocked every one of them.
    h, w = 480, 640
    focal = w/2/np.tan(np.deg2rad(79)/2)
    ray = (np.arange(h)[:, None]+.5-h/2)/focal
    depth = np.broadcast_to(np.minimum(5., 1.43/np.maximum(.01, ray)), (h, w)).copy()
    params = dict(PARAMS, hfov_deg=79, camera_height=.88, agent_height=.88, radius=.18)
    candidates, rays = ground_candidates(depth, params, 30, "e:0")
    center = next(r for r in rays if r["bearing_deg"] == 0)
    assert center["floor_support_pixels"] > 0
    assert candidates
    assert any(c["bearing_deg"] == 0 for c in candidates)
    assert center["forward_step_clearance_supported"]


@pytest.mark.parametrize("step_angle,degrees,expected", [(15, 60, 4), (30, -60, 2)])
def test_relative_view_turn_uses_track_angle_without_model_calls(step_angle, degrees, expected):
    from types import SimpleNamespace as NS
    run = GroundedRun.__new__(GroundedRun)
    run.episode = NS(config=NS(SIMULATOR=NS(TURN_ANGLE=step_angle)))
    run.look_counter = 0
    run.current_obs = "current"
    actions = []
    run.commit = lambda op_id, action: actions.append((op_id, action))
    receipt = run.handle("turn", {"degrees": degrees})
    assert len(actions) == expected
    assert all(a[1] == ("TURN_LEFT" if degrees < 0 else "TURN_RIGHT") for a in actions)
    assert receipt["degrees_committed"] == degrees
    with pytest.raises(ValueError):
        run.handle("turn", {"degrees": float("inf")})
    assert len(actions) == expected
