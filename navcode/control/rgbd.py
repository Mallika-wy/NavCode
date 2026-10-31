"""RGB-D local controller. All motion still goes through the sole ActionBroker.

Targets are bound to the actual observation. Every turn and forward primitive
causes fresh depth validation. No GPS, navmesh query, shortest-path or world pose.
"""
from __future__ import annotations

import math
import hashlib

import numpy as np
from PIL import ImageDraw

from navcode.control.geometry import heading_clearances


def calibration(config):
    sim = config.SIMULATOR
    depth, rgb = sim.DEPTH_SENSOR, sim.RGB_SENSOR
    if depth.HFOV != rgb.HFOV or tuple(depth.POSITION) != tuple(rgb.POSITION):
        raise ValueError("controller requires co-located RGB-D cameras with matching HFOV")
    if tuple(depth.ORIENTATION) != (0., 0., 0.) or tuple(rgb.ORIENTATION) != (0., 0., 0.):
        raise ValueError("level RGB-D camera required for this controller")
    if abs(depth.WIDTH / depth.HEIGHT - rgb.WIDTH / rgb.HEIGHT) > .001:
        raise ValueError("RGB-D aspect ratios must agree")
    return dict(hfov_deg=depth.HFOV, camera_height=depth.POSITION[1],
                agent_height=sim.AGENT_0.HEIGHT, radius=sim.AGENT_0.RADIUS,
                min_depth=depth.MIN_DEPTH, max_depth=depth.MAX_DEPTH,
                normalized=depth.NORMALIZE_DEPTH)


def ground_candidates(depth, params, turn_angle, obs_id):
    """Project visible floor targets; blocked rays cannot produce targets."""
    clearances = heading_clearances(depth, **params)
    h, w = np.asarray(depth).squeeze().shape
    focal = w / 2 / math.tan(math.radians(params["hfov_deg"]) / 2)
    z = np.asarray(depth, dtype=float).squeeze()
    if params["normalized"]:
        z = z * (params["max_depth"] - params["min_depth"]) + params["min_depth"]
    u, v = np.meshgrid(np.arange(w)+.5, np.arange(h)+.5)
    down = (v-h/2) * z / focal
    bearing = np.degrees(np.arctan((u-w/2) / focal))
    candidates = []
    for ray in clearances:
        angle = ray["bearing_deg"]
        if abs(angle / turn_angle - round(angle / turn_angle)) > .001:
            continue
        floor_height = ray["estimated_camera_above_floor_m"]
        clearance = ray["visible_obstacle_clearance_m"]
        if floor_height is None:
            continue
        limit = min(2.5, clearance - params["radius"] - .10) if clearance is not None else 2.5
        valid = (np.isfinite(z) & (z > .5) & (z < limit)
                 & (np.abs(down-floor_height) < .10) & (np.abs(bearing-angle) <= 3))
        ys, xs = np.where(valid)
        if len(xs) < 8:
            continue
        # Prefer a 1.7m visible floor patch. It is a target, not a guarantee
        # that the full segment is traversable; controller rechecks per step.
        distances = z[ys, xs]
        idx = int(np.argmin(np.abs(distances - 1.7)))
        py, px = int(ys[idx]), int(xs[idx])
        label = f"W{len(candidates)+1}"
        candidates.append({"candidate_id": f"{obs_id}/{label}", "label": label, "obs_id": obs_id,
                           "bearing_deg": angle, "optical_depth_m": float(z[py, px]),
                           "pixel_xy": [(px+.5)/w, (py+.5)/h], "coordinate_frame": "normalized_rgb",
                           "kind": "visible_ground_target", "clearance_m": clearance})
    return candidates, clearances


def annotate_candidates(image, candidates):
    result = image.copy()
    draw = ImageDraw.Draw(result)
    w, h = result.size
    for candidate in candidates:
        x, y = candidate["pixel_xy"]
        x, y = int(x*w), int(y*h)
        draw.ellipse((x-6, y-6, x+6, y+6), fill="yellow", outline="black", width=2)
        draw.text((x+7, y-10), candidate.get("label", candidate["candidate_id"]), fill="black", stroke_width=2, stroke_fill="yellow")
    return result


class DepthController:
    def __init__(self, params, turn_angle, forward_step, snapshot, commit, event):
        self.params, self.turn_angle, self.forward_step = params, turn_angle, forward_step
        self.snapshot, self.commit, self.event = snapshot, commit, event
        self.moves = 0
        self.failed_views = set()
        self.recoveries = 0
        self.recovery_side = None

    def recover(self):
        """Policy-requested, bounded backoff probe; never asserts reachability.

        A close rear wall can occlude the floor. In that case depth clearance
        permits only one short exploratory step, not a claim of free ground.
        A second attempt alternates a viable side and may take two short steps.
        """
        start = self.snapshot()
        if self.recoveries >= 2:
            return {"status": "RECOVERY_LIMIT", "purpose": "collision_recovery",
                    "actions_committed": 0, "view_changed": False,
                    "final_obs_id": start["obs_id"]}
        self.recoveries += 1
        op = f"recover-{self.recoveries}"
        action_count = 0
        heading = 0.
        def turn(degrees, phase):
            nonlocal action_count, heading
            count = round(abs(degrees)/self.turn_angle)
            for i in range(count):
                self.commit(f"{op}-{phase}-{i}", "TURN_RIGHT" if degrees > 0 else "TURN_LEFT")
                action_count += 1
                heading += self.turn_angle if degrees > 0 else -self.turn_angle
        before = np.array(start["rgb"], dtype=float, copy=True)
        turn(180, "rear")
        rear = self.snapshot()
        rays = heading_clearances(rear["depth"], **self.params)
        minimum = self.forward_step + self.params["radius"] + .10
        options = [r for r in rays if abs(r["bearing_deg"]) == 30
                   and r["visible_obstacle_clearance_m"] is not None
                   and r["visible_obstacle_clearance_m"] > minimum]
        options.sort(key=lambda r: r["visible_obstacle_clearance_m"], reverse=True)
        if self.recovery_side is not None and len(options) > 1:
            options.sort(key=lambda r: r["bearing_deg"] == self.recovery_side)
        selected = options[0] if options else None
        forward_commands = 0
        floor_unknown = False
        status = "NO_REAR_CLEARANCE"
        if selected is not None:
            self.recovery_side = selected["bearing_deg"]
            turn(self.recovery_side, "side")
            for i in range(self.recoveries):
                now = self.snapshot()
                center = next(r for r in heading_clearances(now["depth"], **self.params) if r["bearing_deg"] == 0)
                clearance = center["visible_obstacle_clearance_m"]
                if clearance is None or clearance <= minimum:
                    status = "REAR_DEPTH_BLOCKED"
                    break
                floor_unknown |= center["floor_support_pixels"] < 8
                image = np.array(now["rgb"], dtype=float, copy=True)
                self.commit(f"{op}-backoff-{i}", "MOVE_FORWARD")
                action_count += 1
                forward_commands += 1
                change = float(np.mean(np.abs(np.asarray(self.snapshot()["rgb"], dtype=float)-image)))
                if change < .2:
                    status = "REAR_VISUALLY_STALLED"
                    break
                status = "BACKOFF_PROBED"
        turn(-heading, "restore")
        changed = float(np.mean(np.abs(np.asarray(self.snapshot()["rgb"], dtype=float)-before))) >= .2
        result = {"status": status, "purpose": "collision_recovery", "attempt": self.recoveries,
                  "selected_rear_bearing_deg": selected["bearing_deg"] if selected else None,
                  "rear_clearances": rays, "floor_unobserved_during_probe": floor_unknown,
                  "forward_commands": forward_commands, "actions_committed": action_count,
                  "view_changed": bool(changed), "relative_turn_command_deg": heading,
                  "source_obs_id": start["obs_id"], "final_obs_id": self.snapshot()["obs_id"]}
        self.event("LOCAL_RECOVERY_RESOLVED", result)
        return result

    def move(self, candidate_id, obs_id, max_steps):
        if type(max_steps) is not int or not 1 <= max_steps <= 8:
            raise ValueError("max_steps must be 1..8")
        current = self.snapshot()
        if obs_id != current["obs_id"]:
            raise ValueError("stale ground target observation")
        candidate = next((c for c in current["candidates"] if c["candidate_id"] == candidate_id), None)
        if candidate is None:
            raise ValueError("candidate not in current sensor-derived catalog")
        view_hash = hashlib.sha256(np.asarray(current["rgb"], dtype=np.uint8).tobytes() +
                                   np.round(np.asarray(current["depth"], dtype=np.float32), 4).tobytes()).hexdigest()
        failed_key = (view_hash, candidate["bearing_deg"])
        if failed_key in self.failed_views:
            result = {"status": "PREVIOUSLY_STALLED", "source_obs_id": obs_id,
                      "candidate_id": candidate_id, "final_obs_id": current["obs_id"],
                      "actions_committed": 0, "nominal_commanded_advance_m": 0.}
            self.event("LOCAL_MOTION_RESOLVED", result)
            return result
        self.moves += 1
        move_id = f"local-{self.moves}"
        committed = []
        angle = candidate["bearing_deg"]
        n_turns = round(abs(angle) / self.turn_angle)
        for i in range(n_turns):
            action = "TURN_RIGHT" if angle > 0 else "TURN_LEFT"
            committed.append(self.commit(f"{move_id}-turn-{i}", action))
            # Snapshot re-computes the catalog from the NEW actual RGB-D frame.
            self.snapshot()
        status = "PARTIAL"
        nominal_advance = 0.
        forward_visual_progress = False
        forward_with_visual_change = 0
        target_distance = candidate["optical_depth_m"] / max(.5, math.cos(math.radians(angle)))
        steps = min(max_steps, max(1, int(target_distance / self.forward_step)))
        for i in range(steps):
            now = self.snapshot()
            rays = heading_clearances(now["depth"], **self.params)
            center = next(r for r in rays if r["bearing_deg"] == 0)
            clearance = center["visible_obstacle_clearance_m"]
            minimum = self.forward_step + self.params["radius"] + .10
            if center["floor_support_pixels"] < 8 or (clearance is not None and clearance <= minimum):
                status = "DEPTH_BLOCKED_OR_UNKNOWN"
                break
            before = np.array(now["rgb"], dtype=float, copy=True)
            receipt = self.commit(f"{move_id}-forward-{i}", "MOVE_FORWARD")
            committed.append(receipt)
            nominal_advance += self.forward_step
            after = np.asarray(self.snapshot()["rgb"], dtype=float)
            # A zero image change is strong evidence of no progress. A nonzero
            # change is NOT treated as a measurement of physical displacement.
            image_change = float(np.mean(np.abs(after-before)))
            if image_change < .2:
                status = "VISUALLY_STALLED"
                if not forward_visual_progress:
                    self.failed_views.add(failed_key)
                break
            forward_visual_progress = True
            forward_with_visual_change += 1
        result = {"status": status, "source_obs_id": obs_id, "candidate_id": candidate_id,
                  "final_obs_id": self.snapshot()["obs_id"], "actions_committed": len(committed),
                  "nominal_commanded_advance_m": nominal_advance,
                  "forward_with_visual_change": forward_with_visual_change}
        self.event("LOCAL_MOTION_RESOLVED", result)
        return result
