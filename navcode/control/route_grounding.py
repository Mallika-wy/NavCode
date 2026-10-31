"""Bind visual route intent to local RGB-D candidates, without global geometry."""
import math


from navcode.paths import PACKAGE_ROOT

ROUTE_GROUNDING_GUIDANCE = (PACKAGE_ROOT/"prompts/experimental/route_grounding.md").read_text()


def ground_route_intent(report, candidates, hfov_deg, turn_angle):
    """Resolve a visual bearing, not a world waypoint or a semantic truth test.

    Candidate headings are quantized by the track. Half one primitive plus
    three degrees allows rounding; anything farther needs another view.
    The local controller still checks every primitive from fresh depth.
    """
    result = dict(report)
    if report.get("verdict") == "SUPPORTED":
        result.update(target_candidate_id=None, route_grounding_status="NO_MOTION_NEEDED")
        return result
    anchor = report.get("route_anchor")
    valid = isinstance(anchor, dict) and isinstance(anchor.get("description"), str) and bool(anchor["description"].strip())
    xy = anchor.get("image_xy") if valid else None
    scale = {"normalized_01": 1, "normalized_1000": 1000}.get(anchor.get("coordinate_frame")) if valid else None
    valid = valid and scale is not None and isinstance(xy, list) and len(xy) == 2 and all(
        type(v) in (int, float) and math.isfinite(v) and 0 <= v <= scale for v in xy)
    if not valid:
        result.update(target_candidate_id=None, route_grounding_status="NO_VALID_CURRENT_ANCHOR")
        return result
    bearing = math.degrees(math.atan((2 * xy[0] / scale - 1) * math.tan(math.radians(hfov_deg) / 2)))
    result["route_anchor_bearing_deg"] = bearing
    nearest = min(candidates, key=lambda c: abs(c["bearing_deg"] - bearing), default=None)
    tolerance = turn_angle / 2 + 3
    if nearest is not None and abs(nearest["bearing_deg"] - bearing) <= tolerance:
        result.update(target_candidate_id=nearest["label"], route_grounding_status="DIRECTION_MATCHED")
    else:
        result.update(target_candidate_id=None, route_grounding_status="TURN_TO_ROUTE_FIRST")
        if abs(bearing) > 3:
            result["suggested_observation"] = "LEFT" if bearing < 0 else "RIGHT"
    return result
