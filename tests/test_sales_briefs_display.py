"""Operator display contracts; optional UI execution uses installed local Edge."""
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

import pytest


PAGE = Path(__file__).resolve().parents[1] / "templates" / "sales_briefs.html"


def test_operator_template_contains_no_embedded_data_or_secret_storage():
    page = PAGE.read_text(encoding="utf-8")
    for heading in ("Captured project facts", "Outstanding customer information",
                    "Provisional product candidates", "Evidence provenance and gaps",
                    "Clear and lock", "Full saved brief"):
        assert heading in page
    for forbidden in ("innerHTML", "localStorage", "sessionStorage", "sk_local_dev_test"):
        assert forbidden not in page
    assert "'X-Aurora-Lead-Admin-Key': operatorKey" in page
    assert "requestVersion" in page and "activeRequest.abort()" in page


@pytest.mark.skipif(not os.getenv("AURORA_TEST_EDGE"), reason="Opt-in installed local Edge UI check")
def test_render_filter_refresh_lock_and_request_races(tmp_path):
    """Execute actual template JS without fetching records or external pages."""
    websocket = pytest.importorskip("websocket")
    executable = Path(os.environ["AURORA_TEST_EDGE"])
    assert executable.is_file()
    profile = tmp_path / "edge-profile"
    process = subprocess.Popen([
        str(executable), "--headless=new", "--disable-gpu", "--no-first-run",
        "--no-default-browser-check", "--disable-background-networking",
        "--disable-component-update", "--disable-sync", "--metrics-recording-only",
        "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=0",
        f"--user-data-dir={profile}", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    connection = None
    try:
        port_file = profile / "DevToolsActivePort"
        for _ in range(100):
            if port_file.is_file():
                break
            assert process.poll() is None, "Local Edge exited before readiness"
            time.sleep(.1)
        assert port_file.is_file(), "Local Edge did not expose loopback DevTools"
        port = int(port_file.read_text().splitlines()[0])
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5) as response:
            pages = json.load(response)
        target = next(page for page in pages if page["type"] == "page")
        connection = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=10, suppress_origin=True)
        call_id = 0

        def command(method, params):
            nonlocal call_id
            call_id += 1
            connection.send(json.dumps({"id": call_id, "method": method, "params": params}))
            while True:
                result = json.loads(connection.recv())
                if result.get("id") == call_id:
                    assert "error" not in result, result
                    return result["result"]

        command("Page.navigate", {"url": PAGE.as_uri()})
        for _ in range(100):
            ready = command("Runtime.evaluate", {"expression": "typeof render", "returnByValue": True})
            if ready["result"].get("value") == "function":
                break
            time.sleep(.1)
        else:
            pytest.fail("Operator display JavaScript did not initialise")
        script = """(async () => {
 const assert = (condition, message) => {if (!condition) throw new Error(message);};
 const synthetic = [
  {conversation_id:'enquiry-one',site_id:'local',created_at:'2026-10-03',
   problem_statement:'Cold brick wall',email:'synthetic@example.invalid',
   sales_brief:{decision_status:'HUMAN_REVIEW_REQUIRED',approval:null,
    known_facts:{construction:'<img src=x onerror=alert(1)>',access:'lining stays intact'},
    capture_completeness:{unresolved_fields:['airspace'],field_status:{airspace:'unknown'}},
    operator_questions:['Confirm airspace?'],candidates:[{family_id:'TEST_WALL',name:'Synthetic wall family',
     disposition:'HOLD',reasons:['No installation approval'],evidence:{source_gaps:['Missing local PDF']}}]}},
  {conversation_id:'legacy-two',site_id:'local',created_at:'2026-10-02',problem_statement:'Legacy floor',
   sales_brief:{decision_status:'LEGACY_REQUIRES_REVIEW',candidates:[],approval:null}}
 ];
 records = synthetic; render();
 assert(document.querySelectorAll('article').length===2,'Expected one card per enquiry');
 assert(el('briefs').textContent.includes('airspace - unknown') ||
  el('briefs').textContent.includes('Reflective airspace - unknown'),'Missing unresolved information');
 assert(el('briefs').textContent.includes('Legacy enquiry'),'Legacy fallback missing');
 assert(el('briefs').textContent.includes('Missing local PDF'),'Missing source gaps');
 assert(el('briefs').textContent.includes('<img src=x'),'Untrusted text should be literal');
 assert(!el('briefs').querySelector('img'),'Untrusted content created an element');
 el('search').value='enquiry-one';render();
 assert(document.querySelectorAll('article').length===1,'ID filter failed');
 el('search').value='floor';render();
 assert(document.querySelectorAll('article').length===1,'Problem filter failed');
 el('search').value='nonexistent';render();
 assert(document.querySelectorAll('article').length===0,'Empty filter failed');
 lock();el('site').value='local';
 let request;
 window.fetch=async (url, options)=>{request={url,options};return {ok:true,json:async()=>synthetic};};
 el('key').value='synthetic-operator';
 await el('access').onsubmit({preventDefault(){}});
 assert(request.options.headers['X-Aurora-Lead-Admin-Key']==='synthetic-operator','Missing separate header');
 assert(!request.url.includes('synthetic-operator'),'Key leaked in URL');
 assert(el('key').value==='' && !el('key').required,'Key field not cleared or refresh blocked');
 assert(records.length===2,'Authenticated read did not render');
 await el('access').onsubmit({preventDefault(){}});
 assert(records.length===2,'In-memory refresh failed');
 let release;
 window.fetch=()=>new Promise(resolve=>{release=resolve;});
 const pending=el('access').onsubmit({preventDefault(){}});
 lock();
 release({ok:true,json:async()=>synthetic});
 await pending;
 assert(records.length===0 && el('briefs').children.length===0,'Stale response repopulated locked page');
 assert(operatorKey==='' && el('key').required,'Lock did not clear key or restore required input');
 window.fetch=async()=>({ok:true,json:async()=>[]});
 el('key').value='synthetic-operator';
 await el('access').onsubmit({preventDefault(){}});
 assert(el('status').textContent.includes('No saved enquiries'),'Empty state missing');
 window.fetch=async()=>({ok:false,status:503});
 await el('access').onsubmit({preventDefault(){}});
 assert(el('status').textContent.includes('disabled') && !operatorKey,'Disabled operator error not explicit');
 return 'render, filter, XSS escaping, refresh, lock, stale responses and empty/error states passed';
})()"""
        result = command("Runtime.evaluate", {"expression": script, "awaitPromise": True, "returnByValue": True})
        assert "exceptionDetails" not in result, result.get("exceptionDetails")
        assert "passed" in result["result"]["value"]
    finally:
        if connection is not None:
            connection.close()
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=20)
