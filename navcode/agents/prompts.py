"""Load versioned role prompts from reviewable Markdown resources."""
from navcode.paths import PACKAGE_ROOT


def _prompt(name):
    return (PACKAGE_ROOT/"prompts"/name).read_text()


CODE_SYSTEM = _prompt("legacy/code_rgb.md")
VISION_SYSTEM = _prompt("legacy/vision_rgb.md")
VISION_FINAL_SYSTEM = _prompt("legacy/vision_rgb_final.md")
GROUNDED_CODE_SYSTEM = _prompt("legacy/code_rgbd.md")
GROUNDED_VISION_SYSTEM = _prompt("legacy/vision_rgbd.md")
GROUNDED_VISION_FINAL = _prompt("legacy/vision_rgbd_final.md")

SKILL_CODE_SYSTEM = _prompt("roles/code.md")
SKILL_VISION_SYSTEM = _prompt("roles/vision.md")
SKILL_VISION_FINAL = _prompt("roles/vision_final.md")
