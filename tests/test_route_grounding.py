import pytest

from navcode.control.route_grounding import ground_route_intent


def report(xy, **fields):
    return dict(verdict="REFUTED", target_candidate_id="W1", suggested_observation="NONE",
                route_anchor={"description": "opening leading along the route", "coordinate_frame": "normalized_01", "image_xy": xy}, **fields)


def test_side_opening_cannot_be_grounded_to_a_dot_facing_the_wall():
    source = report([.08, .55])
    result = ground_route_intent(source, [{"label": "W1", "bearing_deg": 0}], 79, 30)
    assert result["target_candidate_id"] is None
    assert result["suggested_observation"] == "LEFT"
    assert result["route_grounding_status"] == "TURN_TO_ROUTE_FIRST"
    assert source["target_candidate_id"] == "W1"


def test_route_direction_selects_matching_current_candidate_instead_of_wrong_label():
    result = ground_route_intent(report([.2, .7]), [
        {"label": "W1", "bearing_deg": 0}, {"label": "W2", "bearing_deg": -30}], 90, 30)
    assert result["target_candidate_id"] == "W2"
    assert result["route_grounding_status"] == "DIRECTION_MATCHED"


@pytest.mark.parametrize("xy", [None, [], [float("nan"), .7], [True, .7], [-.1, .7], [300, 400]])
def test_invalid_or_non_normalized_anchor_never_enables_motion(xy):
    result = ground_route_intent(report(xy), [{"label": "W1", "bearing_deg": 0}], 79, 30)
    assert result["target_candidate_id"] is None


def test_empty_catalog_is_not_a_reachable_waypoint():
    result = ground_route_intent(report([.8, .6]), [], 90, 15)
    assert result["target_candidate_id"] is None and result["suggested_observation"] == "RIGHT"


def test_coordinate_system_is_explicit_and_not_guessed_from_value_range():
    source = report([80, 550])
    source["route_anchor"]["coordinate_frame"] = "normalized_1000"
    result = ground_route_intent(source, [{"label": "W1", "bearing_deg": 0}], 79, 30)
    assert result["suggested_observation"] == "LEFT"
    assert result["route_anchor_bearing_deg"] < -30
    source["route_anchor"].pop("coordinate_frame")
    assert ground_route_intent(source, [], 79, 30)["route_grounding_status"] == "NO_VALID_CURRENT_ANCHOR"


def test_semantic_completion_is_not_changed_by_motion_grounding():
    result = ground_route_intent({"verdict": "SUPPORTED", "target_candidate_id": "W1"}, [], 90, 15)
    assert result["verdict"] == "SUPPORTED" and result["target_candidate_id"] is None
