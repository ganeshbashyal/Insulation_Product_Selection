"""Serving snapshots and isolated runtime validation with synthetic approvals only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from knowledge_release import ReleaseLibrary, validate, build
from research_store import canonical

ROOT = Path(__file__).resolve().parents[1]


def envelope(families=None, evidence=None, revoked=None):
    families = families or [{"family_id":"TEST","name":"Synthetic family","manufacturer":"Test",
                             "confidence":"manufacturer_supported","primary_function":"Unreviewed generated prose",
                             "category":"Synthetic","applications":["wall"],"keywords":["synthetic"],
                             "questions":["Check exact source"],"human_gates":["Human review"],
                             "scores":{"acoustic_comfort":0,"energy_efficiency":0,"sustainability":0,
                                       "installation_practicality":0,"compliance_readiness":0}}]
    body = {"schema_version":1,"automatic_selection":False,"baseline":"synthetic","publication_id":None,
            "families":families,"evidence":evidence or {row["family_id"]:[] for row in families},
            "revoked":revoked or [],"catalogue":[],"eligibility":{},"gaps":[]}
    return {"release_id":hashlib.sha256(canonical(body).encode()).hexdigest(),"payload":body}


def test_release_checksum_activation_expected_pointer_and_immutable_files(tmp_path):
    library = ReleaseLibrary(tmp_path)
    data = envelope()
    assert library.save(data).exists()
    assert library.active_id() is None
    with pytest.raises(ValueError):
        library.activate(data["release_id"],"wrong",None)
    library.activate(data["release_id"],data["release_id"],None)
    assert library.active() == data
    assert len(library.save(data).stem) == 16
    with pytest.raises(ValueError, match="prefix collision"):
        library.read(data["release_id"][:16] + "0" * 48)
    with pytest.raises(ValueError,match="changed"):
        library.activate(data["release_id"],data["release_id"],None)
    data["payload"]["baseline"]="tampered"
    with pytest.raises(ValueError,match="checksum"):
        validate(data)


def test_withdrawal_survives_rollback_and_concurrent_activation_lock(tmp_path):
    library = ReleaseLibrary(tmp_path)
    claim = {"evidence_id":"R","evidence_status":"verified","metric_type":"thermal_r",
             "verified_by":"synthetic","verified_at":"2026-10-01T00:00:00Z",
             "source_locator":"Page 1","source_url":"https://example.invalid/tds",
             "variant":"Synthetic","scope":"product","test_context":"Synthetic laboratory",
             "test_standard":"TEST","value":2,"unit":"m2.K/W"}
    old = envelope(evidence={"TEST":[claim]})
    library.save(old)
    library.activate(old["release_id"],old["release_id"],None)
    new = envelope(revoked=[{"family_id":"TEST","evidence_id":"R"}])
    library.save(new)
    library.activate(new["release_id"],new["release_id"],old["release_id"])
    with pytest.raises(ValueError,match="resurrect"):
        library.activate(old["release_id"],old["release_id"],new["release_id"])
    (tmp_path/"activation.lock").write_text("existing owner")
    with pytest.raises(FileExistsError):
        library.activate(new["release_id"],new["release_id"],new["release_id"])
    assert (tmp_path/"activation.lock").read_text()=="existing owner"


def test_build_rejects_held_publication_and_excludes_pending():
    from types import SimpleNamespace
    idx = SimpleNamespace(families={"TEST":{"family_id":"TEST"}},skus=[],
                          baseline=lambda:"synthetic",browse=lambda **kwargs:{"families":[]})
    reader = SimpleNamespace(index=lambda:idx,evidence=lambda:({"TEST":[{"evidence_status":"pending_human_review"}]},
                            {"state":"baseline_only","publication_id":None,"revoked":[],"eligibility":{}}))
    assert build(reader)["payload"]["evidence"] == {"TEST":[]}
    reader.evidence = lambda: ({},{"state":"stale_sources_review_required"})
    with pytest.raises(ValueError,match="held"):
        build(reader)


def test_serving_runtime_blocks_heavy_imports_and_network_and_has_no_research_routes(tmp_path):
    library = ReleaseLibrary(tmp_path/"release")
    data = envelope()
    data["payload"]["site_visibility"] = {"test":["TEST"],"hidden":[]}
    data["release_id"] = hashlib.sha256(canonical(data["payload"]).encode()).hexdigest()
    library.save(data)
    library.activate(data["release_id"],data["release_id"],None)
    sites=tmp_path/"sites"
    sites.mkdir()
    (sites/"test.json").write_text(json.dumps({
        "site_id":"test","display_name":"Test","colours":{"primary":"#000","accent":"#fff"},
        "logo_url":"","greeting":"","contact_method":"phone","phone":"test",
        "allowed_origins":["https://test.invalid"]}))
    script = r'''
import sys, importlib.abc, urllib.request, socket, time, json
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self, fullname, path=None, target=None):
  if fullname.split('.')[0] in {'pandas','numpy','pypdf','openpyxl','google','jupyterlab','jsonschema','research_api','product_research'}:
   raise AssertionError('Heavy/authoring import: '+fullname)
sys.meta_path.insert(0,Block())
urllib.request.urlopen=lambda *a,**k: (_ for _ in ()).throw(AssertionError('Network request'))
start=time.monotonic()
import web_agent, asyncio
asyncio.run(web_agent.startup())
assert '/api/research/login' not in web_agent.app.openapi()['paths']
assert web_agent.ready()['release_id']
import agent_core
result=web_agent.conversation_service.handle(agent_core.Conversation(),'What is Synthetic family?',site_id='test')
assert 'Unreviewed generated prose' not in result.reply
assert 'Synthetic family' in result.reply
hidden=agent_core.Conversation()
hidden.topic_products=['TEST']
hidden.product_options=['TEST']
result=web_agent.conversation_service.handle(hidden,'What is Synthetic family?',site_id='hidden')
assert 'Synthetic family' not in result.reply
assert not hidden.topic_products and not hidden.product_options
from sales_brief import SalesBriefBuilder
family={**agent_core.FAMILIES[0],'scores':{key:5 for key in agent_core.FAMILIES[0]['scores']}}
brief=SalesBriefBuilder([family])
answers={'application':'external wall','priority':'reduce heat and energy bills'}
assert brief.build(answers,site_id='test')['candidates']
assert not brief.build(answers,site_id='hidden')['candidates']
print(json.dumps({'startup_seconds':time.monotonic()-start,'release_id':web_agent.ready()['release_id'],'no_heavy_imports':True}))
'''
    env={**os.environ,"AURORA_RELEASE_DIR":str(library.directory),"AURORA_STATE_DIR":str(tmp_path/"state"),
         "AURORA_SITES_DIR":str(sites),"AURORA_SERVING_ONLY":"true","AURORA_ENV":"production",
         "AGENT_USE_LLM":"false","USE_HYBRID_RANKING":"false","AURORA_SITE_API_KEY_TEST":"synthetic-only"}
    env["AURORA_RATE_LIMIT_BACKEND"]="sqlite"
    result=subprocess.run([sys.executable,"-c",script],cwd=ROOT,env=env,text=True,capture_output=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    assert '"no_heavy_imports": true' in result.stdout


def test_allowlisted_runtime_package_starts_without_authoring_sources(tmp_path):
    import shutil
    from scripts.package_runtime import package, FILES
    source=tmp_path/"source"
    source.mkdir()
    for name in FILES:
        dest=source/name
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,dest)
    shutil.copytree(ROOT/"tools",source/"tools",ignore=shutil.ignore_patterns("__pycache__"))
    library=ReleaseLibrary(tmp_path/"release")
    data=envelope()
    library.save(data)
    library.activate(data["release_id"],data["release_id"],None)
    target=source/"data"/"local"/"distribution"/"synthetic"
    manifest=package(source,library.directory,target)
    assert manifest["release_id"]==data["release_id"]
    assert not (target/"config"/"sites").exists()
    assert not (target/"data").exists()
    assert not (target/"research_api.py").exists()
    assert not (target/"knowledge"/"performance_evidence.json").exists()
    assert not list(target.rglob("*.pdf"))
    sites=tmp_path/"sites"
    sites.mkdir()
    (sites/"test.json").write_text(json.dumps({"site_id":"test","display_name":"Test",
        "colours":{"primary":"#000","accent":"#fff"},"logo_url":"","greeting":"","contact_method":"phone",
        "phone":"synthetic","allowed_origins":["https://test.invalid"]}))
    env={**os.environ,"AURORA_RELEASE_DIR":str(target/"releases"),"AURORA_STATE_DIR":str(tmp_path/"state"),
         "AURORA_SITES_DIR":str(sites),"AURORA_ENV":"production","AURORA_SERVING_ONLY":"true",
         "AGENT_USE_LLM":"false","USE_HYBRID_RANKING":"false","AURORA_RATE_LIMIT_BACKEND":"sqlite",
         "AURORA_SITE_API_KEY_TEST":"synthetic"}
    env.pop("PYTHONPATH",None)
    result=subprocess.run([sys.executable,"-c","import asyncio,web_agent; asyncio.run(web_agent.startup()); assert web_agent.ready()['release_id']; print('PACKAGED_RUNTIME_READY')"],
                          cwd=target,env=env,text=True,capture_output=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    assert "PACKAGED_RUNTIME_READY" in result.stdout


def test_typed_intake_candidates_keep_unknowns_scopes_and_pending_status():
    from local_intake import checked_candidates
    candidate = {"family_id":"TEST","kind":"performance","field":"thermal_r","value":2.0,
                 "unit":"m2.K/W","variant":"90 mm","scope":"product","page":2,
                 "quote":"Thermal R value 2.0","test_standard":"","test_context":""}
    item = {"family_ids":["TEST"],"role":"sds","candidates":[candidate]}
    extracted = {"sha256":"synthetic","pages":[{"page":1,"text":"Cover"},
                                            {"page":2,"text":"Thermal R value 2.0"}]}
    result = checked_candidates(item, extracted)[0]
    assert result["review_status"] == "pending_human_review"
    assert result["performance_source_gap"] is True
    assert result["test_standard"] == ""
    for change in ({"page":1}, {"family_id":"OTHER"}, {"value":float("nan")}, {"quote":"Invented"}):
        item["candidates"] = [{**candidate, **change}]
        with pytest.raises(ValueError):
            checked_candidates(item, extracted)


def test_reviewed_exports_are_version_bound_without_generated_research(tmp_path):
    import sqlite3
    from release_exports import export
    data = envelope()
    library = ReleaseLibrary(tmp_path / "r")
    library.save(data)
    with pytest.raises(ValueError, match="activated"):
        export(library, tmp_path / "blocked")
    library.activate(data["release_id"], data["release_id"], None)
    destination = tmp_path / "exports"
    manifest = export(library, destination)
    assert manifest["release_id"] == data["release_id"]
    card = json.loads((destination / "retrieval_cards.jsonl").read_text())
    assert card["family_id"] == "TEST" and card["reviewed_claims"] == []
    voice = (destination / "voice_knowledge.txt").read_text()
    assert "Unreviewed generated prose" not in voice
    assert "Do not recommend/select products" in voice
    with sqlite3.connect(destination / "knowledge.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM families").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM claims").fetchone()[0] == 0
    with pytest.raises(ValueError, match="overwrite"):
        export(library, destination)


def test_release_visibility_rejects_unknown_ids_and_scopes_all_export_adapters(tmp_path):
    from release_exports import export
    data = envelope()
    data["payload"]["site_visibility"] = {"shop_a":["TEST"],"shop_b":[]}
    data["release_id"] = hashlib.sha256(canonical(data["payload"]).encode()).hexdigest()
    library = ReleaseLibrary(tmp_path / "r")
    library.save(data)
    library.activate(data["release_id"], data["release_id"], None)
    manifest = export(library, tmp_path / "shop-b", "shop_b")
    assert manifest["family_count"] == manifest["sku_count"] == 0
    assert not (tmp_path / "shop-b" / "retrieval_cards.jsonl").read_text()
    data["payload"]["site_visibility"]["shop_b"] = ["MISSING"]
    data["release_id"] = hashlib.sha256(canonical(data["payload"]).encode()).hexdigest()
    with pytest.raises(ValueError, match="canonical"):
        validate(data)
