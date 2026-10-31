"""Recursive source snapshots and immutable experiment-batch checks."""
import hashlib
import shutil
from pathlib import Path

from navcode.paths import PACKAGE_ROOT


def package_source_hashes(package_root=PACKAGE_ROOT):
    root = Path(package_root)
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and p.suffix in (".py", ".md", ".json")
            and "__pycache__" not in p.parts}


def archive_package_sources(destination, package_root=PACKAGE_ROOT):
    root, destination = Path(package_root), Path(destination)
    sources = package_source_hashes(root)
    for relative in sources:
        target = destination/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root/relative, target)
    return sources


def verify_package_sources(expected, package_root=PACKAGE_ROOT):
    current = package_source_hashes(package_root)
    if current != expected:
        changed = sorted(k for k in set(current) | set(expected) if current.get(k) != expected.get(k))
        raise RuntimeError("source changed during fixed batch; refusing mixed-version results: " + ", ".join(changed))
