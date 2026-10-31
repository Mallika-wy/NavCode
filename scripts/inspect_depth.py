"""Save calibrated, sensor-only clearance diagnostics from a real RGB-D smoke."""
import argparse
import json
from pathlib import Path

import numpy as np
import yaml

from navcode.control.geometry import heading_clearances

parser = argparse.ArgumentParser()
parser.add_argument("directory")
args = parser.parse_args()
directory = Path(args.directory)
result = json.loads((directory / "result.json").read_text())
if result["capabilities"]["sensor_track"] != "RGB-D":
    raise ValueError("depth diagnostic requires explicitly labeled RGB-D track")
cfg = yaml.safe_load(result["capabilities"]["resolved_config"])["SIMULATOR"]
sensor = cfg["DEPTH_SENSOR"]
params = dict(hfov_deg=sensor["HFOV"], camera_height=sensor["POSITION"][1],
              agent_height=cfg["AGENT_0"]["HEIGHT"], radius=cfg["AGENT_0"]["RADIUS"],
              min_depth=sensor["MIN_DEPTH"], max_depth=sensor["MAX_DEPTH"],
              normalized=sensor["NORMALIZE_DEPTH"])
diagnostic = {"kind": "visible_depth_geometry_not_reachability_or_navigation_result",
              "calibration": params,
              "headings": heading_clearances(np.load(directory / "initial_depth.npy"), **params)}
(directory / "depth_clearances.json").write_text(json.dumps(diagnostic, indent=2))
print(json.dumps(diagnostic, indent=2))
