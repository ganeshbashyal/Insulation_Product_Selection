"""Classification-aware priority scoring for product families.

The original generators scored families by physical form alone (every "batt"
got energy_efficiency 5), which made manufacturer-classified acoustic products
(e.g. Bradford Soundscreen, Autex desk dividers) outrank real thermal products
on thermal enquiries. Scores here are driven by what the manufacturer says the
product is for (name, applications, keywords), with the physical-form category
only providing the baseline for the non-thermal/acoustic dimensions.
"""
from __future__ import annotations

CATEGORY_SCORES = {
    "batt": {"acoustic_comfort": 3, "energy_efficiency": 5, "sustainability": 4, "installation_practicality": 4, "compliance_readiness": 4},
    "blanket": {"acoustic_comfort": 3, "energy_efficiency": 5, "sustainability": 4, "installation_practicality": 3, "compliance_readiness": 4},
    "board": {"acoustic_comfort": 2, "energy_efficiency": 4, "sustainability": 3, "installation_practicality": 3, "compliance_readiness": 4},
    "reflective": {"acoustic_comfort": 2, "energy_efficiency": 4, "sustainability": 2, "installation_practicality": 4, "compliance_readiness": 3},
    "foil": {"acoustic_comfort": 2, "energy_efficiency": 4, "sustainability": 2, "installation_practicality": 4, "compliance_readiness": 3},
    "pipe": {"acoustic_comfort": 2, "energy_efficiency": 4, "sustainability": 2, "installation_practicality": 4, "compliance_readiness": 3},
    "wrap": {"acoustic_comfort": 2, "energy_efficiency": 3, "sustainability": 2, "installation_practicality": 4, "compliance_readiness": 3},
    "panel": {"acoustic_comfort": 4, "energy_efficiency": 3, "sustainability": 3, "installation_practicality": 3, "compliance_readiness": 3},
    "accessory": {"acoustic_comfort": 1, "energy_efficiency": 1, "sustainability": 2, "installation_practicality": 5, "compliance_readiness": 2},
}
DEFAULT_SCORES = {"acoustic_comfort": 3, "energy_efficiency": 3, "sustainability": 3, "installation_practicality": 3, "compliance_readiness": 3}

# "ceiling", "wall" and "floor" are deliberately absent: internal-wall/ceiling
# products are as often acoustic as thermal, so only unambiguous phrases count.
ACOUSTIC_SIGNALS = (
    "acoustic", "sound", "quiet", "noise", "noisy", "echo", "reverb",
    "baffle", "raft", "nrc", "absorber", "silencer", "desk divider",
    "desk screen", "hanging screen", "screen", "pinboard", "cubicle",
    "composition", "vicinity", "frontier", "lanes", "cube", "quietspace",
)
THERMAL_SIGNALS = (
    "thermal", "roof", "sarking", "wall wrap", "reflective", "foil",
    "underfloor", "condensation", "thermal break", "pipe", "duct",
    "shed", "external wall", "r value", "r-value", "blanket",
    "ceiling insulation", "roof insulation", "wall insulation", "soffit",
    "slab liner", "glareshield", "insulbreak", "insulshed", "insuliner",
)
FIRE_SIGNALS = ("fire", "party wall fire", "flame", "bal ", "bushfire")


def _hits(signals: tuple[str, ...], text: str) -> bool:
    return any(signal in text for signal in signals)


def classify_scores(category: str, name: str = "", applications=(), keywords=()) -> dict:
    """Return priority scores for a family.

    Baseline comes from the physical-form category, then acoustic/thermal/fire
    signals in the manufacturer-supplied name, applications and keywords
    override the acoustic_comfort / energy_efficiency / compliance dimensions.
    """
    base = dict(CATEGORY_SCORES.get((category or "").lower(), DEFAULT_SCORES))
    if (category or "").lower() == "accessory":
        # Tapes, adhesives and fixings are not acoustic or thermal products no
        # matter which family they are sold alongside.
        return base
    text = " ".join([name or "", *(applications or ()), *(keywords or ())]).casefold()

    acoustic = _hits(ACOUSTIC_SIGNALS, text)
    thermal = _hits(THERMAL_SIGNALS, text)
    fire = _hits(FIRE_SIGNALS, text)

    if fire:
        base["compliance_readiness"] = 5
        base["acoustic_comfort"] = min(base["acoustic_comfort"], 2)
        base["energy_efficiency"] = min(base["energy_efficiency"], 2)
    elif acoustic and not thermal:
        base["acoustic_comfort"] = 5
        base["energy_efficiency"] = min(base["energy_efficiency"], 2)
    elif thermal and not acoustic:
        base["energy_efficiency"] = 5
        base["acoustic_comfort"] = min(base["acoustic_comfort"], 2)
    elif acoustic and thermal:
        base["acoustic_comfort"] = 4
        base["energy_efficiency"] = 4
    return base
