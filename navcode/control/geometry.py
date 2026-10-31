"""Sensor-only depth geometry diagnostic for a separate, explicit RGB-D track.

Uses camera intrinsics/extrinsics, never agent/world pose or navmesh. Clearances
are visible surface estimates, not a reachability guarantee. Candidate execution
still requires fresh depth checks after every turn and forward primitive.
"""
from __future__ import annotations

import math

import numpy as np


def heading_clearances(depth, *, hfov_deg, camera_height, agent_height, radius,
                       min_depth, max_depth, normalized=True, floor_horizon_m=3.0, lateral_margin_m=.03):
    z = np.asarray(depth, dtype=float).squeeze()
    if z.ndim != 2 or min(z.shape) < 2:
        raise ValueError("depth must be HxW or HxWx1")
    if not (0 < hfov_deg < 180 and 0 <= min_depth < max_depth and radius > 0):
        raise ValueError("invalid depth calibration")
    valid = np.isfinite(z)
    if normalized:
        valid &= (z >= 0) & (z <= 1)
        z = z * (max_depth - min_depth) + min_depth
    valid &= z > 0.01
    h, w = z.shape
    focal = (w / 2) / math.tan(math.radians(hfov_deg) / 2)
    u, v = np.meshgrid(np.arange(w) + 0.5, np.arange(h) + 0.5)
    x = (u - w / 2) * z / focal
    down = (v - h / 2) * z / focal
    # Sensor y is relative to the agent base, which need not coincide with the
    # rendered floor. Estimate the horizontal floor band from legal depth; do
    # not read simulator pose to compensate for navmesh/base offsets.
    candidates = valid & (v > h * .55) & (down > max(.3, camera_height - .4)) & (down < camera_height + .6)
    samples = down[candidates]
    floor_height = None
    if samples.size >= 24:
        bins = np.arange(max(.3, camera_height - .4), camera_height + .62, .02)
        histogram, bins = np.histogram(samples, bins=bins)
        index = int(histogram.argmax())
        band = candidates & (down >= bins[index]) & (down <= bins[index+1])
        ys, xs = np.where(band)
        if (len(xs) >= max(24, .1 * samples.size) and np.ptp(xs) >= w * .1
                and np.ptp(ys) >= h * .1):
            floor_height = float(np.median(down[band]))
    height = (floor_height if floor_height is not None else camera_height) - down
    obstacle = valid & (height > 0.15) & (height < agent_height + 0.10)
    floor = valid & (np.abs(height) <= 0.12) if floor_height is not None else np.zeros_like(valid)
    result = []
    for bearing in (-30, -15, 0, 15, 30):
        theta = math.radians(bearing)
        along = z * math.cos(theta) + x * math.sin(theta)
        across = x * math.cos(theta) - z * math.sin(theta)
        tube = (np.abs(across) <= radius + lateral_margin_m) & (along > 0.05)
        distances = along[tube & obstacle]
        clearance = float(np.min(distances)) if distances.size else None
        # No obstacle return is UNKNOWN, not infinite free space. Floor support
        # is reported separately so unseen gaps/stairs are not called reachable.
        supported = along[tube & floor & (along <= floor_horizon_m)]
        result.append({"bearing_deg": bearing, "visible_obstacle_clearance_m": clearance,
                       "estimated_camera_above_floor_m": floor_height,
                       "floor_support_pixels": int(supported.size),
                       "furthest_floor_support_m": float(supported.max()) if supported.size else None,
                       "forward_step_clearance_supported": bool(clearance is not None and clearance > 0.5
                                                                  and supported.size >= 8)})
    return result
