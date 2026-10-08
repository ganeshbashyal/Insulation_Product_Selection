"""Private local competitor evidence; never consumed by public facts or eligibility."""
from __future__ import annotations

import json
from pathlib import Path
import re

from local_source_review import checked_pages, file_hash


def comparison(root: Path, idx) -> dict:
    records = []
    errors = []
    directory = root / "data" / "local" / "competitors"
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        key = data.get("competitor_id")
        if not isinstance(key,str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}",key):
            raise ValueError(f"{path.name}: stable competitor_id required")
        if any(row["competitor_id"]==key for row in records):
            raise ValueError(f"Duplicate competitor identity: {key}")
        if data.get("our_family_id") not in idx.families:
            raise ValueError(f"{path.name}: unknown our_family_id")
        if not isinstance(data.get("name"),str) or not isinstance(data.get("claims"),list):
            raise ValueError(f"{path.name}: name and claims required")
        claims=[]
        for claim in data["claims"]:
            required={"metric","value","unit","variant","scope","test_standard","test_context","citation"}
            if not isinstance(claim,dict) or not required.issubset(claim):
                raise ValueError(f"{path.name}: scoped claim fields required")
            cite=claim["citation"]
            if not isinstance(cite,dict) or not {"path","sha256","page","quote"}.issubset(cite):
                raise ValueError(f"{path.name}: exact local citation required")
            if not isinstance(cite["path"],str) or type(cite["page"]) is not int or cite["page"]<1 or not isinstance(cite["quote"],str) or not cite["quote"].strip():
                raise ValueError(f"{path.name}: invalid citation")
            pdf=(root/cite["path"]).resolve()
            if not pdf.is_relative_to((root/"data").resolve()) or pdf.suffix.casefold()!=".pdf":
                raise ValueError(f"{path.name}: competitor document must be in local data library")
            status="source_missing"
            if pdf.is_file():
                if file_hash(pdf)!=cite["sha256"]:
                    status="stale_source"
                else:
                    pages=checked_pages(pdf, cite["sha256"])
                    text=next((page["text"] for page in pages["pages"] if page["page"]==cite["page"]),"")
                    status="cited_text_not_human_approval" if " ".join(cite["quote"].split()).casefold() in " ".join(text.split()).casefold() else "quote_not_found"
            if status!="cited_text_not_human_approval":
                errors.append(f"{key}: {claim['metric']} / {status}")
            claims.append({**claim,"status":status,"review_status":"pending_human_review"})
        records.append({"competitor_id":key,"name":data["name"],"our_family_id":data["our_family_id"],
                        "claims":claims,"notes":data.get("notes",""),
                        "comparison_rule":"Match metric, unit, exact variant, product/system scope and test standard/context. Differences or missing values are not equivalent; no winner."})
    return {"competitors":records,"errors":errors,"public_use":False,"automatic_winner":False,
            "note":"Local internal comparison only. Supplied claims are not approvals; unknown is not zero."}
