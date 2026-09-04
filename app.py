from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from audit_store import create_review, decide_review, get_review
from bot_engine import (
    PRIORITY_LABELS,
    detected_priority,
    rank_families as rank_catalogue,
    recommendation_allowed,
    technical_gate,
)

APP_TITLE = "Insulation Sales Engineer"
REPO_ROOT = Path(__file__).resolve().parent
CATALOGUE_FILES = [
    REPO_ROOT / "knowledge" / "thermotec" / "families.json",
    REPO_ROOT / "knowledge" / "fletcher" / "families.json",
]
PERFORMANCE_FILE = REPO_ROOT / "knowledge" / "performance_evidence.json"

QUESTIONS = [
    ("challenge", "What would you like to improve—noise, heat, condensation or general comfort?"),
    ("application", "Where is the problem—wall, floor, roof, pipe or somewhere else?"),
    ("priority", "What matters most: comfort, energy savings, sustainability, easy installation, budget or compliance?"),
    ("conditions", "Any practical constraints, such as limited space, weather exposure, temperature or floor finish?"),
    ("project", "Is this residential, commercial or industrial? Is it new work or a retrofit?"),
    ("locality", "What suburb and postcode is the project in? I’ll use it for the NCC climate-zone check."),
    ("requirements", "Do you have a target rating, NCC, fire, BAL or consultant requirement? It’s okay if you’re unsure."),
    ("contact", "Would you prefer to call us, receive a callback or have the brief emailed to the team?"),
]

NCC_ZONE_GUIDE = [
    {"Zone": 1, "Climate": "High-humidity summer, warm winter", "Wall wrap / external wall layer": "No zone-specific minimum in 10.8.1(2); membrane must still meet 10.8.1(1)", "Roof-space note": "General condensation design applies"},
    {"Zone": 2, "Climate": "Warm-humid summer, mild winter", "Wall wrap / external wall layer": "No zone-specific minimum in 10.8.1(2); membrane must still meet 10.8.1(1)", "Roof-space note": "General condensation design applies"},
    {"Zone": 3, "Climate": "Hot-dry summer, warm winter", "Wall wrap / external wall layer": "No zone-specific minimum in 10.8.1(2); membrane must still meet 10.8.1(1)", "Roof-space note": "General condensation design applies"},
    {"Zone": 4, "Climate": "Hot-dry summer, cool winter", "Wall wrap / external wall layer": "≥ 0.143 µg/N·s; Class 3 or 4 meets the explanatory threshold", "Roof-space note": "General condensation design applies"},
    {"Zone": 5, "Climate": "Warm temperate", "Wall wrap / external wall layer": "≥ 0.143 µg/N·s; Class 3 or 4 meets the explanatory threshold", "Roof-space note": "General condensation design applies"},
    {"Zone": 6, "Climate": "Mild temperate", "Wall wrap / external wall layer": "≥ 1.14 µg/N·s; Class 4", "Roof-space note": "10.8.3 roof-space/ventilation provisions apply, subject to details and exceptions"},
    {"Zone": 7, "Climate": "Cool temperate", "Wall wrap / external wall layer": "≥ 1.14 µg/N·s; Class 4", "Roof-space note": "10.8.3 roof-space/ventilation provisions apply, subject to details and exceptions"},
    {"Zone": 8, "Climate": "Alpine", "Wall wrap / external wall layer": "≥ 1.14 µg/N·s; Class 4", "Roof-space note": "10.8.3 plus alpine provisions; specialist review"},
]

LOCALITY_ZONE_HINTS = {
    "darwin": 1, "cairns": 1,
    "brisbane": 2, "gold coast": 2,
    "alice springs": 3,
    "perth": 5, "adelaide": 5, "sydney": 5, "newcastle": 5, "wollongong": 5,
    "melbourne": 6,
    "canberra": 7, "hobart": 7,
    "thredbo": 8,
}
EXAMPLES = {
    "Thermal wall comfort": [
        "The rooms are cold in winter and hot in summer.", "External timber-framed walls.",
        "Energy efficiency and thermal comfort.", "The wall cavities are accessible during renovation.",
        "Residential renovation.", "Parramatta, Sydney NSW 2150.", "No special fire or BAL requirement is known.", "Please arrange a callback.",
    ],
    "Roof at ceiling level": [
        "We need to improve the thermal insulation in the roof.", "The insulation will sit at ceiling level below the roof space.",
        "Energy efficiency and year-round comfort.", "It is a tiled roof with good access above the ceiling.",
        "Residential retrofit.", "Sydney NSW 2000.", "No special fire or BAL requirement is known.", "Please arrange a callback.",
    ],
    "Thermal subfloor": [
        "The timber floor is cold in winter.", "Insulation will sit underneath the suspended ground floor.",
        "Energy efficiency and thermal comfort.", "There is crawl-space access and some wind exposure.",
        "Residential retrofit.", "Hobart TAS 7000.", "No target rating is available yet.", "Please arrange a callback.",
    ],
    "Between-floor noise": [
        "We hear voices between the ground and first floor.", "The insulation will sit inside the cavity between storeys.",
        "Acoustic comfort.", "The ceiling will be opened during renovation.",
        "Residential renovation.", "Melbourne VIC 3000.", "No acoustic target is known.", "Email the brief to the team.",
    ],
    "Airborne wall noise": [
        "We hear conversations and television through the wall.", "An existing internal stud wall between a bedroom and living room.",
        "Acoustic comfort first, with minimal added thickness.", "The wall cavity is accessible during renovation.",
        "Residential renovation.", "Melbourne VIC 3000.", "No target is known and I am not sure about fire requirements.", "Please arrange an afternoon callback.",
    ],
    "Noisy waste pipe": [
        "Water movement in a waste pipe is loud in the bedroom.", "A 100 mm PVC waste pipe in a boxed service riser.",
        "Acoustic comfort and practical installation in tight access.", "Indoor service, limited access, temperature is not high.",
        "Apartment renovation.", "Brisbane QLD 4000.", "The consultant detail is available but I do not know the clause.", "Email the enquiry for review.",
    ],
    "Outdoor solar pipe": [
        "We need to reduce heat loss from solar hot-water pipes.", "Copper pipe running outside on the roof.",
        "Energy efficiency and weather durability.", "High temperature with continuous sun and UV exposure; pipe size is 22 mm.",
        "Residential retrofit.", "Brisbane QLD 4000.", "The plumber needs an NCC-suitable system but no clause was supplied.", "Please arrange a callback.",
    ],
    "Hot metal shed": [
        "The metal shed becomes extremely hot in summer.", "Under a new metal roof and in the walls.",
        "Energy efficiency and summer comfort.", "The roof has a ventilated air space; condensation design is not complete.",
        "Commercial shed refurbishment.", "Perth WA 6000.", "The certifier will review NCC and condensation requirements.", "Email the project brief.",
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
PERFORMANCE = {
    record["family_id"]: record
    for record in json.loads(PERFORMANCE_FILE.read_text(encoding="utf-8"))["families"]
}


def initialise_state() -> None:
    defaults = {
        "messages": [{"role": "assistant", "content": "Hi—" + QUESTIONS[0][1]}],
        "answers": {}, "step": 0, "demo_complete": False, "human_approved": False, "myob_quote": None, "review_id": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_demo() -> None:
    for key in ["messages", "answers", "step", "demo_complete", "human_approved", "myob_quote", "review_id"]:
        st.session_state.pop(key, None)
    initialise_state()


def enquiry_text(answers: dict[str, str]) -> str:
    return " ".join(answers.values()).casefold()


def has_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def detected_element(answers: dict[str, str]) -> str | None:
    text = enquiry_text(answers)
    element_terms = {
        "roof": ["roof", "ceiling", "rafter", "truss"],
        "floor": ["floor", "subfloor", "underfloor", "storey", "storeys"],
        "wall": ["wall", "partition"],
        "pipe": ["pipe", "plumbing", "waste", "solar hot water"],
        "duct": ["duct", "hvac"],
    }
    return next((element for element, terms in element_terms.items() if has_any(text, terms)), None)


def question_for_step(step: int, answers: dict[str, str]) -> str:
    if step == 1:
        text = enquiry_text(answers)
        element = detected_element(answers)
        if element == "roof":
            if has_any(text, ["ceiling level", "ceiling space", "roofline", "rafter", "truss"]):
                return "What type of roof is it—metal, tile or something else?"
            return "Should the insulation sit at ceiling level or up near the roofline, rafters or trusses?"
        if element == "floor":
            if has_any(text, ["subfloor", "underfloor", "suspended floor", "between floors", "between storeys", "floor finish", "underlay"]):
                return "What is the floor construction—timber, concrete or something else?"
            return "Is it under a suspended ground floor, inside the cavity between storeys, or directly beneath the floor finish?"
        if element == "wall":
            return "Is it an internal or external wall, and what is the frame made from?"
        if element in {"pipe", "duct"}:
            return "What service is it, and is it indoors or exposed to weather?"
    if step == 3:
        text = enquiry_text(answers)
        element = detected_element(answers)
        if element == "roof":
            if has_any(text, ["metal roof", "tiled roof", "tile roof"]):
                return "How much space is available, and are condensation or rain noise concerns?"
            return "What type of roof is it, and are condensation or rain noise concerns?"
        if element == "floor":
            return "What access, cavity depth, moisture or floor-finish constraints should we allow for?"
    return QUESTIONS[step][1]


def supplied_locality(answers: dict[str, str]) -> str | None:
    return next((value for value in answers.values() if re.search(r"\b\d{4}\b", value)), None)


def ncc_zone_hint(locality: str) -> dict | None:
    folded = locality.casefold()
    zone = next((zone for place, zone in LOCALITY_ZONE_HINTS.items() if place in folded), None)
    return next((row for row in NCC_ZONE_GUIDE if row["Zone"] == zone), None)


def wall_wrap_zone_summary(zone: int) -> str:
    if zone <= 3:
        return "No zone-specific minimum permeance in 10.8.1(2); the membrane and installation requirements still apply."
    if zone <= 5:
        return "Minimum 0.143 µg/N·s where 10.8.1(2) applies; Class 3 or 4 meets the explanatory threshold."
    return "Minimum 1.14 µg/N·s where 10.8.1(2) applies; Class 4."


def rank_families(answers: dict[str, str], manufacturer_scope: str | None = None) -> list[dict]:
    return rank_catalogue(FAMILIES, answers, manufacturer_scope)


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
    if st.session_state.step < len(QUESTIONS) and QUESTIONS[st.session_state.step][0] == "locality":
        locality = supplied_locality(st.session_state.answers)
        if locality:
            st.session_state.answers["locality"] = locality
            st.session_state.step += 1
    if st.session_state.step < len(QUESTIONS):
        st.session_state.messages.append({"role": "assistant", "content": question_for_step(st.session_state.step, st.session_state.answers)})
    else:
        st.session_state.demo_complete = True
        top = rank_families(st.session_state.answers, st.session_state.get("manufacturer_scope", "Compare both"))[0]
        if not top["reliable_match"]:
            reply = "I don’t have a reliable product match from those details. I’ll send this to the team for review rather than guess."
        elif recommendation_allowed(top):
            application = next(iter(dict.fromkeys(top["matched_applications"])), "")
            priority = PRIORITY_LABELS[top["priority_key"]].lower()
            why = f"It suits {application} applications and your focus on {priority}." if application else f"It lines up with your focus on {priority}."
            reply = f"**{top['name']}** looks like the best fit. {why} We’ll confirm the exact product and compliance details before quoting."
        else:
            reply = f"**{top['name']}** is the closest match, but its product evidence still needs checking. I’ll flag it for the team before anything is selected or quoted."
        st.session_state.messages.append({"role": "assistant", "content": reply})
        if st.session_state.review_id is None:
            st.session_state.review_id = create_review(
                callback_payload(),
                retention_days=int(os.getenv("AUDIT_RETENTION_DAYS", "30")),
                require_encryption=os.getenv("AUDIT_REQUIRE_ENCRYPTION", "false").casefold() == "true",
            )


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
    locality = st.session_state.answers.get("locality", "")
    zone = ncc_zone_hint(locality) if locality else None
    return {
        "created_at": datetime.now().isoformat(timespec="seconds"), "demo_only": True,
        "review_id": st.session_state.get("review_id"),
        "customer_answers": st.session_state.answers,
        "demo_recommendation": ({"family_id": top["family_id"], "name": top["name"], "scope": "product_family_only"} if recommendation_allowed(top) and top.get("reliable_match", False) else None),
        "candidate_families": [{"family_id": x["family_id"], "name": x["name"], "confidence": x["confidence"]} for x in ranked[:3]],
        "technical_review": {"status": gate, "reason": reason},
        "ncc_climate_zone_screen": {
            "locality": locality,
            "indicative_zone": zone["Zone"] if zone else None,
            "status": "indicative_only_confirm_with_abcb_map" if zone else "exact_zone_lookup_required",
        },
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
            priority_context = " ".join(value for key, value in answers.items() if key != "priority")
            priority_key = detected_priority(answers.get("priority", ""), priority_context)
            st.markdown(f'<div class="card good"><div class="label">Detected customer priority</div><div class="value">{PRIORITY_LABELS[priority_key]}</div></div>', unsafe_allow_html=True)
            locality = answers.get("locality", "")
            zone = ncc_zone_hint(locality) if locality else None
            if locality and zone:
                zone_note = wall_wrap_zone_summary(zone["Zone"])
                st.markdown(f'<div class="card gate"><div class="label">Indicative NCC climate zone</div><div class="value">Zone {zone["Zone"]} · {zone["Climate"]}</div><div class="note">{locality}<br>Wall wrap: {zone_note}<br>Confirm the exact address, applicable NCC edition and jurisdictional variations.</div></div>', unsafe_allow_html=True)
            elif locality:
                st.markdown(f'<div class="card gate"><div class="label">NCC climate zone</div><div class="value">Exact lookup required</div><div class="note">{locality}<br>This locality is not in the demo hint list. Confirm it with the official ABCB Climate Map.</div></div>', unsafe_allow_html=True)
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
            if st.session_state.review_id:
                review = get_review(st.session_state.review_id)
                st.caption(f"Review queue: {st.session_state.review_id} · {review['status'] if review else 'UNKNOWN'}")
            if st.button("Simulate technical approval", type="primary", width="stretch"):
                decide_review(st.session_state.review_id, "APPROVED", os.getenv("AUDIT_REVIEWER", "demo-sales-engineer"), "POC approval")
                st.session_state.human_approved = True
                st.rerun()
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
        performance = PERFORMANCE[selected["family_id"]]
        st.markdown("**Structured performance evidence**")
        st.caption(f"Automation status: {performance['automation_status'].replace('_', ' ')}")
        if performance["evidence_items"]:
            st.dataframe(pd.DataFrame([{
                "Metric": item["metric_type"], "Value": f"{item['value']} {item['unit']}".strip(),
                "Variant": item["variant"], "Scope": item["scope"], "Evidence": item["evidence_status"],
                "Context": item["test_context"],
            } for item in performance["evidence_items"]]), hide_index=True, width="stretch")
        else:
            st.warning("No normalized performance claim has been approved for this family yet.")
        st.markdown("**Questions before selection**")
        for question in selected["questions"]: st.markdown(f"- {question}")
        if selected["source_url"]: st.link_button("Open supporting source", selected["source_url"])

with architecture_tab:
    st.subheader("One language across customer, AI and human workflows")
    st.markdown("**Google Sheet SKU rows** → family ID → **versioned Markdown + structured catalogue** → Streamlit/Aircall retrieval → human approval → **MYOB draft quote**")
    st.info("The structured catalogue controls matching and ratings; Markdown holds the fuller explanation, limits and source context. Both use the same family ID.")
    st.markdown("#### Current controls")
    st.markdown("- Demo mode may recommend a manufacturer-supported product family.\n- It does not select a SKU, grade, thickness, quantity or promise an installed outcome.\n- Secondary-source, identity-unverified and identity-review families are not recommended.\n- Normalized performance claims retain their variant, scope, test context and source.\n- Fire, NCC, BAL, acoustic targets and exact selection remain human gates.\n- Every completed enquiry receives a local review ID; MYOB is mocked and cannot create or send a real quote.")
    st.markdown("#### NCC climate-zone screening")
    st.dataframe(pd.DataFrame(NCC_ZONE_GUIDE), hide_index=True, width="stretch")
    st.caption("NCC 2022 Housing Provisions 10.8 screening aid only. Required roof, wall and floor Total R-values are project-specific; confirm the exact address, building class, compliance pathway, applicable NCC edition and state or territory variations.")
    st.link_button("Open the official ABCB Climate Map", "https://ncc.abcb.gov.au/abcb-climate-map")

st.markdown('<p class="small-note">Demonstration only. No live Aircall, Google Drive, MYOB, pricing, stock, customer-record or ordering connection is used.</p>', unsafe_allow_html=True)
