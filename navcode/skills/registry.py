"""Read only named, role-authorized guidance from a frozen run-local bundle."""
import hashlib
import json
from pathlib import Path


class SkillRegistry:
    def __init__(self, root, role, event=lambda *args: None):
        if role not in ("code", "vision"):
            raise ValueError("unknown skill role")
        self.root, self.role, self.event = Path(root).resolve(), role, event
        manifest = json.loads((self.root/"catalog.json").read_text())
        if manifest.get("version") != 1:
            raise ValueError("unsupported skill catalog version")
        self.entries = {row["name"]: row for row in manifest["skills"] if role in row["roles"]}
        self.loaded = {}

    def catalog(self):
        return [{"name": row["name"], "description": row["description"]} for row in self.entries.values()]

    def read(self, name, reason="model_request"):
        if not isinstance(name, str) or name not in self.entries:
            raise ValueError("skill is not authorized for this role")
        if name not in self.loaded:
            path = (self.root/self.entries[name]["entry"]).resolve()
            if not path.is_relative_to(self.root) or not path.is_file():
                raise ValueError("invalid skill resource")
            data = path.read_bytes()
            if len(data) > 24000:
                raise ValueError("skill exceeds context limit")
            item = {"name": name, "text": data.decode(), "sha256": hashlib.sha256(data).hexdigest()}
            self.loaded[name] = item
            self.event("SKILL_LOADED", {"name": name, "role": self.role,
                                         "sha256": item["sha256"], "reason": reason})
        return self.loaded[name]

    def context(self):
        return {"skill_catalog": self.catalog(), "loaded_skills": list(self.loaded.values())}
