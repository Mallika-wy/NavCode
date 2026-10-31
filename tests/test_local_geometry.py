import numpy as np
import pytest
from navcode.control.geometry import heading_clearances


def test_metric_and_normalized_depth_agree_and_center_wall_is_detected():
    wall = np.full((100, 100, 1), 0.35)
    params = dict(hfov_deg=90, camera_height=1.25, agent_height=1.5,
                  radius=0.1, min_depth=0, max_depth=10)
    metric = heading_clearances(wall, normalized=False, **params)
    normalized = heading_clearances(wall / 10, normalized=True, **params)
    assert metric == normalized
    center = metric[2]
    assert center["visible_obstacle_clearance_m"] == pytest.approx(0.35)
    assert not center["forward_step_clearance_supported"]


def test_missing_depth_is_unknown_rather_than_free_space():
    result = heading_clearances(np.full((10, 10), float("nan")), hfov_deg=90,
                                camera_height=1.25, agent_height=1.5, radius=.1,
                                min_depth=0, max_depth=10)
    assert all(r["visible_obstacle_clearance_m"] is None for r in result)
    assert not any(r["forward_step_clearance_supported"] for r in result)


def test_floor_is_estimated_from_depth_without_using_agent_world_pose():
    # Camera config is 1.25m above agent origin, rendered floor is 1.40m below
    # camera. Depth-only floor inference must handle the origin/floor offset.
    h = w = 100
    down_ray = (np.arange(h)[:, None] + .5 - h/2) / (w/2)
    depth = np.broadcast_to(1.4 / np.maximum(down_ray, .01), (h, w)).copy()
    result = heading_clearances(depth, hfov_deg=90, camera_height=1.25,
                                agent_height=1.5, radius=.1, min_depth=0,
                                max_depth=1000, normalized=False)
    assert result[2]["estimated_camera_above_floor_m"] == pytest.approx(1.4)
    assert result[2]["floor_support_pixels"] > 0
