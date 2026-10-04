"""Frozen private source compilation with local-Llama reconciliation receipts."""
import csv
from html import escape
import json
from pathlib import Path
from urllib.parse import quote

from tds_cache_inventory import inventory
from tds_build import checksum, checked_extraction, digest, version, save


def resolved_path(value):
    return Path(str(value).removeprefix("\\\\?\\")).resolve()


def cached_rows(sources, files):
    rows = []
    for file in files:
        for family in sources.get(file["sha256"],{}).get("families",[]) or [""]:
            rows.append(dict(family_id=family,url="",display_url="",final_url="",path=file["path"],filename=file["filename"],sha256=file["sha256"],status="cached" if family else "unassigned",provenance="archive_hash" if family else "unassigned_file",confidence="hash_association_unapproved" if family else "unknown"))
    return rows


def supplied_rows(directory, manifest, files):
    rows = []
    for r in manifest['rows']:
        p = directory / 'downloads' / (checksum(r['url'])[:24] + '.json')
        receipt = json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
        matches = [f for f in files if f['sha256'] == receipt.get('sha256') and not r['holds']] or [dict(path='', filename='', sha256='')]
        for f in matches:
            status = 'held' if r['holds'] else receipt.get('status', 'unavailable')
            if status == 'archived' and not f['path']:
                raise ValueError("Archived download is missing from the cache inventory")
            rows.append(dict(family_id=r['family_id'], url=r['url'], display_url=r['display_url'], final_url=receipt.get('final_url', ''), path=f['path'], filename=f['filename'], sha256=f['sha256'], status=status, provenance=json.dumps(dict(sheet=r['sheet'], row=r['row'], holds=r['holds'], error=receipt.get('error'))), confidence='source_recorded_unapproved'))
    return rows


def source_rows(build, build_id, index, files):
    directory, manifest = build.job(build_id)
    rows = cached_rows(build.sources(build_id), files) + supplied_rows(directory, manifest, files)
    seen = {r['family_id'] for r in rows}
    for key in index.families:
        if key not in seen:
            rows.append({'family_id': key, 'url': '', 'display_url': '', 'final_url': '', 'path': '', 'filename': '', 'sha256': '', 'status': 'no_source', 'provenance': 'collection_frozen', 'confidence': 'unknown'})
    return rows


def render_family(family_id, rows):
    lines = ["## "+(family_id or "Unassigned documents"),"","Private source register; claims unapproved.","","| TDS URLs | File | Full path | Status | Provenance | Confidence |","| --- | --- | --- | --- | --- | --- |"]
    def esc(value):
        return escape(str(value)).replace("|", "&#124;").replace("\n", " ").replace("\r", " ").replace("[", "&#91;").replace("]", "&#93;")
    for r in rows:
        if r["family_id"] != family_id:
            continue
        urls = " ; ".join(
            "[TDS](" + quote(url, safe=":/?=&%+#@") + ")"
            for url in dict.fromkeys(r[k] for k in ("url", "display_url", "final_url") if r[k])
            if url.startswith("https://"))
        urls += " " + " ; ".join(esc(url) for url in dict.fromkeys(
            r[k] for k in ("url", "display_url", "final_url") if r[k]))
        file = "["+esc(r["filename"])+"]("+Path(r["path"]).as_uri().replace("(", "%28").replace(")", "%29")+")" if r["path"] else "No verified cached file"
        cells = [urls or "No supplied URL",file,esc(r["path"]),esc(r["status"]),esc(r["provenance"]),esc(r["confidence"])]
        lines.append("| "+" | ".join(cells)+" |")
    return "\n".join(lines)+"\n"


def export_csv(folder, rows):
    temp = Path(folder) / "register.csv.tmp"
    with temp.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: (chr(39) + v if v.startswith(("=", "+", "-", "@", "\t", "\r")) else v) for k, v in row.items()})
    temp.replace(folder / "register.csv")
    return str(folder / "register.csv")


def export_register(folder, payload):
    folder.mkdir(parents=True, exist_ok=True)
    save(folder / "register.json", payload)
    csv_path = export_csv(folder, payload["rows"])
    parts = ["# Frozen private TDS register", payload["warning"]]
    parts.extend(render_family(key, payload["rows"]) for key in payload["families"])
    for key in sorted({row["family_id"] for row in payload["rows"]} - set(payload["families"]) - {""}):
        parts.append(render_family(key, payload["rows"]))
    parts.append(render_family("", payload["rows"]))
    if payload.get("unassigned_review"):
        parts.extend(["## Local Llama unassigned-source suggestions",
                      "Advisory only; no family binding or claim approval was changed.",
                      json.dumps(payload["unassigned_review"], ensure_ascii=True, indent=2)])
    temp = folder / "register.md.tmp"
    temp.write_text("\n\n".join(parts), encoding="utf-8")
    temp.replace(folder / "register.md")
    return {"json": str(folder / "register.json"), "csv": csv_path,
            "md": str(folder / "register.md")}


def compile_register(build, build_id, index):
    directory, manifest = build.job(build_id)
    files = inventory(build.cache)
    rows = source_rows(build, build_id, index, files)
    sources = build.sources(build_id)
    documents = {}
    for sha, source in sources.items():
        parser = ("full-pages-v1/pypdf-" + version("pypdf") if source["suffix"] == ".pdf"
                  else "docx-paragraphs-tables-v1")
        path = build.path("extraction", checksum({"sha": sha, "parser": parser}) + ".json")
        extracted = checked_extraction(path, sha, parser)
        documents[sha] = {"sha256": sha, "families": source["families"],
                          "provenance": source["provenance"], "rights": source["rights"],
                          "extraction_path": str(path), "extraction_hash": digest(path),
                          "extraction_status": extracted["status"],
                          "page_count": len(extracted["pages"]),
                          "source_excerpt": next((page["text"][:700] for page in extracted["pages"]
                                                  if page["text"].strip()), ""),
                          "source_excerpt_page": next((page["page"] for page in extracted["pages"]
                                                       if page["text"].strip()), None),
                          "claim_approval": "not_granted"}
    audit_path = build.path("reports", "family-gap-audit-20261004", "audit.json")
    advisory = None
    if audit_path.is_file():
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        if audit["build_id"] != build_id:
            raise ValueError("Local Llama audit belongs to a different build")
        advisory = {"model": audit["model"], "findings": audit["local_review"],
                    "path": str(audit_path), "sha256": digest(audit_path),
                    "status": "unverified_advisory_not_family_bindings"}
    unassigned_path = build.path("reports", "unassigned-source-review.json")
    unassigned = None
    if unassigned_path.is_file():
        unassigned = json.loads(unassigned_path.read_text(encoding="utf-8"))
        if unassigned["build_id"] != build_id:
            raise ValueError("Unassigned review belongs to another build")
    families = sorted(index.families)
    payload = {"version": 1, "build_id": build_id, "authoring_preview": manifest["authoring_preview"],
               "collection": "frozen", "families": families, "rows": rows,
               "inventory": files, "documents": documents, "local_llama_review": advisory,
               "unassigned_review": unassigned,
               "retained_packs": str(build.path("current.json")),
               "retained_packs_hash": digest(build.path("current.json")),
               "warning": "PRIVATE. Collection frozen; file integrity and recorded association "
                          "do not authenticate origin, regional applicability or approve claims."}
    if not set(families).issubset({row["family_id"] for row in rows}):
        raise ValueError("Compiled register omitted families")
    if {file["path"] for file in files} != {row["path"] for row in rows if row["path"]}:
        raise ValueError("Compiled register omitted cache files")
    for row in manifest["rows"]:
        if not any(item["family_id"] == row["family_id"] and item["url"] == row["url"]
                   and item["display_url"] == row["display_url"] for item in rows):
            raise ValueError("Compiled register omitted supplied URL")
    if inventory(build.cache) != files:
        raise ValueError("Sources changed during compilation")
    folder = resolved_path(build.path("reports", "tds-register-" + checksum(payload)[:20]))
    outputs = export_register(folder, payload)
    pointer = {"version": 1, "cache": str(build.cache), "build_id": build_id,
               "authoring_preview": manifest["authoring_preview"],
               "outputs": outputs, "sha256": digest(Path(outputs["json"]))}
    save(build.root / "data" / "local" / "tds_register.json", pointer)
    return pointer


def compiled_sources(root, family_id):
    pointer_path = Path(root) / "data" / "local" / "tds_register.json"
    if not pointer_path.is_file():
        return {"state": "not_compiled", "collection": "unknown", "sources": [],
                "documents": [], "local_llama_findings": [], "unassigned_suggestions": [],
                "approval": "not_granted"}
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    if pointer["version"] != 1:
        raise ValueError("Unsupported compiled source pointer")
    cache = resolved_path(pointer["cache"])
    path = resolved_path(pointer["outputs"]["json"])
    if not path.is_relative_to(cache / "AuroraKnowledge" / "reports"):
        raise ValueError("Compiled register escapes managed reports")
    if digest(path) != pointer["sha256"]:
        raise ValueError("Compiled register hash mismatch")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload["build_id"] != pointer["build_id"] or payload["version"] != 1:
        raise ValueError("Compiled register identity mismatch")
    rows = [row.copy() for row in payload["rows"] if row["family_id"] == family_id]
    stale = False
    for row in rows:
        if row["path"]:
            source = resolved_path(row["path"])
            if not source.is_relative_to(cache):
                raise ValueError("Compiled source escapes cache")
            row["file_current"] = source.is_file() and digest(source) == row["sha256"]
            stale |= not row["file_current"]
    documents = [doc for doc in payload["documents"].values()
                 if family_id in doc["families"]]
    for doc in documents:
        extraction = resolved_path(doc["extraction_path"])
        if not extraction.is_relative_to(cache / "AuroraKnowledge" / "extraction"):
            raise ValueError("Compiled extraction escapes cache")
        stale |= not extraction.is_file() or digest(extraction) != doc["extraction_hash"]
    pack_pointer = Path(payload["retained_packs"])
    stale |= not pack_pointer.is_file() or digest(pack_pointer) != payload["retained_packs_hash"]
    return {"state": "stale" if stale else "compiled", "collection": "frozen",
            "sources": rows, "documents": documents,
            "local_llama_findings": [r for r in (payload.get("local_llama_review") or {}).get("findings", [])
                                    if r["family_id"] == family_id],
            "unassigned_suggestions": [r for r in (payload.get("unassigned_review") or {}).get("reviews", [])
                                      if r["family_id"] == family_id],
            "register": pointer["outputs"]["md"], "approval": "not_granted",
            "warning": payload["warning"]}
