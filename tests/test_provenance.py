import pytest

from navcode.artifacts.provenance import archive_package_sources, package_source_hashes, verify_package_sources


def test_nested_sources_are_archived_without_basename_collisions_and_changes_are_detected(tmp_path):
    root = tmp_path/"package"
    for name, source in [("agents/__init__.py", '"agents"'), ("runtime/__init__.py", '"runtime"'),
                         ("runtime/worker.py", 'print("worker")')]:
        path = root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    archive = tmp_path/"implementation"
    hashes = archive_package_sources(archive, root)
    assert set(hashes) == {"agents/__init__.py", "runtime/__init__.py", "runtime/worker.py"}
    assert hashes == package_source_hashes(archive)
    assert (archive/"agents/__init__.py").read_text() != (archive/"runtime/__init__.py").read_text()
    verify_package_sources(hashes, root)
    (root/"new.py").write_text('"new module"')
    with pytest.raises(RuntimeError, match="new.py"):
        verify_package_sources(hashes, root)
    (root/"new.py").unlink()
    (root/"runtime/worker.py").unlink()
    with pytest.raises(RuntimeError, match="runtime/worker.py"):
        verify_package_sources(hashes, root)


def test_instruction_resources_are_frozen_but_credentials_are_not_archived(tmp_path):
    root = tmp_path/"package"
    (root/"skills/entry").mkdir(parents=True)
    (root/"skills/entry/SKILL.md").write_text("Guidance v1")
    (root/"skills/catalog.json").write_text('{"version":1}')
    (root/".env").write_text("never archive credentials")
    snapshot = archive_package_sources(tmp_path/"archive", root)
    assert set(snapshot) == {"skills/entry/SKILL.md", "skills/catalog.json"}
    assert not (tmp_path/"archive/.env").exists()
    (root/"skills/entry/SKILL.md").write_text("Guidance v2")
    with pytest.raises(RuntimeError, match="SKILL.md"):
        verify_package_sources(snapshot, root)
