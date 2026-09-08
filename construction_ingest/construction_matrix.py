"""Construction phase x framing type x climate zone rules matrix (NCC 2022).

Encodes standard Australian residential build sequence and the material
consequences of timber vs cold-formed steel framing:

    Slab/subfloor -> Framing -> Wrapping/sarking -> Insulation -> Lining

Scope and limitation
--------------------
This is a screening and conversation aid built from NCC 2022 Volume Two / ABCB
Housing Provisions and AS/NZS 4200.1-2, not a compliance certificate. Required
Total R-values are project-specific (building class, construction, compliance
pathway, glazing and services trade-offs, state variations) and are deliberately
NOT tabulated here. Every rule carries its ``provision`` so an assessor can
check the source clause.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum


class FramingType(str, Enum):
    TIMBER = "Timber"
    STEEL = "Steel"


class Phase(str, Enum):
    SLAB = "1. Subfloor & Slab"
    FRAMING = "2. Framing"
    WRAPPING = "3. Wrapping / Sarking"
    INSULATION = "4. Wall & Ceiling Cavity Insulation"
    LINING = "5. Internal Lining"


PHASE_ORDER: tuple[Phase, ...] = (
    Phase.SLAB,
    Phase.FRAMING,
    Phase.WRAPPING,
    Phase.INSULATION,
    Phase.LINING,
)

#: Zones grouped by the condensation-management treatment in Housing
#: Provisions 10.8.1. Zones 1-3 have no zone-specific minimum permeance;
#: zones 4-5 and 6-8 do.
WARM_ZONES: frozenset[int] = frozenset({1, 2, 3})
TEMPERATE_ZONES: frozenset[int] = frozenset({4, 5})
COOL_ZONES: frozenset[int] = frozenset({6, 7, 8})
ALL_ZONES: frozenset[int] = frozenset(range(1, 9))


# ---------------------------------------------------------------------------
# Framing physics
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FramingProfile:
    """Physical and thermal characteristics of a framing system."""

    framing_type: FramingType
    typical_stud_sizes_mm: tuple[str, ...]
    typical_stud_centres_mm: tuple[int, ...]
    thermal_conductivity_w_mk: float
    thermal_bridging_severity: str
    thermal_break_required: bool
    thermal_break_provision: str
    notes: str

    def as_dict(self) -> dict:
        data = asdict(self)
        data["framing_type"] = self.framing_type.value
        return data


FRAMING_PROFILES: dict[FramingType, FramingProfile] = {
    FramingType.TIMBER: FramingProfile(
        framing_type=FramingType.TIMBER,
        typical_stud_sizes_mm=("45 x 70", "45 x 90", "45 x 140", "35 x 90"),
        typical_stud_centres_mm=(450, 600),
        # Softwood across the grain; AS/NZS 4859.1 default order of magnitude.
        thermal_conductivity_w_mk=0.12,
        thermal_bridging_severity="Low - timber is a comparatively poor conductor, "
        "but studs, noggings, plates and lintels still reduce whole-wall Total R "
        "below the nominal batt R-value (framing fraction typically 10-20%).",
        thermal_break_required=False,
        thermal_break_provision="No NCC-mandated continuous thermal break for timber "
        "framing. Framing losses are handled through the Total R-value calculation "
        "in the project energy assessment.",
        notes="Cavity batts friction-fit between studs. Timber tolerates fixings and "
        "trims easily, and is dimensionally sensitive to moisture, so wet-trades "
        "sequencing and cavity drying matter.",
    ),
    FramingType.STEEL: FramingProfile(
        framing_type=FramingType.STEEL,
        typical_stud_sizes_mm=("64 x 35 BMT 0.75", "76 x 35", "90 x 35", "150 x 40"),
        typical_stud_centres_mm=(450, 600),
        # Cold-formed steel; the ~400x conductivity gap vs timber is the whole
        # reason NCC 2022 requires a continuous thermal break.
        thermal_conductivity_w_mk=50.0,
        thermal_bridging_severity="Severe - roughly 400x the conductivity of timber. "
        "Each stud is a continuous metal path from lining to cladding, and can strip "
        "a large share of the nominal cavity R-value from the whole-wall Total R.",
        thermal_break_required=True,
        thermal_break_provision="NCC 2022 Volume Two / ABCB Housing Provisions Part 13.2 "
        "(and Volume One Section J equivalent): a metal-framed external wall requires a "
        "thermal break of minimum R0.2 installed between the external cladding and the "
        "metal frame where the cladding is fixed directly to the frame.",
        notes="Steel studs are rolled to fixed section sizes; batts must be ordered to "
        "the steel stud module rather than trimmed on site. Dissimilar-metal contact, "
        "fixing type and condensation on the cold steel face all need checking.",
    ),
}


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConstructionRule:
    """One requirement for a phase, framing type and set of climate zones."""

    phase: Phase
    framing_type: FramingType | None
    climate_zones: frozenset[int]
    requirement: str
    material: str
    provision: str
    verification: str = ""
    severity: str = "required"  # required | recommended | informational
    tags: tuple[str, ...] = field(default_factory=tuple)

    def applies_to(self, framing_type: FramingType | None, climate_zone: int | None) -> bool:
        if self.framing_type is not None and framing_type is not None and self.framing_type != framing_type:
            return False
        if climate_zone is not None and climate_zone not in self.climate_zones:
            return False
        return True

    def as_dict(self) -> dict:
        return {
            "phase": self.phase.value,
            "framing_type": self.framing_type.value if self.framing_type else "Any",
            "climate_zones": sorted(self.climate_zones),
            "requirement": self.requirement,
            "material": self.material,
            "provision": self.provision,
            "verification": self.verification,
            "severity": self.severity,
            "tags": list(self.tags),
        }


CONSTRUCTION_RULES: tuple[ConstructionRule, ...] = (
    # -- Phase 1: Subfloor & Slab -------------------------------------------
    ConstructionRule(
        phase=Phase.SLAB,
        framing_type=None,
        climate_zones=ALL_ZONES,
        requirement="Install a vapour barrier / damp-proof membrane under the slab, "
        "lapped and taped at joints and turned up at edges before the pour.",
        material="Polyethylene underslab membrane to AS 2870 (typically 0.2 mm, "
        "high-impact grade where required by the site classification)",
        provision="AS 2870 Residential slabs and footings; NCC 2022 Housing Provisions "
        "Part 4.4 (damp and weatherproofing of the slab)",
        verification="Confirm membrane grade against the site classification and the "
        "engineer's slab detail.",
        tags=("dpm", "vapour barrier", "slab"),
    ),
    ConstructionRule(
        phase=Phase.SLAB,
        framing_type=None,
        climate_zones=frozenset({5, 6, 7, 8}),
        requirement="Slab-edge insulation is commonly required in cooler zones where "
        "the energy assessment relies on it, and is mandatory for a heated slab.",
        material="Extruded polystyrene (XPS) or expanded polystyrene (EPS) slab-edge "
        "board, termite-managed and UV-protected where exposed",
        provision="NCC 2022 Housing Provisions Part 13.2 (floors) - a heated slab "
        "requires edge and underslab insulation; unheated slab-edge insulation is "
        "driven by the project energy assessment",
        verification="Take the required edge R-value and depth from the NatHERS or "
        "elemental-provisions assessment, not from a generic zone table.",
        severity="recommended",
        tags=("slab edge", "xps", "eps"),
    ),
    ConstructionRule(
        phase=Phase.SLAB,
        framing_type=FramingType.STEEL,
        climate_zones=ALL_ZONES,
        requirement="Isolate the bottom track from the slab: check the damp-proof "
        "course, corrosion protection and any dissimilar-metal contact at the base "
        "of steel wall frames.",
        material="DPC strip / bottom-plate isolation membrane",
        provision="NASH Standard - Residential and Low-rise Steel Framing; NCC 2022 "
        "Housing Provisions Part 4.4 (damp-proofing)",
        verification="Confirm the frame manufacturer's base-fixing and corrosion detail.",
        tags=("steel base", "dpc", "corrosion"),
    ),
    ConstructionRule(
        phase=Phase.SLAB,
        framing_type=None,
        climate_zones=ALL_ZONES,
        requirement="For a suspended floor, plan the subfloor insulation and its "
        "support system before the floor is closed in - retrofitting is far dearer.",
        material="Underfloor batts/boards with permanent mechanical support, or a "
        "reflective/foil subfloor system with the required airspace",
        provision="NCC 2022 Housing Provisions Part 13.2 (floors); AS 3999 for "
        "bulk insulation installation",
        verification="Confirm a reflective system's airspace and emittance are as tested; "
        "a dusty or blocked airspace does not deliver the rated R-value.",
        severity="recommended",
        tags=("subfloor", "suspended floor"),
    ),
    # -- Phase 2: Framing ----------------------------------------------------
    ConstructionRule(
        phase=Phase.FRAMING,
        framing_type=FramingType.TIMBER,
        climate_zones=ALL_ZONES,
        requirement="Frame to AS 1684 with standard 45 mm x 90 mm (or 70/140 mm) "
        "studs at 450 mm or 600 mm centres, and record the actual centres - they set "
        "the batt width ordered in Phase 4.",
        material="Seasoned softwood/hardwood framing to AS 1684, treated to the "
        "required hazard class",
        provision="AS 1684 Residential timber-framed construction; NCC 2022 Housing "
        "Provisions Part 6",
        verification="Timber conductivity is around 0.12 W/mK, so framing still cuts "
        "whole-wall Total R below the nominal batt value - use the Total R-value from "
        "the energy assessment.",
        tags=("timber", "as1684", "stud centres"),
    ),
    ConstructionRule(
        phase=Phase.FRAMING,
        framing_type=FramingType.STEEL,
        climate_zones=ALL_ZONES,
        requirement="Frame cold-formed steel to the NASH Standard, then treat thermal "
        "bridging as a separate design item - steel conducts roughly 400x more heat "
        "than timber and short-circuits cavity insulation.",
        material="Cold-formed galvanised steel studs and tracks (typically 0.55-1.15 mm BMT)",
        provision="NASH Standard - Residential and Low-rise Steel Framing; NCC 2022 "
        "Housing Provisions Part 6 and Part 13.2",
        verification="Steel conductivity is around 50 W/mK. Whole-wall Total R must be "
        "calculated with the steel framing correction, never taken as the batt R-value.",
        tags=("steel", "nash", "thermal bridging"),
    ),
    ConstructionRule(
        phase=Phase.FRAMING,
        framing_type=FramingType.STEEL,
        climate_zones=ALL_ZONES,
        requirement="Provide a CONTINUOUS thermal break of at least R0.2 between the "
        "steel frame and directly-fixed external cladding. This is the single most "
        "commonly missed steel-frame requirement.",
        material="Thermal break strip/tape to the stud face, or continuous rigid "
        "insulation board over the frame, with a declared R-value of R0.2 or greater",
        provision="NCC 2022 Housing Provisions Part 13.2 (Volume One Section J "
        "equivalent) - minimum R0.2 thermal break for metal-framed external walls "
        "with directly-fixed cladding",
        verification="Check the declared R-value of the strip itself, that it runs "
        "continuously over every stud, plate and lintel, and that fixings do not "
        "compress it into an ineffective layer.",
        tags=("thermal break", "r0.2", "steel", "cladding"),
    ),
    ConstructionRule(
        phase=Phase.FRAMING,
        framing_type=None,
        climate_zones=ALL_ZONES,
        requirement="Complete the frame inspection and set out services before "
        "wrapping. Penetrations cut after wrapping are the usual source of membrane "
        "and air-barrier defects.",
        material="Frame inspection record; service penetration set-out",
        provision="NCC 2022 Housing Provisions Part 6; state building-surveyor "
        "mandatory inspection stages",
        severity="recommended",
        tags=("sequencing", "inspection"),
    ),
    # -- Phase 3: Wrapping / Sarking ----------------------------------------
    ConstructionRule(
        phase=Phase.WRAPPING,
        framing_type=None,
        climate_zones=ALL_ZONES,
        requirement="Any pliable building membrane must comply with AS/NZS 4200.1 and "
        "be installed to AS/NZS 4200.2, positioned on the OUTSIDE of the primary "
        "insulation layer.",
        material="Pliable building membrane classified to AS/NZS 4200.1 (vapour "
        "control Class 1-4, plus water-barrier and duty classification)",
        provision="NCC 2022 Housing Provisions clause 10.8.1(1); AS/NZS 4200.1 and "
        "AS/NZS 4200.2",
        verification="Vapour class is not the same as water-barrier class, duty, fire "
        "performance, UV exposure allowance or BAL suitability - check each separately.",
        tags=("as4200", "membrane", "sarking"),
    ),
    ConstructionRule(
        phase=Phase.WRAPPING,
        framing_type=None,
        climate_zones=WARM_ZONES,
        requirement="Zones 1-3 have no zone-specific minimum vapour permeance in "
        "clause 10.8.1(2). A lower-permeance (Class 1 or 2) vapour barrier is "
        "acceptable, and the design priority is keeping humid outdoor air and "
        "radiant heat out.",
        material="Reflective foil sarking / vapour barrier (Class 1 or 2) with the "
        "reflective face to a compliant airspace, or a breather wrap where the "
        "designer prefers drying capacity",
        provision="NCC 2022 Housing Provisions clause 10.8.1(2) (no zone-specific "
        "minimum permeance for zones 1-3)",
        verification="Air-conditioned buildings in zones 1-2 drive vapour inwards in "
        "summer; a project condensation risk assessment still applies.",
        tags=("vapour barrier", "class 1", "class 2", "reflective foil", "tropical"),
    ),
    ConstructionRule(
        phase=Phase.WRAPPING,
        framing_type=None,
        climate_zones=TEMPERATE_ZONES,
        requirement="Zones 4-5: every pliable membrane outside the primary wall "
        "insulation must have a vapour permeance of at least 0.143 ug/N.s - a "
        "vapour-permeable membrane, not a foil vapour barrier.",
        material="Vapour-permeable wall wrap - the NCC explanatory material identifies "
        "Class 3 or Class 4 as meeting this threshold",
        provision="NCC 2022 Housing Provisions clause 10.8.1(2) - minimum vapour "
        "permeance 0.143 ug/N.s for climate zones 4 and 5",
        verification="Check EVERY layer outside the primary insulation, not just the "
        "branded wrap - a foil-faced board or a taped secondary layer can breach it.",
        tags=("vapour permeable", "class 3", "class 4", "0.143"),
    ),
    ConstructionRule(
        phase=Phase.WRAPPING,
        framing_type=None,
        climate_zones=COOL_ZONES,
        requirement="Zones 6-8: every pliable membrane outside the primary wall "
        "insulation must have a vapour permeance of at least 1.14 ug/N.s. A foil "
        "vapour barrier in this position traps interstitial condensation.",
        material="High-permeance vapour-permeable membrane - the NCC explanatory "
        "material identifies Class 4",
        provision="NCC 2022 Housing Provisions clause 10.8.1(2) - minimum vapour "
        "permeance 1.14 ug/N.s for climate zones 6, 7 and 8",
        verification="Confirm the tested permeance on the TDS in ug/N.s. Class 4 is the "
        "explanatory identification, but the numeric value is what the clause states.",
        tags=("vapour permeable", "class 4", "1.14", "interstitial condensation"),
    ),
    ConstructionRule(
        phase=Phase.WRAPPING,
        framing_type=None,
        climate_zones=COOL_ZONES,
        requirement="Zones 6-8 also trigger the roof-space ventilation provisions - "
        "check roof-space location, the minimum 20 mm space and ventilation openings.",
        material="Roof-space ventilation (eave/ridge) per the applicable construction detail",
        provision="NCC 2022 Housing Provisions clause 10.8.3 - roof space ventilation "
        "for climate zones 6, 7 and 8, subject to its construction details and exceptions",
        verification="Ceiling-level vs roofline insulation changes the roof-space "
        "condition; confirm which one the design uses.",
        tags=("roof space", "ventilation", "10.8.3"),
    ),
    ConstructionRule(
        phase=Phase.WRAPPING,
        framing_type=None,
        climate_zones=ALL_ZONES,
        requirement="Where no pliable membrane is installed, the primary water-control "
        "layer generally has to be separated from water-sensitive materials by a "
        "drained cavity.",
        material="Drained and vented cavity behind the cladding (batten cavity system)",
        provision="NCC 2022 Housing Provisions clause 10.8.1(3), subject to its "
        "single-skin masonry and concrete exclusions",
        tags=("drained cavity", "10.8.1(3)"),
    ),
    ConstructionRule(
        phase=Phase.WRAPPING,
        framing_type=FramingType.STEEL,
        climate_zones=ALL_ZONES,
        requirement="On steel frames the wrap layer is also where the thermal path is "
        "broken: fit thermal break tape or continuous rigid insulation behind the "
        "battens/cladding so the steel is not bridged straight to the outside.",
        material="Thermal break tape over studs, or continuous rigid board (PIR/XPS/EPS) "
        "over the frame, delivering at least R0.2 continuously",
        provision="NCC 2022 Housing Provisions Part 13.2 (R0.2 thermal break) read with "
        "clause 10.8.1 for the membrane's vapour permeance",
        verification="A foil-faced rigid board can satisfy the thermal break and breach "
        "the zone 4-8 permeance requirement at the same time. Both must be checked.",
        tags=("thermal break tape", "rigid board", "steel", "battens"),
    ),
    ConstructionRule(
        phase=Phase.WRAPPING,
        framing_type=FramingType.STEEL,
        climate_zones=COOL_ZONES,
        requirement="Cold steel studs in zones 6-8 reach dew point readily. Keep the "
        "vapour-permeable wrap outboard of the insulation and manage the internal "
        "vapour source separately.",
        material="Class 4 vapour-permeable wrap outboard; internal vapour control "
        "reviewed by the project condensation assessment",
        provision="NCC 2022 Housing Provisions Part 10.8 (condensation management)",
        verification="Request a condensation risk assessment for steel frames in "
        "zones 7-8 rather than relying on a generic wrap selection.",
        severity="recommended",
        tags=("condensation", "steel", "dew point"),
    ),
    # -- Phase 4: Wall & Ceiling Cavity Insulation ---------------------------
    ConstructionRule(
        phase=Phase.INSULATION,
        framing_type=FramingType.TIMBER,
        climate_zones=ALL_ZONES,
        requirement="Friction-fit batts between the timber studs, full width and full "
        "depth, with no gaps, compression or tucking behind services.",
        material="Glasswool, rockwool or polyester batts sized to the timber stud "
        "module (typically 430 mm for 450 mm centres, 580 mm for 600 mm centres)",
        provision="AS 3999 Thermal insulation of buildings - bulk insulation "
        "installation; NCC 2022 Housing Provisions Part 13.2",
        verification="Installation quality dominates outcomes: a 5% gap can cost far "
        "more than the difference between two batt R-values.",
        tags=("batts", "friction fit", "timber", "as3999"),
    ),
    ConstructionRule(
        phase=Phase.INSULATION,
        framing_type=FramingType.STEEL,
        climate_zones=ALL_ZONES,
        requirement="Order batts to the STEEL stud module (450 mm / 600 mm centres) - "
        "steel sections differ from timber, so timber-width batts will not friction-fit "
        "correctly and leave edge gaps at every stud.",
        material="Glasswool or polyester batts in the manufacturer's steel-frame width, "
        "installed to the steel-frame installation instructions",
        provision="AS 3999; NASH Standard installation guidance; NCC 2022 Housing "
        "Provisions Part 13.2",
        verification="Confirm the batt width against the actual steel section, not the "
        "nominal centres.",
        tags=("batts", "steel", "450", "600", "stud centres"),
    ),
    ConstructionRule(
        phase=Phase.INSULATION,
        framing_type=FramingType.STEEL,
        climate_zones=ALL_ZONES,
        requirement="Apply the steel-framing thermal bridging correction when "
        "calculating wall Total R-value. The nominal cavity batt R-value is NOT the "
        "wall's performance.",
        material="Calculated Total R-value including the steel framing correction and "
        "the R0.2+ thermal break",
        provision="NCC 2022 Housing Provisions Part 13.2 (Total R-value determination "
        "for metal-framed construction); AS/NZS 4859.2 for calculating Total R-value",
        verification="Have the Total R-value calculated by the energy assessor using "
        "AS/NZS 4859.2 with the actual stud size, centres, thermal break and cladding.",
        tags=("total r-value", "derating", "4859.2", "steel"),
    ),
    ConstructionRule(
        phase=Phase.INSULATION,
        framing_type=None,
        climate_zones=ALL_ZONES,
        requirement="Maintain the required clearances around downlights, flues, "
        "exhaust fans and other heat-producing fittings, and keep ceiling insulation "
        "continuous over the top plate.",
        material="Insulation with the fitting manufacturer's clearance maintained, or "
        "rated covers where the fitting allows",
        provision="AS/NZS 3000 (electrical clearances); AS 3999; NCC 2022 Housing "
        "Provisions Part 13.2",
        verification="Gaps at the wall/ceiling junction are a very common thermal and "
        "condensation weak point.",
        tags=("clearances", "downlights", "ceiling"),
    ),
    ConstructionRule(
        phase=Phase.INSULATION,
        framing_type=None,
        climate_zones=ALL_ZONES,
        requirement="Do not apply a universal R-value by climate zone. Required Total "
        "R-values depend on building class, construction, compliance pathway, glazing "
        "and services trade-offs and jurisdiction.",
        material="Project-specific R-values from the NatHERS or elemental-provisions "
        "assessment - not a generic per-zone figure",
        provision="NCC 2022 Volume Two Part H6 / Housing Provisions Part 13.2; "
        "state and territory variations",
        severity="informational",
        tags=("r-value", "scope limit"),
    ),
    # -- Phase 5: Internal Lining -------------------------------------------
    ConstructionRule(
        phase=Phase.LINING,
        framing_type=None,
        climate_zones=ALL_ZONES,
        requirement="Inspect and photograph the insulation and membrane before the "
        "plasterboard closes the cavity - this is the last opportunity to fix gaps.",
        material="Pre-lining inspection record",
        provision="Standard practice; supports the energy-assessment assumptions and "
        "any condensation risk assessment",
        severity="recommended",
        tags=("pre-lining inspection", "quality"),
    ),
    ConstructionRule(
        phase=Phase.LINING,
        framing_type=None,
        climate_zones=ALL_ZONES,
        requirement="Line with plasterboard to AS/NZS 2589, using wet-area-grade board "
        "and waterproofing where required.",
        material="Plasterboard to AS/NZS 2589; wet-area board and waterproofing to "
        "AS 3740 in wet areas",
        provision="AS/NZS 2589 Gypsum linings; AS 3740 Waterproofing of domestic wet "
        "areas; NCC 2022 Housing Provisions Part 10.2",
        tags=("plasterboard", "gyprock", "as2589"),
    ),
    ConstructionRule(
        phase=Phase.LINING,
        framing_type=FramingType.STEEL,
        climate_zones=ALL_ZONES,
        requirement="Use screw fixings suited to steel studs and confirm they do not "
        "compress or puncture the thermal break; check for fastener-head condensation "
        "and thermal ghosting risk on the lining.",
        material="Self-drilling drywall screws to the steel-frame specification",
        provision="AS/NZS 2589; NASH Standard; frame manufacturer's fixing schedule",
        severity="recommended",
        tags=("fixings", "steel", "ghosting"),
    ),
    ConstructionRule(
        phase=Phase.LINING,
        framing_type=None,
        climate_zones=COOL_ZONES,
        requirement="Zones 6-8: manage the internal vapour source. Wet areas, kitchens "
        "and laundries need exhaust that discharges outside, not into the roof space.",
        material="Mechanical exhaust ducted to outside air per the condensation provisions",
        provision="NCC 2022 Housing Provisions Part 10.8.2 (exhaust systems) and "
        "Part 10.6 (ventilation)",
        verification="Discharging an exhaust fan into the roof space is a frequent "
        "cause of roof-space condensation in cool zones.",
        tags=("exhaust", "10.8.2", "condensation"),
    ),
)


# ---------------------------------------------------------------------------
# Indexes and query helpers
# ---------------------------------------------------------------------------

#: ``(phase, framing_type, climate_zone) -> [ConstructionRule, ...]``
#:
#: Fully materialised so lookups are a single dict access.
CONSTRUCTION_MATRIX: dict[tuple[Phase, FramingType, int], list[ConstructionRule]] = {
    (phase, framing, zone): [
        rule for rule in CONSTRUCTION_RULES if rule.phase is phase and rule.applies_to(framing, zone)
    ]
    for phase in PHASE_ORDER
    for framing in FramingType
    for zone in sorted(ALL_ZONES)
}


def rules_for(
    phase: Phase | str | None = None,
    framing_type: FramingType | str | None = None,
    climate_zone: int | None = None,
) -> list[ConstructionRule]:
    """Return every rule matching the supplied filters (``None`` = any)."""
    phase_key = Phase(phase) if isinstance(phase, str) else phase
    framing_key = coerce_framing(framing_type) if framing_type is not None else None
    if climate_zone is not None and climate_zone not in ALL_ZONES:
        raise ValueError(f"climate_zone must be 1-8, got {climate_zone!r}")

    if phase_key is not None and framing_key is not None and climate_zone is not None:
        return list(CONSTRUCTION_MATRIX[(phase_key, framing_key, climate_zone)])
    return [
        rule
        for rule in CONSTRUCTION_RULES
        if (phase_key is None or rule.phase is phase_key) and rule.applies_to(framing_key, climate_zone)
    ]


def coerce_framing(value: FramingType | str) -> FramingType:
    """Parse loose user text such as ``"steel frame"`` into a ``FramingType``."""
    if isinstance(value, FramingType):
        return value
    text = str(value).casefold()
    if "steel" in text or "metal" in text or "nash" in text:
        return FramingType.STEEL
    if "timber" in text or "wood" in text or "stick" in text:
        return FramingType.TIMBER
    raise ValueError(f"unrecognised framing type: {value!r}")


def build_sequence(framing_type: FramingType | str, climate_zone: int) -> list[dict]:
    """Return the full ordered build sequence for a framing type and zone."""
    framing = coerce_framing(framing_type)
    return [
        {
            "phase": phase.value,
            "framing_type": framing.value,
            "climate_zone": climate_zone,
            "rules": [rule.as_dict() for rule in CONSTRUCTION_MATRIX[(phase, framing, climate_zone)]],
        }
        for phase in PHASE_ORDER
    ]


def membrane_requirement(climate_zone: int) -> dict:
    """Return the wall-membrane vapour permeance requirement for a zone."""
    if climate_zone not in ALL_ZONES:
        raise ValueError(f"climate_zone must be 1-8, got {climate_zone!r}")
    if climate_zone in WARM_ZONES:
        return {
            "climate_zone": climate_zone,
            "minimum_vapour_permeance_ug_per_Ns": None,
            "membrane_classes": ["Class 1", "Class 2", "Class 3", "Class 4"],
            "summary": "No zone-specific minimum permeance in clause 10.8.1(2). A Class 1 "
            "or 2 vapour barrier / reflective foil sarking is acceptable, and AS/NZS 4200.1 "
            "compliance plus AS/NZS 4200.2 installation still apply.",
            "provision": "NCC 2022 Housing Provisions clause 10.8.1",
        }
    if climate_zone in TEMPERATE_ZONES:
        return {
            "climate_zone": climate_zone,
            "minimum_vapour_permeance_ug_per_Ns": 0.143,
            "membrane_classes": ["Class 3", "Class 4"],
            "summary": "Membranes outside the primary wall insulation need a vapour "
            "permeance of at least 0.143 ug/N.s. The NCC explanatory material identifies "
            "Class 3 and Class 4 as meeting this threshold.",
            "provision": "NCC 2022 Housing Provisions clause 10.8.1(2)",
        }
    return {
        "climate_zone": climate_zone,
        "minimum_vapour_permeance_ug_per_Ns": 1.14,
        "membrane_classes": ["Class 4"],
        "summary": "Membranes outside the primary wall insulation need a vapour permeance "
        "of at least 1.14 ug/N.s. The NCC explanatory material identifies Class 4. Roof-space "
        "ventilation provisions in clause 10.8.3 also apply in zones 6-8.",
        "provision": "NCC 2022 Housing Provisions clauses 10.8.1(2) and 10.8.3",
    }


def framing_comparison() -> dict:
    """Side-by-side timber vs steel framing summary."""
    timber = FRAMING_PROFILES[FramingType.TIMBER]
    steel = FRAMING_PROFILES[FramingType.STEEL]
    return {
        "timber": timber.as_dict(),
        "steel": steel.as_dict(),
        "conductivity_ratio": round(steel.thermal_conductivity_w_mk / timber.thermal_conductivity_w_mk),
        "key_difference": "Steel framing requires a continuous R0.2 minimum thermal break "
        "under NCC 2022 Housing Provisions Part 13.2 where cladding is fixed directly to "
        "the frame; timber framing has no equivalent mandated thermal break.",
    }


def to_json(indent: int = 2) -> str:
    """Serialise the whole matrix for downstream retrieval or RAG indexing."""
    return json.dumps(
        {
            "ncc_edition": "NCC 2022",
            "scope_note": "Screening aid only. Not a compliance certificate. Required "
            "Total R-values are project-specific and are not tabulated here.",
            "phases": [phase.value for phase in PHASE_ORDER],
            "framing_profiles": {key.value: profile.as_dict() for key, profile in FRAMING_PROFILES.items()},
            "membrane_requirements": {str(zone): membrane_requirement(zone) for zone in sorted(ALL_ZONES)},
            "rules": [rule.as_dict() for rule in CONSTRUCTION_RULES],
        },
        indent=indent,
    )


if __name__ == "__main__":
    print(to_json())
