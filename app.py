from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

APP_TITLE = "Insulation Sales Engineer"
REPO_ROOT = Path(__file__).resolve().parent
CATALOGUE_FILES = [
    REPO_ROOT / "knowledge" / "thermotec" / "families.json",
    REPO_ROOT / "knowledge" / "fletcher" / "families.json",
]

QUESTIONS = [
    ("challenge", "What are you trying to improve, and what noise, heat, condensation or comfort problem are you experiencing?"),
    ("application", "Where is it—for example an internal wall, floor, roof, hot-water pipe, waste pipe, plant room or outdoor fence?"),
    ("priority", "What matters most: acoustic comfort, energy efficiency, sustainability, installation practicality, budget or documented compliance?"),
    ("conditions", "What conditions matter—temperature, pipe size, floor finish, weather/UV exposure, limited space or another constraint?"),
    ("project", "Is this residential, commercial or industrial—and a new build, renovation, repair or retrofit?"),
    ("requirements", "Is there an Rw/Rw+Ctr target, NCC, fire, BAL, consultant or project specification? It is fine if you are not sure."),
    ("contact", "Would you prefer to call the team, receive a callback, or have the enquiry emailed for review? No real contact details are needed in this demo."),
]

PRIORITY_LABELS = {
    "acoustic_comfort": "Acoustic comfort",
    "energy_efficiency": "Energy efficiency",
    "sustainability": "Sustainability",
    "installation_practicality": "Installation practicality",
    "compliance_readiness": "Evidence readiness",
}
PRIORITY_TERMS = {
    "acoustic_comfort": ["acoustic", "quiet", "noise", "sound", "comfort"],
    "energy_efficiency": ["energy", "thermal", "heat", "condensation", "efficiency", "r-value", "r value"],
    "sustainability": ["sustainable", "sustainability", "environment", "recycled", "low carbon"],
    "installation_practicality": ["install", "easy", "access", "space", "thin", "practical", "retrofit"],
    "compliance_readiness": ["compliance", "ncc", "fire", "bal", "spec", "consultant", "certification"],
}
EXAMPLES = {
    "Airborne wall noise": [
        "We hear conversations and television through the wall.", "An existing internal stud wall between a bedroom and living room.",
        "Acoustic comfort first, with minimal added thickness.", "The wall cavity is accessible during renovation.",
        "Residential renovation in Melbourne.", "No target is known and I am not sure about fire requirements.", "Please arrange an afternoon callback.",
    ],
    "Noisy waste pipe": [
        "Water movement in a waste pipe is loud in the bedroom.", "A 100 mm PVC waste pipe in a boxed service riser.",
        "Acoustic comfort and practical installation in tight access.", "Indoor service, limited access, temperature is not high.",
        "Apartment renovation.", "The consultant detail is available but I do not know the clause.", "Email the enquiry for review.",
    ],
    "Outdoor solar pipe": [
        "We need to reduce heat loss from solar hot-water pipes.", "Copper pipe running outside on the roof.",
        "Energy efficiency and weather durability.", "High temperature with continuous sun and UV exposure; pipe size is 22 mm.",
        "Residential retrofit.", "The plumber needs an NCC-suitable system but no clause was supplied.", "Please arrange a callback.",
    ],
    "Hot metal shed": [
        "The metal shed becomes extremely hot in summer.", "Under a new metal roof and in the walls.",
        "Energy efficiency and summer comfort.", "The roof has a ventilated air space; condensation design is not complete.",
        "Commercial shed refurbishment.", "The certifier will review NCC and condensation requirements.", "Email the project brief.",
    ],
}


@st.cache_data
def load_catalogue() -> dict:
    families = []
    for path in CATALOGUE_FILES:
        data = json.loads(path.read_text(encoding="utf-8"))
        default_manufacturer = path.parent.name.title()
        for family in data["families"]:
            families.append({**family, "manufacturer": family.get("manufacturer", default_manufacturer), "catalogue_file": path.relative_to(REPO_ROOT).as_posix()})
    return {"families": families, "rating_scale": "1 = low relevance, 3 = useful, 5 = primary strength; ratings guide discovery and are not compliance or performance certificates"}


CATALOGUE = load_catalogue()
FAMILIES = CATALOGUE["families"]


def initialise_state() -> None:
    defaults = {
        "messages": [{"role": "assistant", "content": "Thanks for calling. I’ll capture the application and priorities, then prepare an evidence-linked product-family pathway for technical review. " + QUESTIONS[0][1]}],
        "answers": {}, "step": 0, "demo_complete": False, "human_approved": False, "myob_quote": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_demo() -> None:
    for key in ["messages", "answers", "step", "demo_complete", "human_approved", "myob_quote"]:
        st.session_state.pop(key, None)
    initialise_state()


def detected_priority(text: str) -> str:
    folded = text.casefold()
    scored = {key: sum(term in folded for term in terms) for key, terms in PRIORITY_TERMS.items()}
    best = max(scored, key=scored.get)
    return best if scored[best] else "acoustic_comfort"


def rank_families(answers: dict[str, str], manufacturer_scope: str | None = None) -> list[dict]:
    text = " ".join(answers.values()).casefold()
    priority = detected_priority(answers.get("priority", ""))
    ranked = []
    for family in FAMILIES:
        if manufacturer_scope and manufacturer_scope != "Compare both" and family["manufacturer"].casefold() != manufacturer_scope.casefold():
            continue
        keyword_hits = [term for term in family["keywords"] if term.casefold() in text]
        application_hits = [term for term in family["applications"] if term.casefold() in text]
        score = len(keyword_hits) * 4 + len(application_hits) * 3 + family["scores"].get(priority, 0) * 0.35
        if family["confidence"] == "identity_unverified":
            score -= 6
        ranked.append({**family, "match_score": score, "matched": keyword_hits + application_hits, "priority_key": priority})
    return sorted(ranked, key=lambda item: (item["match_score"], item["scores"].get(priority, 0)), reverse=True)


def recommendation_allowed(family: dict | None) -> bool:
    return bool(family and family["confidence"].startswith("manufacturer_supported"))


def technical_gate(answers: dict[str, str], family: dict | None) -> tuple[str, str]:
    if family and family["confidence"] == "identity_unverified":
        return "BLOCKED", "The catalogue identity is unverified. Manufacturer or purchasing confirmation is mandatory."
    requirements = answers.get("requirements", "").casefold()
    if any(term in requirements for term in ["rw", "ncc", "fire", "bal", "bushfire", "consultant", "spec", "certifier"]):
        return "REVIEW REQUIRED", "A stated technical or regulatory requirement must be checked against the complete installed system."
    return "REVIEW REQUIRED", "The demo may recommend this documented family; a person must still confirm construction, size/grade, evidence and availability before quoting."


def confidence_label(value: str) -> str:
    labels = {
        "manufacturer_supported": "Manufacturer supported",
        "manufacturer_supported_performance_pending": "Manufacturer supported · data extraction pending",
        "manufacturer_supported_classification_pending": "Manufacturer supported · classification pending",
        "secondary_owned_source_only": "Owned-site source only · verification required",
        "identity_unverified": "Identity unverified · blocked",
    }
    return labels.get(value, value.replace("_", " ").title())


def process_customer_message(prompt: str) -> None:
    st.session_state.messages.append({"role": "user", "content": prompt})
    if st.session_state.step < len(QUESTIONS):
        key, _ = QUESTIONS[st.session_state.step]
        st.session_state.answers[key] = prompt.strip()
        st.session_state.step += 1
    if st.session_state.step < len(QUESTIONS):
        st.session_state.messages.append({"role": "assistant", "content": "Thanks, I’ve noted that. " + QUESTIONS[st.session_state.step][1]})
    else:
        st.session_state.demo_complete = True
        top = rank_families(st.session_state.answers, st.session_state.get("manufacturer_scope", "Compare both"))[0]
        match_reason = ", ".join(top["matched"][:3]) or top["primary_function"].lower()
        if recommendation_allowed(top):
            reply = f"Based on the information provided, this demo recommends the **{top['name']} family** because the enquiry aligns with {match_reason}. This is a family-level recommendation—not a confirmed SKU, grade, quantity, installed result or compliance decision. A team member must verify those details before any quote or order."
        else:
            reply = f"The closest catalogue match is **{top['name']}**, but the demo cannot recommend it because its evidence status is {confidence_label(top['confidence']).lower()}. The enquiry has been flagged for human verification before selection or quotation."
        st.session_state.messages.append({"role": "assistant", "content": reply})


def load_example(name: str) -> None:
    reset_demo()
    for answer in EXAMPLES[name]:
        process_customer_message(answer)


def score_frame(families: list[dict]) -> pd.DataFrame:
    rows = [{"Family": f["name"], **{label: f["scores"].get(key, 0) for key, label in PRIORITY_LABELS.items()}} for f in families]
    return pd.DataFrame(rows).set_index("Family")


def callback_payload() -> dict:
    ranked = rank_families(st.session_state.answers, st.session_state.get("manufacturer_scope", "Compare both")) if st.session_state.answers else []
    top = ranked[0] if ranked else None
    gate, reason = technical_gate(st.session_state.answers, top)
    return {
        "created_at": datetime.now().isoformat(timespec="seconds"), "demo_only": True,
        "customer_answers": st.session_state.answers,
        "demo_recommendation": ({"family_id": top["family_id"], "name": top["name"], "scope": "product_family_only"} if recommendation_allowed(top) else None),
        "candidate_families": [{"family_id": x["family_id"], "name": x["name"], "confidence": x["confidence"]} for x in ranked[:3]],
        "technical_review": {"status": gate, "reason": reason},
        "myob_status": "mock_draft_created" if st.session_state.myob_quote else "not_created",
        "catalogue_sources": [path.relative_to(REPO_ROOT).as_posix() for path in CATALOGUE_FILES],
    }


st.set_page_config(page_title=APP_TITLE, page_icon="◉", layout="wide")
initialise_state()
st.markdown("""
<style>
:root{--ink:#17232c;--muted:#66737c;--teal:#087f7a;--teal2:#0aa39a;--line:#dce3df}.stApp{background:linear-gradient(135deg,#f7faf8 0%,#eef5f3 55%,#f6f1e8 100%);color:var(--ink)}[data-testid="stHeader"]{background:rgba(247,250,248,.75)}.block-container{max-width:1500px;padding-top:1.1rem;padding-bottom:2rem}h1,h2,h3{letter-spacing:-.025em;color:var(--ink)}.hero{background:#102b32;border-radius:22px;padding:1.35rem 1.55rem;color:white;box-shadow:0 18px 50px rgba(21,48,54,.14);margin-bottom:.7rem}.hero h1{color:white;margin:.15rem 0 .25rem;font-size:2rem}.hero p{color:#c7dedb;margin:0}.eyebrow,.panel-title{color:var(--teal);font-size:.77rem;font-weight:800;letter-spacing:.12em;text-transform:uppercase}.pill{display:inline-block;background:#e5a647;color:#2b2113;padding:.28rem .58rem;border-radius:99px;font-size:.72rem;font-weight:800}.card{background:rgba(255,255,255,.84);border:1px solid var(--line);border-radius:16px;padding:.85rem 1rem;margin:.48rem 0}.card .label{color:var(--muted);font-size:.72rem;text-transform:uppercase;letter-spacing:.08em;font-weight:700}.card .value{color:var(--ink);font-size:1.02rem;font-weight:760;margin-top:.18rem}.card .note{color:var(--muted);font-size:.82rem;margin-top:.3rem;line-height:1.4}.gate{border-left:4px solid #df8b2e}.good{border-left:4px solid var(--teal2)}.blocked{border-left:4px solid #c8463a}[data-testid="stChatMessage"]{background:rgba(255,255,255,.75);border:1px solid var(--line);border-radius:16px;padding:.25rem .7rem;margin-bottom:.6rem}[data-testid="stSidebar"]{background:#102b32}[data-testid="stSidebar"] *{color:#eef8f6}[data-testid="stSidebar"] .stButton button{background:#1b444b;color:white;border-color:#35636a}.small-note{color:var(--muted);font-size:.78rem;line-height:1.45}div[data-testid="stProgress"]>div>div{background-color:var(--teal2)}
</style>""", unsafe_allow_html=True)
st.markdown("""<div class="hero"><span class="pill">TWO-MANUFACTURER POC</span><div class="eyebrow" style="color:#78d7d0;margin-top:.65rem">Evidence-led customer conversation</div><h1>Insulation Sales Engineer</h1><p>Qualify the problem, compare Fletcher and Thermotec, and recommend the best documented product family.</p></div>""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("## Demo controls")
    st.caption("Choose a realistic scenario or enter your own answers.")
    manufacturer_scope = st.radio("Manufacturer scope", ["Compare both", "Thermotec", "Fletcher"], horizontal=False, key="manufacturer_scope")
    example_name = st.selectbox("Scenario", list(EXAMPLES))
    if st.button("▶ Load scenario", width="stretch"):
        load_example(example_name); st.rerun()
    if st.button("↻ Start again", width="stretch"):
        reset_demo(); st.rerun()
    st.divider()
    count_cols = st.columns(2)
    count_cols[0].metric("Thermotec", sum(x["manufacturer"] == "Thermotec" for x in FAMILIES))
    count_cols[1].metric("Fletcher", sum(x["manufacturer"] == "Fletcher" for x in FAMILIES))
    st.caption("280 Thermotec and 134 Fletcher Sheet1 rows are represented. Evidence gates remain visible.")
    st.markdown("✓ Evidence-linked family records\n\n✓ Priority comparison\n\n✓ Human technical gate\n\n◌ MYOB — simulated only")

conversation_tab, explorer_tab, architecture_tab = st.tabs(["Customer conversation", "Product range explorer", "Demo architecture"])
with conversation_tab:
    chat_col, work_col = st.columns([1.35, 1], gap="large")
    with chat_col:
        st.markdown('<div class="panel-title">Customer conversation</div>', unsafe_allow_html=True)
        st.progress(min(st.session_state.step / len(QUESTIONS), 1.0), text=f"Enquiry captured: {st.session_state.step} of {len(QUESTIONS)} areas")
        for message in st.session_state.messages:
            with st.chat_message(message["role"]): st.markdown(message["content"])
        if not st.session_state.demo_complete:
            prompt = st.chat_input("Type the customer's response…")
            if prompt: process_customer_message(prompt); st.rerun()
        else: st.success("Enquiry complete. The sales-engineer brief is ready for review.")
    with work_col:
        st.markdown('<div class="panel-title">Sales engineer workspace</div>', unsafe_allow_html=True)
        answers = st.session_state.answers
        ranked = rank_families(answers, manufacturer_scope) if answers else []
        top = ranked[0] if ranked else None
        gate_status, gate_reason = technical_gate(answers, top)
        if not answers:
            st.info("Candidates, priority scores and evidence gates will appear as the caller responds.")
        else:
            priority_key = detected_priority(answers.get("priority", ""))
            st.markdown(f'<div class="card good"><div class="label">Detected customer priority</div><div class="value">{PRIORITY_LABELS[priority_key]}</div></div>', unsafe_allow_html=True)
            if top:
                recommendation_label = "Demo recommendation" if recommendation_allowed(top) else "Closest match — recommendation withheld"
                st.markdown(f'<div class="card"><div class="label">{recommendation_label}</div><div class="value">{top["manufacturer"]} · {top["name"]}</div><div class="note">{top["primary_function"]}<br>{confidence_label(top["confidence"])} · Family level only; no SKU or grade selected.</div></div>', unsafe_allow_html=True)
            gate_class = "blocked" if gate_status == "BLOCKED" else "gate"
            st.markdown(f'<div class="card {gate_class}"><div class="label">Technical approval gate</div><div class="value">{gate_status}</div><div class="note">{gate_reason}</div></div>', unsafe_allow_html=True)
            st.markdown("#### Candidate comparison")
            for index, candidate in enumerate(ranked[:3], start=1):
                with st.expander(f"{index}. {candidate['manufacturer']} · {candidate['name']} · {confidence_label(candidate['confidence'])}", expanded=index == 1):
                    st.write(candidate["score_notes"])
                    st.caption("Matched enquiry language: " + (", ".join(candidate["matched"][:5]) or "priority fit only—more application detail needed"))
                    st.dataframe(score_frame([candidate]), width="stretch")
                    st.markdown("**Next questions**")
                    for question in candidate["questions"]: st.markdown(f"- {question}")
                    st.markdown("**Human gates**")
                    for gate in candidate["human_gates"]: st.markdown(f"- {gate}")
                    st.caption(f"Knowledge: knowledge/{candidate['manufacturer'].casefold()}/{candidate['knowledge_file']}")
            with st.expander("Captured enquiry brief", expanded=st.session_state.demo_complete):
                for key, label in QUESTIONS: st.markdown(f"**{label.split('?')[0]}:** {answers.get(key, 'Not captured')}")
        st.markdown("### Quote/order workflow")
        if not st.session_state.demo_complete: st.caption("Complete the enquiry before preparing a quote handoff.")
        elif not st.session_state.human_approved:
            st.warning("MYOB action locked: technical approval is pending.")
            if st.button("Simulate technical approval", type="primary", width="stretch"): st.session_state.human_approved = True; st.rerun()
        elif st.session_state.myob_quote is None:
            st.success("Technical approval simulated for this demonstration.")
            if st.button("Create mock MYOB draft quote", type="primary", width="stretch"):
                st.session_state.myob_quote = {"reference": "DEMO-Q-0001", "status": "DRAFT — NOT SENT", "product": top["name"] if top else "Awaiting selection"}; st.rerun()
        else:
            quote = st.session_state.myob_quote
            st.markdown(f'<div class="card good"><div class="label">Mock MYOB quote</div><div class="value">{quote["reference"]}</div><div class="note">{quote["status"]}<br>{quote["product"]}<br>SKU and live price would come from approved MYOB integration.</div></div>', unsafe_allow_html=True)
        if answers: st.download_button("Download callback brief", json.dumps(callback_payload(), indent=2, ensure_ascii=False), "demo_callback_brief.json", "application/json", width="stretch")

with explorer_tab:
    st.subheader("Fletcher and Thermotec family catalogue")
    st.caption(CATALOGUE["rating_scale"] + ". Zero means not scored because evidence is unverified.")
    c0, c1, c2 = st.columns(3)
    with c0: selected_manufacturers = st.multiselect("Filter manufacturer", ["Thermotec", "Fletcher"])
    categories = sorted({item["category"] for item in FAMILIES})
    with c1: selected_categories = st.multiselect("Filter category", categories)
    with c2: query = st.text_input("Search application or problem", placeholder="e.g. solar pipe, footsteps, metal roof")
    shown = [item for item in FAMILIES if (not selected_manufacturers or item["manufacturer"] in selected_manufacturers) and (not selected_categories or item["category"] in selected_categories)]
    if query:
        words = query.casefold().split()
        shown = [item for item in shown if all(word in " ".join([item["name"], item["primary_function"], *item["applications"], *item["keywords"]]).casefold() for word in words)]
    st.dataframe(pd.DataFrame([{"Manufacturer": x["manufacturer"], "Family": x["name"], "Category": x["category"], "Evidence": confidence_label(x["confidence"]), "Acoustic": x["scores"]["acoustic_comfort"], "Energy": x["scores"]["energy_efficiency"], "Sustainability": x["scores"]["sustainability"], "Install": x["scores"]["installation_practicality"], "Evidence readiness": x["scores"]["compliance_readiness"]} for x in shown]), hide_index=True, width="stretch")
    selected_name = st.selectbox("Open family record", [x["name"] for x in shown] if shown else ["No matching family"])
    selected = next((x for x in shown if x["name"] == selected_name), None)
    if selected:
        st.markdown(f"### {selected['manufacturer']} · {selected['name']}"); st.write(selected["primary_function"])
        left, right = st.columns(2)
        with left:
            st.markdown("**Typical applications**"); st.write(", ".join(selected["applications"]))
            st.markdown("**Priority interpretation**"); st.write(selected["score_notes"])
        with right:
            st.markdown("**Evidence status**"); st.write(confidence_label(selected["confidence"]))
            st.markdown("**Knowledge file**"); st.code(f"knowledge/{selected['manufacturer'].casefold()}/{selected['knowledge_file']}")
        st.markdown("**Questions before selection**")
        for question in selected["questions"]: st.markdown(f"- {question}")
        if selected["source_url"]: st.link_button("Open supporting source", selected["source_url"])

with architecture_tab:
    st.subheader("One language across customer, AI and human workflows")
    st.markdown("**Google Sheet SKU rows** → family ID → **versioned Markdown + structured catalogue** → Streamlit/Aircall retrieval → human approval → **MYOB draft quote**")
    st.info("The structured catalogue controls matching and ratings; Markdown holds the fuller explanation, limits and source context. Both use the same family ID.")
    st.markdown("#### Current controls")
    st.markdown("- Demo mode may recommend a manufacturer-supported product family.\n- It does not select a SKU, grade, thickness, quantity or promise an installed outcome.\n- Secondary-source and identity-unverified families are not recommended.\n- Fire, NCC, BAL, acoustic targets and exact selection remain human gates.\n- MYOB is mocked and cannot create or send a real quote.")

st.markdown('<p class="small-note">Demonstration only. No live Aircall, Google Drive, MYOB, pricing, stock, customer-record or ordering connection is used.</p>', unsafe_allow_html=True)
