"""No real product data/approval is used by the standalone-runner tests."""
import json
import os
from pathlib import Path
import subprocess

import pytest

from scripts.run_local_maintenance import Maintenance, Ollama, INPUT_LIMIT, CONTEXT_TOKENS, PREDICT_TOKENS


@pytest.fixture
def runner(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "README.md").write_text("# Synthetic project\n", encoding="utf-8")
    (tmp_path / "module.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    obj = Maintenance(tmp_path)
    obj.add("example", "Document synthetic project only", ["README.md"], ["docs/EXAMPLE.md"], [], [], "llama3.2:latest")
    return obj


class FakeModel:
    def __init__(self, edits=None, error=None):
        self.edits = edits if edits is not None else [{"path": "docs/EXAMPLE.md", "content": "# Example\n\n[Project](../README.md)\n"}]
        self.error = error
        self.calls = 0

    def generate(self, model, prompt):
        self.calls += 1
        if self.error:
            raise self.error
        return json.dumps({"rationale": "Synthetic candidate.", "edits": self.edits})


def test_read_only_inventory_status_resume_never_initialise_or_call_model(tmp_path, monkeypatch):
    (tmp_path / "module.py").write_text("import ast\n\ndef main():\n    pass\n")
    obj = Maintenance(tmp_path)
    monkeypatch.setattr(Ollama, "request", lambda *a, **k: pytest.fail("No model calls for reads"))
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("No processes for reads"))
    assert obj.status() == {"tasks": {}}
    assert obj.next_steps()["model_calls"] == 0
    records = obj.inventory()["files"]
    assert records[0]["functions"][0]["name"] == "main"
    assert not obj.state.exists()


def test_next_state_guidance_is_read_only_and_detects_stale_candidate(runner):
    before = (runner.state / "journal.json").read_bytes()
    advice = runner.next_steps()["tasks"][0]
    assert advice["command"].endswith("propose example")
    assert (runner.state / "journal.json").read_bytes() == before
    runner.propose("example", FakeModel())
    advice = runner.next_steps()["tasks"][0]
    assert advice["status"] == "staged"
    assert "not semantic" in advice["advice"]
    assert advice["command"].endswith("verify example")
    runner.verify("example")
    advice = runner.next_steps()["tasks"][0]
    assert advice["status"] == "verified" and advice["command"] is None
    assert "Human semantic" in advice["advice"]
    (runner.root / "README.md").write_text("# Updated input\n")
    advice = runner.next_steps()["tasks"][0]
    assert "Inputs changed" in advice["advice"] and advice["command"] is None


@pytest.mark.parametrize("state", ["running", "applying", "apply_interrupted", "failed", "rejected", "applied"])
def test_next_never_automates_failure_or_interruption(runner, state):
    runner.update("example", status=state, error="synthetic error")
    advice = runner.next_steps()["tasks"][0]
    assert advice["command"] is None
    assert advice["error"] == "synthetic error"
    assert runner.next_steps()["writes"] is False


def test_next_with_lock_does_not_schedule_or_clear_worker(runner):
    with runner.locked():
        advice = runner.next_steps()
        assert advice["lock_present"]
        assert advice["tasks"][0]["command"] is None
        assert (runner.state / "runner.lock").exists()


def test_rejection_preserves_attempt_and_prepares_without_model_call(runner):
    model = FakeModel()
    runner.propose("example", model)
    original = (runner.state / "example" / "reply.txt").read_bytes()
    result = runner.reject("example", "Invented facts; use cited source text only.", "narrow",
                           "Use only the supplied sentence with file/line citation.", ["README.md@1:1"])
    assert result["replacement"] == "narrow"
    assert model.calls == 1
    task = runner.status()["tasks"]["example"]
    assert task["status"] == "rejected"
    archive = Path(task["archived"])
    assert (archive / "reply.txt").read_bytes() == original
    assert json.loads((archive / "rejection.json").read_text())["replacement"] == "narrow"
    assert runner.status()["tasks"]["narrow"]["status"] == "pending"
    assert runner.status()["tasks"]["narrow"]["attempts"] == 0
    assert not (runner.root / "docs" / "EXAMPLE.md").exists()
    with pytest.raises(ValueError, match="Rejected"):
        runner.propose("example", FakeModel(), retry=True)


def test_invalid_replacement_leaves_original_proposal_staged(runner):
    runner.propose("example", FakeModel())
    with pytest.raises(ValueError):
        runner.reject("example", "Valid feedback with detail", "bad-replacement",
                      "Use source", ["../private.md"])
    assert runner.status()["tasks"]["example"]["status"] == "staged"
    assert "bad-replacement" not in runner.status()["tasks"]


def test_failed_replacement_can_select_smaller_model(runner):
    runner.update("example", status="failed", model="llama3.1:8b", attempts=1, error="HTTP 500")
    runner.reject("example", "Use a smaller model after resource failure.", "light",
                  "Cite the source sentence only.", ["README.md@1:1"], model="llama3.2:latest")
    tasks = runner.status()["tasks"]
    assert tasks["example"]["model"] == "llama3.1:8b"
    assert tasks["example"]["status"] == "rejected"
    assert tasks["light"]["model"] == "llama3.2:latest"
    assert tasks["light"]["attempts"] == 0


def test_invalid_replacement_model_preserves_failed_attempt(runner):
    runner.update("example", status="failed", attempts=1, error="HTTP 500")
    with pytest.raises(ValueError):
        runner.reject("example", "Use a smaller model after resource failure.", "light",
                      "Cite the source sentence only.", ["README.md@1:1"], model="cloud")
    assert runner.status()["tasks"]["example"]["status"] == "failed"
    assert "light" not in runner.status()["tasks"]


def test_request_records_low_memory_budget(runner):
    runner.propose("example", FakeModel())
    request = json.loads((runner.state / "example" / "request.json").read_text())
    assert request["num_ctx"] == CONTEXT_TOKENS == 4096
    assert request["num_predict"] == PREDICT_TOKENS == 1024
    assert request["input_limit"] == INPUT_LIMIT == 4000


def test_retry_keeps_original_raw_reply(runner):
    runner.propose("example", FakeModel())
    original = (runner.state / "example" / "reply.txt").read_bytes()
    runner.propose("example", FakeModel([{"path": "docs/EXAMPLE.md", "content": "# Different candidate\n"}]), retry=True)
    archive = next((runner.state / "example").glob("attempt-1-*"))
    assert (archive / "reply.txt").read_bytes() == original


@pytest.mark.parametrize("path", ["../outside.md", "C:/outside.md", "docs/../README.md",
                                  "/outside.md", "docs\\outside.md", ".git/config", "data/local/lead.json",
                                  "evidence/inbox/private.json", "password.txt"])
def test_paths_are_confined_and_private_data_denied(runner, path):
    with pytest.raises(ValueError):
        runner.path(path)


@pytest.mark.parametrize("path", ["knowledge/families.md", "data/workbook.md", "reports/test.md",
                                  "aircall/test.md", "config/test.py", "scripts/run_local_maintenance.py",
                                  "tests/test_local_maintenance.py", "data/local/approval.json"])
def test_model_cannot_change_sources_or_its_safety_boundary(runner, path):
    with pytest.raises(ValueError):
        runner.path(path, writable=True)


@pytest.mark.parametrize("host", ["https://api.example.invalid", "http://127.0.0.1:11434/redirect",
                                  "http://localhost:11434", "http://127.0.0.1:9999",
                                  "http://user:password@127.0.0.1:11434", "http://127.0.0.1:11434?host=cloud"])
def test_only_literal_loopback_endpoint_allowed(host):
    with pytest.raises(ValueError):
        Ollama(host)


def test_installed_model_required_without_pull(monkeypatch):
    client = Ollama()
    calls = []
    def request(endpoint, payload=None):
        calls.append(endpoint)
        return {"models": []}
    monkeypatch.setattr(client, "request", request)
    with pytest.raises(ValueError, match="not installed"):
        client.generate("llama3.2:latest", "test")
    assert calls == ["/api/tags"]


def test_no_parallel_model_or_cloud_fallback(monkeypatch):
    client = Ollama()
    monkeypatch.setattr(client, "request", lambda endpoint, payload=None:
                        {"models": [{"name": "llama3.2:latest"}]} if endpoint == "/api/tags"
                        else {"models": [{"name": "gemma4:26b"}]})
    with pytest.raises(ValueError, match="resident"):
        client.generate("llama3.2:latest", "test")


def test_only_this_run_loaded_model_is_unloaded(monkeypatch):
    client = Ollama()
    calls = []
    def request(endpoint, payload=None):
        calls.append((endpoint, payload))
        if endpoint == "/api/tags":
            return {"models": [{"name": "llama3.2:latest"}]}
        if endpoint == "/api/ps":
            return {"models": []}
        if endpoint == "/api/chat":
            return {"message": {"content": "{}"}, "done_reason": "stop"}
        return {}
    monkeypatch.setattr(client, "request", request)
    assert client.generate("llama3.2:latest", "test") == "{}"
    payload = next(payload for endpoint, payload in calls if endpoint == "/api/chat")
    assert payload["options"]["num_ctx"] == 4096
    assert payload["options"]["num_predict"] == 1024
    assert payload["options"]["num_thread"] == 2
    assert calls[-1] == ("/api/generate", {"model": "llama3.2:latest", "keep_alive": 0})


def test_propose_verify_and_apply_only_confirmed_candidate(runner):
    runner.propose("example", FakeModel())
    target = runner.root / "docs" / "EXAMPLE.md"
    assert not target.exists()
    assert runner.status()["tasks"]["example"]["status"] == "staged"
    result = runner.verify("example")
    assert not result["errors"]
    assert not target.exists()
    with pytest.raises(ValueError, match="confirm"):
        runner.apply("example", confirm="wrong")
    result = runner.apply("example", confirm="example")
    assert result["status"] == "applied"
    assert target.read_text().startswith("# Example")
    assert runner.status()["tasks"]["example"]["status"] == "applied"
    with pytest.raises(ValueError, match="Applied"):
        runner.propose("example", FakeModel())


def test_existing_dirty_content_is_preserved_in_candidate_and_backup(runner):
    dirty = b"# Human edits already here\n"
    (runner.root / "README.md").write_bytes(dirty)
    runner.add("edit-readme", "Keep hand edits", ["README.md"], ["README.md"], [], [], "llama3.2:latest")
    runner.propose("edit-readme", FakeModel([{"path": "README.md", "content": "# Human edits already here\n\nNew paragraph.\n"}]))
    result = runner.verify("edit-readme")
    assert not result["errors"]
    assert (runner.root / "README.md").read_bytes() == dirty
    runner.apply("edit-readme", confirm="edit-readme")
    backup = json.loads((runner.state / "edit-readme" / "apply-backup.json").read_text())
    assert bytes.fromhex(backup["README.md"]) == dirty


def test_stale_files_block_verify_and_apply(runner):
    runner.propose("example", FakeModel())
    runner.verify("example")
    (runner.root / "module.py").write_text("# concurrent change\n")
    with pytest.raises(ValueError, match="changed"):
        runner.apply("example", confirm="example")
    assert not (runner.root / "docs" / "EXAMPLE.md").exists()


def test_source_bytes_are_bound_but_not_copied_or_sent(runner):
    source = runner.root / "data" / "tds" / "synthetic.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"synthetic original source")
    model = FakeModel()
    runner.propose("example", model)
    request = json.loads((runner.state / "example" / "request.json").read_text())
    assert "synthetic original source" not in request["prompt"]
    result = runner.verify("example")
    assert result["omitted_sources"] == ["data/tds/synthetic.pdf"]
    assert not (Path(result["candidate_root"]) / "data" / "tds" / "synthetic.pdf").exists()
    source.write_bytes(b"changed source")
    with pytest.raises(ValueError, match="changed"):
        runner.apply("example", confirm="example")


def test_deep_candidate_paths_are_verifiable_on_windows(runner):
    # Source fits MAX_PATH; the extra candidate prefix pushes the copy beyond it.
    source = runner.root / "knowledge" / ("a" * 15) / "research" / ("b" * 20 + ".json")
    source.parent.mkdir(parents=True)
    source.write_text('{"retained": true}', encoding="utf-8")
    runner.propose("example", FakeModel())
    result = runner.verify("example")
    assert not result["errors"]
    from scripts.run_local_maintenance import io_path
    target = Path(result["candidate_root"]) / source.relative_to(runner.root)
    assert io_path(target).read_bytes() == source.read_bytes()


def test_private_site_config_cannot_be_added_to_model_context(runner):
    with pytest.raises(ValueError, match="credentials"):
        runner.add("private", "Read config", ["config/sites/local.json"], ["docs/X.md"], [], [], "llama3.2:latest")


def test_interrupted_apply_is_not_success_and_keeps_precise_backups(runner, monkeypatch):
    original_bytes = (runner.root / "README.md").read_bytes()
    runner.add("two-edits", "Document", ["README.md"], ["README.md", "docs/SECOND.md"], [], [], "llama3.2:latest")
    runner.propose("two-edits", FakeModel([{"path": "README.md", "content": "# First accepted edit\n"},
                                         {"path": "docs/SECOND.md", "content": "# Second edit\n"}]))
    runner.verify("two-edits")
    original = runner.snapshot
    calls = 0
    def concurrent_change():
        nonlocal calls
        calls += 1
        if calls == 3:
            (runner.root / "module.py").write_text("# external change\n")
        return original()
    monkeypatch.setattr(runner, "snapshot", concurrent_change)
    with pytest.raises(ValueError, match="Concurrent"):
        runner.apply("two-edits", confirm="two-edits")
    assert runner.status()["tasks"]["two-edits"]["status"] == "apply_interrupted"
    assert (runner.root / "README.md").read_text() == "# First accepted edit\n"
    assert not (runner.root / "docs" / "SECOND.md").exists()
    backup = json.loads((runner.state / "two-edits" / "apply-backup.json").read_text())
    assert bytes.fromhex(backup["README.md"]) == original_bytes


def test_bounded_line_context_and_edit_preserves_other_human_lines(runner):
    (runner.root / "README.md").write_text("# Human heading\nOld sentence.\nKeep this note.\n")
    runner.add("line-edit", "Update sentence only", ["README.md@2:2"], ["README.md"], [], [], "llama3.2:latest")
    runner.propose("line-edit", FakeModel([{"path": "README.md", "start_line": 2, "end_line": 2,
                                          "content": "New sentence.\n"}]))
    request = json.loads((runner.state / "line-edit" / "request.json").read_text())
    assert "Keep this note." not in request["prompt"]
    assert "L2:" in request["prompt"]
    assert not runner.verify("line-edit")["errors"]
    runner.apply("line-edit", confirm="line-edit")
    assert (runner.root / "README.md").read_text() == "# Human heading\nNew sentence.\nKeep this note.\n"


def test_python_edits_need_actual_test_selector(runner):
    with pytest.raises(ValueError, match="test selector"):
        runner.add("code-edit", "Update code", ["module.py"], ["module.py"], [], [], "deepseek-coder:6.7b")


def test_failed_model_and_retry_budget_are_explicit(runner):
    with pytest.raises(TimeoutError):
        runner.propose("example", FakeModel(error=TimeoutError("synthetic timeout")))
    assert runner.status()["tasks"]["example"]["status"] == "failed"
    with pytest.raises(ValueError, match="retry"):
        runner.propose("example", FakeModel())
    runner.propose("example", FakeModel(), retry=True)
    with pytest.raises(ValueError, match="retry"):
        runner.propose("example", FakeModel(), retry=True)


@pytest.mark.parametrize("edits", [
    [{"path": "../outside.py", "content": "x"}],
    [{"path": "docs/EXAMPLE.md", "content": ""}],
    [{"path": "docs/EXAMPLE.md", "content": "# ok", "command": "delete something"}],
    [{"path": "docs/EXAMPLE.md", "content": "# ok"}, {"path": "docs/EXAMPLE.md", "content": "# duplicate"}],
])
def test_untrusted_candidate_schema_and_deletion_are_rejected(runner, edits):
    with pytest.raises(ValueError):
        runner.propose("example", FakeModel(edits))
    assert runner.status()["tasks"]["example"]["status"] == "failed"


def test_context_overflow_is_not_silently_truncated(runner):
    (runner.root / "README.md").write_text("x" * (INPUT_LIMIT + 1))
    model = FakeModel()
    with pytest.raises(ValueError, match="split"):
        runner.propose("example", model)
    assert model.calls == 0
    assert runner.status()["tasks"]["example"]["attempts"] == 0


def test_broken_markdown_links_block_apply(runner):
    runner.propose("example", FakeModel([{"path": "docs/EXAMPLE.md", "content": "[bad](../missing.md)\n"}]))
    result = runner.verify("example")
    assert result["errors"]
    with pytest.raises(ValueError):
        runner.apply("example", confirm="example")
    assert not (runner.root / "docs" / "EXAMPLE.md").exists()


def test_modified_candidate_after_verification_requires_reverify(runner):
    runner.propose("example", FakeModel())
    runner.verify("example")
    path = runner.state / "example" / "candidate.json"
    data = json.loads(path.read_text())
    data["edits"][0]["content"] = "# Changed after verification\n"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="verified"):
        runner.apply("example", confirm="example")


def test_prerequisites_and_lock_do_not_allow_duplicate_workers(runner):
    runner.add("dependent", "Document", ["README.md"], ["docs/SECOND.md"], [], ["example"], "llama3.2:latest")
    with pytest.raises(ValueError, match="Prerequisites"):
        runner.propose("dependent", FakeModel())
    with runner.locked():
        with pytest.raises(ValueError, match="lock"):
            with runner.locked():
                pytest.fail("Second worker admitted")
    assert not (runner.state / "runner.lock").exists()


def test_fresh_process_cli_read_actions_need_no_copilot_or_ollama(tmp_path):
    from scripts import run_local_maintenance as module
    (tmp_path / "module.py").write_text("def entry():\n    return 1\n")
    for command in ("status", "resume", "next", "inventory"):
        code = "from pathlib import Path; from scripts import run_local_maintenance as m; m.ROOT=Path(" + repr(str(tmp_path)) + "); raise SystemExit(m.main([" + repr(command) + "]))"
        result = subprocess.run([os.sys.executable, "-c", code], cwd=module.ROOT,
                                capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)
    assert not (tmp_path / "data" / "local" / "maintenance").exists()


def test_test_execution_requires_opt_in_and_errors_surface(runner, monkeypatch):
    tests = runner.root / "tests"
    tests.mkdir()
    (tests / "test_synthetic.py").write_text("def test_example():\n    assert True\n")
    runner.add("with-tests", "Document", ["README.md"], ["docs/EXAMPLE.md"], ["tests/test_synthetic.py"], [], "llama3.2:latest")
    runner.propose("with-tests", FakeModel())
    with pytest.raises(ValueError, match="approve-tests"):
        runner.verify("with-tests")
    def run(command, **kwargs):
        assert command[1:3] == ["-m", "pytest"]
        assert kwargs["cwd"].is_relative_to(runner.state)
        assert kwargs["env"]["AGENT_USE_LLM"] == "false"
        return subprocess.CompletedProcess(command, 1, "synthetic failure", "")
    monkeypatch.setattr(subprocess, "run", run)
    assert runner.verify("with-tests", approve_tests=True)["errors"] == ["Selected tests failed"]
    assert runner.status()["tasks"]["with-tests"]["status"] == "verification_failed"


def test_real_candidate_pytest_executes_only_opted_in_synthetic_task(runner):
    tests = runner.root / "tests"
    tests.mkdir()
    (tests / "test_value.py").write_text("from module import value\n\ndef test_value():\n    assert value() == 2\n")
    runner.add("code-task", "Return synthetic value two", ["module.py", "tests/test_value.py"],
               ["module.py"], ["tests/test_value.py"], [], "deepseek-coder:6.7b")
    runner.propose("code-task", FakeModel([{"path": "module.py", "content": "def value():\n    return 2\n"}]))
    result = runner.verify("code-task", approve_tests=True)
    assert not result["errors"], result
    assert result["tests"]["returncode"] == 0
    assert "return 1" in (runner.root / "module.py").read_text()
    runner.apply("code-task", confirm="code-task")
    assert "return 2" in (runner.root / "module.py").read_text()


@pytest.mark.skipif(not os.getenv("AURORA_TEST_MAINTENANCE_MODEL"), reason="Explicit installed loopback-model smoke only")
def test_actual_local_model_stages_synthetic_document_without_apply(runner):
    task = runner.task("example")
    task["model"] = os.environ["AURORA_TEST_MAINTENANCE_MODEL"]
    runner.update("example", model=task["model"], instruction="Create docs/EXAMPLE.md with exactly '# Synthetic local test\\n'. No links. Return the required JSON.")
    runner.propose("example", Ollama(timeout=180))
    assert not (runner.root / "docs" / "EXAMPLE.md").exists()
    assert not runner.verify("example")["errors"]
