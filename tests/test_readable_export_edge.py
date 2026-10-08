"""Exercise actual UI JavaScript in installed Edge without external resources."""
import json
from pathlib import Path
import socket
import subprocess
import time
import urllib.request

import pytest


def test_edge_download_full_text_copy_error_and_lock_cleanup(tmp_path):
    websocket = pytest.importorskip("websocket")
    edge = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
    if not edge.is_file():
        pytest.skip("Installed Edge unavailable")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen([
        str(edge), "--headless=new", "--disable-gpu", "--no-first-run",
        "--remote-allow-origins=http://localhost", f"--remote-debugging-port={port}",
        f"--user-data-dir={tmp_path / 'edge'}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    connection = None
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        deadline = time.monotonic() + 20
        while True:
            try:
                with opener.open(f"http://127.0.0.1:{port}/json/list", timeout=1) as response:
                    pages = json.load(response)
                page = next(p for p in pages if p["type"] == "page")
                break
            except (OSError, StopIteration):
                if time.monotonic() > deadline:
                    raise
                time.sleep(.1)
        connection = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=15,
                                                 origin="http://localhost", http_proxy_host=None)
        sequence = 0
        def call(method, params):
            nonlocal sequence
            sequence += 1
            connection.send(json.dumps({"id": sequence, "method": method, "params": params}))
            while True:
                result = json.loads(connection.recv())
                if result.get("id") == sequence:
                    assert "error" not in result, result
                    return result.get("result", {})
        call("Browser.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(tmp_path)})
        call("Runtime.enable", {})
        template = (Path(__file__).resolve().parents[1] / "templates" / "product_research.html").read_text()
        script = template.split("<script>", 1)[1].split("</script>", 1)[0]
        parsed = call("Runtime.compileScript", {"expression": script, "sourceURL": "product_research.js",
                                               "persistScript": False})
        assert "exceptionDetails" not in parsed, parsed
        start = template.index("function action(")
        end = template.index("async function loadOverview", start)
        code = template[start:end]
        handler = next(line for line in template.splitlines() if "exportJSON.onclick=" in line)
        text = "FULL RETAINED GUIDE\nSource page 1\nUnicode: \u00ae\n" * 1000
        setup = """
document.body.innerHTML='<div id="detail"></div>';
const $=id=>document.getElementById(id);
const node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
let messages=[];function message(text,error){messages.push({text,error:!!error});}
let selected={family:{family_id:'SYNTHETIC'}},epoch=1;
const json=JSON.stringify;
const exportJSON=node('button'),exportTXT=node('button'),toolbar=node('div');
"""
        expression = setup + code + "\nconst fullText=" + json.dumps(text) + ";" + """
async function api(path){return {readable:fullText};}
""" + handler + """
await exportTXT.onclick();
if(document.querySelector('textarea').value!==fullText)throw new Error('Incomplete fallback');
Object.defineProperty(navigator,'clipboard',{value:undefined,configurable:true});
await document.querySelector('details button').onclick();
if(!messages.some(m=>m.error&&m.text.includes('Clipboard unavailable')))throw new Error('Missing explicit error');
document.getElementById('detail').replaceChildren();
if(document.querySelector('textarea'))throw new Error('Private fallback survives clear');
return true;
"""
        result = call("Runtime.evaluate", {"expression": "(async()=>{" + expression + "})()",
                                          "awaitPromise": True, "returnByValue": True})
        assert "exceptionDetails" not in result, result
        deadline = time.monotonic() + 10
        downloaded = tmp_path / "SYNTHETIC.txt"
        while not downloaded.is_file():
            if time.monotonic() > deadline:
                pytest.fail("Readable download did not arrive in Edge")
            time.sleep(.1)
        assert downloaded.read_text(encoding="utf-8") == text
    finally:
        if connection:
            connection.close()
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
