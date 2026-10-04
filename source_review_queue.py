"""Private source decisions never bind documents or approve technical claims."""
from tds_build import checksum


def items_for_family(compiled, family_id):
    sources = set()
    items = []

    for source in compiled['sources']:
        source_hash = source['sha256']
        if source_hash not in sources and (source_hash or source['url'] or source['provenance']) not in sources:
            sources.add(source_hash or source['url'] or source['provenance'])
            item = {
                'family_id': family_id,
                'source_hash': source_hash,
                'source_path': source['path'],
                'source_url': source['url'],
                'kind': 'document_identity_origin_variant' if source_hash else 'unavailable_or_held_source',
                'status': 'pending',
                'approval': False,
                'reason': 'Confirm product identity, origin, edition and regional variant; collection frozen, no redownload required.',
                'locator': source['provenance'],
                'id': checksum({'family_id': family_id, 'source': source})[:24]
            }
            items.append(item)

    for doc in compiled['documents']:
        if doc['extraction_status'] != 'text_extracted':
            item = {
                'family_id': family_id,
                'source_hash': doc['sha256'],
                'kind': 'extraction_gap',
                'status': 'pending',
                'approval': False,
                'reason': 'Review retained original pages; incomplete extraction is not lost source.',
                'locator': doc['source_excerpt_page'],
                'quote': doc['source_excerpt'],
                'id': checksum({'family_id': family_id, 'document': doc})[:24]
            }
            items.append(item)

    if not any(source["sha256"] for source in compiled["sources"]):
        item = {
            'family_id': family_id,
            'kind': 'standalone_source_need',
            'status': 'pending',
            'approval': False,
            'reason': 'Confirm whether standalone TDS is needed, particularly accessory families.',
            'locator': '',
            'source_hash': ''
        }
        item['id'] = checksum(item)[:24]
        items.append(item)

    return items


def review_view(compiled, family_id, history=()):
    items = items_for_family(compiled, family_id)
    for finding in compiled.get("unassigned_suggestions", []):
        item = {
            "family_id": family_id, "source_hash": finding["sha256"],
            "kind": "proposed_document_association", "status": "pending",
            "approval": False, "quote": finding["quote"], "reason": finding["reason"],
            "locator": "local_llama_exact_quote", "model_status": "unverified_advisory",
        }
        item["id"] = checksum(item)[:24]
        items.append(item)
    for item in items:
        revisions = [row for row in history
                     if row["kind"] == "source_identity_review"
                     and row["target"] == "source-review:" + family_id + ":" + item["id"]]
        if revisions:
            latest = max(revisions, key=lambda row: row["id"])
            item["status"] = latest["payload"]["decision"]
            item["revision"] = latest["id"]
            item["reviewer"] = latest["actor"]
            item["rationale"] = latest["payload"]["rationale"]
    return {"state": compiled["state"], "collection": compiled["collection"], "items": items,
            "local_llama_findings": compiled.get("local_llama_findings", []),
            "warning": "Decisions record identity/provenance review only. No binding, claim or recommendation approval."}
