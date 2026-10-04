"""Offline reads are default; writes require explicit confirmation/named decisions."""
import json
from pathlib import Path

import pytest

from scripts import knowledge_workflow as cli


class SyntheticService:
    def __init__(self, root):
        self.root = root

    def index(self):
        return self

    def overview(self):
        return {"family_count": 2}

    def browse(self, query="", limit=50):
        return {"query": query, "limit": limit, "families": []}

    def family(self, family_id):
        if family_id == "UNKNOWN":
            raise ValueError("Unknown family")
        return {"dossier": {"family_id": family_id, "provenance_state": "legacy_supplied_original_unavailable"}}

    def validation(self):
        return {"publication_state": "baseline_only"}

    def source_preview(self, manifest):
        return {"preview_id": "EXACT", "manifest": str(manifest)}

    def source_stage(self, manifest, confirmation):
        if confirmation != "EXACT":
            raise ValueError("Preview changed")
        return {"state": "staged_pending_human_review"}


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(cli, "KnowledgeService", SyntheticService)


@pytest.mark.parametrize("command,key,value", [
    (["overview"], "family_count", 2),
    (["families", "--query", "batt", "--limit", "3"], "query", "batt"),
    (["validation"], "publication_state", "baseline_only"),
])
def test_commands_use_shared_service(offline, capsys, tmp_path, command, key, value):
    assert cli.main(["--root", str(tmp_path), *command]) == 0
    assert json.loads(capsys.readouterr().out)[key] == value
    assert list(tmp_path.iterdir()) == []


def test_family_returns_shared_dossier(offline, capsys):
    assert cli.main(["family", "TEST"]) == 0
    assert json.loads(capsys.readouterr().out)["dossier"]["family_id"] == "TEST"


def test_errors_are_explicit_not_success_shaped(offline, capsys):
    assert cli.main(["family", "UNKNOWN"]) == 1
    captured = capsys.readouterr()
    assert not captured.out and "Unknown family" in captured.err


def test_publish_requires_explicit_operator_arguments(offline):
    with pytest.raises(SystemExit) as exc:
        cli.main(["publish"])
    assert exc.value.code == 2


def test_nonpositive_limit_is_explicit_error(offline, capsys):
    assert cli.main(["families", "--limit", "-1"]) == 1
    assert "positive" in capsys.readouterr().err


def test_default_root_is_the_checkout():
    assert cli.ROOT == Path(__file__).resolve().parents[1]


def test_source_actions_are_explicit(offline, capsys):
    assert cli.main(["source-preview", "manifest.json"]) == 0
    assert json.loads(capsys.readouterr().out)["preview_id"] == "EXACT"
    assert cli.main(["source-stage", "manifest.json", "--confirm", "WRONG"]) == 1
    assert "Preview changed" in capsys.readouterr().err
    assert cli.main(["source-stage", "manifest.json", "--confirm", "EXACT"]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "staged_pending_human_review"
