"""Ensure the project notebook stays safe to execute with Run All defaults."""
from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "00_project_dashboard.ipynb"


def test_dashboard_run_all_is_read_only_by_default(monkeypatch):
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    assert notebook["nbformat"] == 4
    calls = []

    def read_only_git(command, **kwargs):
        assert command[:2] == ["git", "--no-pager"]
        assert command[2] in {"status", "log"}
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="test local git state")

    def forbidden(*args, **kwargs):
        raise AssertionError("Run All must not start processes or make model/network requests")

    monkeypatch.chdir(NOTEBOOK.parent)
    monkeypatch.setattr(subprocess, "run", read_only_git)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    namespace = {"__name__": "__dashboard_test__"}
    for index, cell in enumerate(notebook["cells"]):
        if cell["cell_type"] != "code":
            continue
        assert cell["outputs"] == []
        assert cell["execution_count"] is None
        source = "".join(cell["source"])
        exec(compile(source, f"dashboard-cell-{index}", "exec"), namespace)

    assert namespace["ROOT"] == ROOT
    assert namespace["APPROVE_ACTION"] == ""
    assert namespace["APPROVE_CHAT"] == ""
    assert namespace["APPROVE_STOP"] == ""
    assert namespace["CHAT_PROCESS"] is None
    assert len(calls) == 2


def test_dashboard_document_links_exist():
    import re

    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    for cell in notebook["cells"]:
        if cell["cell_type"] == "markdown":
            for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", "".join(cell["source"])):
                assert (NOTEBOOK.parent / target).is_file(), target
