import json
import sqlite3

import pytest

from authoring_backup import backup, checked_manifest, restore
from research_store import ResearchStore


def test_retention_roundtrip_excludes_customer_state_and_clears_logins(tmp_path):
    root, saved, restored = (tmp_path / name for name in ("source", "backup", "restore"))
    family = root / "knowledge" / "test" / "families.json"
    family.parent.mkdir(parents=True)
    family.write_text('{"legacy": "original unavailable"}')
    pdf = root / "data" / "tds" / "test.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"retained original")
    store = ResearchStore(root / "data" / "local" / "product_research.sqlite3")
    store.create_user("reviewer", "Synthetic password only!", ["reviewer"])
    token = store.login("reviewer", "Synthetic password only!", "local")["token"]
    with store.connection() as conn:
        conn.execute("INSERT INTO revisions VALUES(1,'family:TEST','note','reviewer','now','{}')")
        conn.execute("INSERT INTO proposals VALUES(1,'publisher','now','baseline',1,'{}',1)")
        conn.execute("INSERT INTO active_publication VALUES(1,1)")
    (store.path.parent / "sessions.sqlite3").write_bytes(b"private customer data")
    (store.path.parent / "sales-operator-key.txt").write_text("not in snapshot")
    assert backup(root, saved)["verified"]
    assert not (saved / "data" / "local" / "sessions.sqlite3").exists()
    assert not (saved / "data" / "local" / "sales-operator-key.txt").exists()
    preview = restore(saved, restored)
    assert preview["writes"] is False and not restored.exists()
    restore(saved, restored, confirm=True)
    assert (restored / pdf.relative_to(root)).read_bytes() == pdf.read_bytes()
    with sqlite3.connect(restored / store.path.relative_to(root)) as conn:
        assert conn.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM revisions").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM proposals").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM active_publication").fetchone()[0] == 0
    assert store.session(token) is not None
    with pytest.raises(ValueError, match="new directory"):
        restore(saved, restored, confirm=True)


@pytest.mark.parametrize("name", ["../escape", "data/local/sessions.sqlite3", "C:/outside", "knowledge/../outside"])
def test_manifest_rejects_unconfined_paths_before_writes(tmp_path, name):
    source = tmp_path / "snapshot"
    source.mkdir()
    (source / "manifest.json").write_text(json.dumps({"schema_version": 1, "files": {name: "0" * 64}}))
    target = tmp_path / "restore"
    with pytest.raises(ValueError):
        restore(source, target, confirm=True)
    assert not target.exists()


def test_corrupt_snapshot_never_restores(tmp_path):
    root = tmp_path / "source"
    (root / "knowledge").mkdir(parents=True)
    (root / "knowledge" / "manual.md").write_text("keep")
    source, target = tmp_path / "backup", tmp_path / "restore"
    backup(root, source)
    (source / "knowledge" / "manual.md").write_text("tampered")
    with pytest.raises(ValueError, match="checksum"):
        checked_manifest(source)
    with pytest.raises(ValueError):
        restore(source, target, confirm=True)
    assert not target.exists()


def test_backup_inside_checkout_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="outside"):
        backup(tmp_path, tmp_path / "backup")
