"""Read-only, evidence-scoped answers; no model, stock feed or web requests."""
from __future__ import annotations

import json
import logging
import math
import re
from datetime import datetime
from pathlib import Path

import sku_catalogue

ROOT = Path(__file__).resolve().parent
LOGGER = logging.getLogger(__name__)
GLOSSARY = ROOT / "knowledge" / "industry" / "training" / "01_glossary.md"
_GENERIC_NAMES = {
    "acoustic", "thermal", "insulation", "accessory", "batt", "batts", "under", "underlay",
    "barrier", "panel", "board", "foil", "tape", "mass", "pipe", "roof", "wall",
    "residential", "commercial", "industrial", "fire", "protection", "ceiling",
    "floor", "duct", "timber", "steel", "comfort", "noise", "sound", "thermal",
    "space", "access", "frame", "internal", "external", "moisture", "condensation",
}
_METRICS = {
    "thermal_r": r"\br[\s-]?value\b",
    "acoustic_rw": r"\brw\b",
    "acoustic_nrc": r"\bnrc\b",
    "thermal_conductivity": r"\b(?:conductivity|lambda)\b",
    "density": r"\bdensity\b",
    "temperature_limit": r"\b(?:temperature|temperature limit)\b",
    "acoustic_aw": r"\b(?:alpha|aw)\b",
    "vapour_permeance": r"\bpermeance\b",
    "vapour_class": r"\bvapour class\b",
}
_GENERIC_METRIC_SUBJECT_RE = re.compile(
    r"^(?:(?:a|an|the)\s+)?(?:insulation|all layers|building element|wall assembly|"
    r"wall|roof|ceiling|floor|building|house|structure)\b"
)


def normalise(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.casefold()))


def contains_name(text: str, name: str) -> bool:
    return f" {name} " in f" {text} "


def _metadata(path: Path | None) -> dict[str, str]:
    if path is None or not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    front = text.split("---", 2)[1]
    return dict(re.findall(r"^([a-z_]+):\s*(.+)$", front, re.M))


class ProductAnswers:
    def __init__(self, families: list[dict]):
        from knowledge_release import configured_release
        self.release = configured_release()
        self.families = families
        self.by_id = {family["family_id"]: family for family in families}
        self.source_paths = {}
        self.metadata = {}
        for path in ([] if self.release else ROOT.glob("knowledge/*/families.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            for row in data["families"]:
                key = row["family_id"]
                self.source_paths[key] = path.relative_to(ROOT).as_posix()
                knowledge = (path.parent / row["knowledge_file"]).resolve() if row.get("knowledge_file") else None
                if knowledge is not None and not knowledge.is_relative_to(path.parent.resolve()):
                    raise ValueError(f"Knowledge path escapes manufacturer directory: {key}")
                self.metadata[key] = _metadata(knowledge)
        if self.release:
            self.metadata = {family["family_id"]: {} for family in families}
            self.source_paths = {family["family_id"]: "reviewed release " + self.release["release_id"] for family in families}
        self.aliases: dict[str, set[str]] = {}
        for family in families:
            name = normalise(family["name"])
            manufacturer = normalise(family.get("manufacturer", ""))
            short = name.removeprefix(manufacturer + " ") if manufacturer else name
            aliases = {name, short, normalise(family["family_id"])}
            tokens = short.split()
            if tokens and tokens[0] not in _GENERIC_NAMES:
                # Shared prefixes deliberately retain all possible identities.
                aliases.update(" ".join(tokens[:count]) for count in range(1, len(tokens) + 1))
            aliases.update(alias[:-1] for alias in tuple(aliases) if alias.endswith("batts"))
            meta = self.metadata.get(family["family_id"], {})
            aliases.update(normalise(meta[key]) for key in ("canonical_name", "product_family", "brand") if meta.get(key))
            for alias in aliases:
                if alias and alias not in _GENERIC_NAMES:
                    self.aliases.setdefault(alias, set()).add(family["family_id"])

        self.definitions = {}
        for term, definition in re.findall(r"^\| \*\*(.+?)\*\* \| (.+?) \|$", GLOSSARY.read_text(encoding="utf-8"), re.M):
            self.definitions[normalise(term)] = (term, definition)
        if self.release:
            self.evidence = self.release["payload"]["evidence"]
        else:
            evidence = json.loads((ROOT / "knowledge" / "performance_evidence.json").read_text(encoding="utf-8"))
            self.evidence = {row["family_id"]: row["evidence_items"] for row in evidence["families"]}

    def resolve(self, message: str, scope: str | None = None) -> list[dict]:
        text = normalise(message)
        matches = [(alias, ids) for alias, ids in self.aliases.items() if contains_name(text, alias)]
        # A specific name supersedes its shared brand prefix, but not a
        # separately named comparison product.
        matches = [
            (alias, ids) for alias, ids in matches
            if not any(alias != other and contains_name(other, alias) for other, _ in matches)
        ]
        ids = set().union(*(ids for _, ids in matches)) if matches else set()
        families = [self.by_id[key] for key in sorted(ids)]
        if scope and scope.casefold() not in {"compare both", "all"}:
            families = [row for row in families if normalise(row.get("manufacturer", "")) == normalise(scope)]
        return families

    def family_introduction(self, message: str) -> str | None:
        text = normalise(message)
        subject = text
        for prefix in ("what is ", "what are ", "tell me about ", "explain "):
            if subject.startswith(prefix):
                subject = subject.removeprefix(prefix)
                break
        alias = self.aliases.get(subject)
        if not alias or len(alias) < 2 or len(subject.split()) < 2:
            return None
        display_name = subject.title()
        if display_name.endswith(" Batt"):
            display_name += "s"
        return (
            f"{display_name} is a range of insulation products with application-based variations. "
            "Which area are you insulating: a wall, ceiling, floor or partition?\n"
            "Source: local product-family catalogue."
        )

    def manufacturers(self, message: str) -> list[str]:
        return sorted({
            family.get("manufacturer", "") for family in self.families
            if contains_name(normalise(message), normalise(family.get("manufacturer", "")))
        } - {""})

    def definition(self, message: str) -> tuple[str, str] | None:
        text = normalise(message)
        if text in {"how does insulation work", "how insulation works"}:
            return "insulation", (
                "Thermal insulation resists heat flow. Heat can transfer by conduction "
                "(through solids), convection (air movement) and radiation (infrared).\n"
                "Source: knowledge/industry/training/01_glossary.md, R-Value, Conduction, Convection and Radiation."
            )
        if text in {"what is insulation", "tell me about insulation", "explain insulation"}:
            return "insulation", (
                "Thermal insulation resists heat flow; acoustic products address sound, "
                "which is a different property. Are you asking about heat, noise or a particular product?\n"
                "Source: knowledge/industry/training/01_glossary.md, R-Value, Rw and NRC."
            )
        matches = [key for key in self.definitions if contains_name(text, key)]
        if not matches:
            return None
        metric_subject = re.search(
            r"\b(?:r[\s-]?value|rw|nrc)\b.{0,40}?\b(?:for|of)\s+"
            r"([^?.!,;]+)",
            text,
        )
        if (
            metric_subject
            and not _GENERIC_METRIC_SUBJECT_RE.match(metric_subject.group(1).strip())
        ):
            return None
        matches = [key for key in matches if not any(key != other and contains_name(other, key) for other in matches)]
        lines = []
        for key in sorted(matches, key=len, reverse=True)[:2]:
            term, definition = self.definitions[key]
            definition = definition.replace("**", "").replace("`", "")
            lines.append(f"{term}: {definition}\nSource: knowledge/industry/training/01_glossary.md, {term}.")
        return matches[0], "\n".join(lines)

    def source(self, family: dict) -> str:
        path = self.source_paths.get(family["family_id"], "local families.json")
        return f"Source: {path}, {family['family_id']} ({family.get('manufacturer', '')})."

    def clarify(self, families: list[dict]) -> str:
        names = "; ".join(f"{index}) {row['name']}" for index, row in enumerate(families[:4], 1))
        more = " (there are more variants)" if len(families) > 4 else ""
        return f"Which product do you mean: {names}{more}? A full product name helps me check the right evidence."

    def metrics(self, family: dict, question: str) -> str:
        from research_store import DEFAULT_DB
        if not self.release and DEFAULT_DB.is_file():
            from knowledge_service import service
            self.evidence, publication = service().evidence()
            if publication["state"] not in {"published", "baseline_only"}:
                LOGGER.warning("Published research unavailable: %s", publication["state"])
        requested = [key for key, pattern in _METRICS.items() if re.search(pattern, question, re.I)]
        approved = []
        for item in self.evidence.get(family["family_id"], []):
            if item.get("metric_type") not in requested or item.get("evidence_status") != "verified":
                continue
            if not all(item.get(key) for key in ("evidence_id", "verified_by", "verified_at", "source_locator", "source_url", "variant", "scope", "test_context", "test_standard")) or "unit" not in item or "value" not in item:
                LOGGER.warning("Ignoring incomplete verified evidence for %s", family["family_id"])
                continue
            if re.search(r"\b(?:pending|unknown)\b", item["source_locator"], re.I):
                continue
            try:
                verified_at = datetime.fromisoformat(item["verified_at"].replace("Z", "+00:00"))
            except ValueError:
                LOGGER.warning("Ignoring invalid verified timestamp for %s", family["family_id"])
                continue
            if "T" not in item["verified_at"] or verified_at.tzinfo is None or not item["source_url"].startswith("https://"):
                LOGGER.warning("Ignoring incomplete verification provenance for %s", family["family_id"])
                continue
            value = item["value"]
            if not isinstance(value, (str, int, float)) or isinstance(value, bool) or (isinstance(value, (int, float)) and not math.isfinite(value)):
                LOGGER.warning("Ignoring invalid verified metric value for %s", family["family_id"])
                continue
            approved.append(item)
        if not approved:
            return (
                f"I don't have a verified value for that property of {family['name']} in the local evidence. "
                "The technical team needs to confirm the exact variant and test context."
            )
        lines = [
            f"{item['variant']}: {item['metric_type']} {item['value']} {item['unit'] or '(dimensionless)'} "
            f"({item['scope']} scope; {item['test_context']}). "
            f"Source: {item['evidence_id']}, {item['source_locator']}, {item['test_standard']}."
            for item in approved[:3]
        ]
        return "\n".join(lines) + "\nThese are documented test values, not a prediction of your installed result."

    def answer(self, question: str, families: list[dict], *, sizes: bool = False) -> str:
        if not families:
            return "Which product do you mean? Please share its full name so I can check the local information."
        if len(families) > 1 and not re.search(r"\b(?:compare|difference|versus|vs)\b", question, re.I):
            return self.clarify(families)
        if len(families) > 2:
            return self.clarify(families)
        if len(families) == 1 and re.search(r"\b(?:compare|difference|versus|vs)\b", question, re.I):
            return f"I can identify {families[0]['name']} locally. Which other product should I compare it with?"
        if any(any(word in str(row.get("confidence", "")) for word in ("secondary", "identity_unverified", "identity_review")) for row in families):
            return "The product identity/evidence still needs review; I can't confirm its characteristics or recommend it."
        if re.search(r"\b(?:how much|quantity|coverage|pack cover|how many|area)\b", question, re.I):
            return "The team needs the product variant and project dimensions to confirm quantity or pack coverage; I can't calculate an order from this information."
        if re.search(r"\b(?:stock|available|availability|do you have|carry|sell)\b", question, re.I) and not re.search(r"\d+\s*mm\b", question, re.I):
            return f"I can check documented options for {families[0]['name']}, but I don't have live stock information. Please ask sales to confirm current availability."
        if sizes:
            return self.dimensions(families[0], question)
        if re.search(r"\b(?:rating|r[\s-]?value|rw|nrc|conductivity|density|performs?|performance|temperature|permeance|vapour class)\b", question, re.I):
            if len(families) != 1:
                return "Which product and performance metric should I check? I can compare only values with verified, matching test contexts."
            return self.metrics(families[0], question)
        replies = []
        for family in families:
            if re.search(r"\b(?:made of|made from|material)\b", question, re.I):
                material = self.metadata[family["family_id"]].get("material", "")
                if material and not re.search(r"\d", material):
                    replies.append(f"{family['name']}: {material}.")
                else:
                    replies.append(f"I don't have a confirmed material description for {family['name']} in the local information.")
            elif re.search(r"\b(?:install|installation|fix|cut)\b", question, re.I):
                replies.append(f"For {family['name']}, use its current manufacturer installation guide; the team must check the substrate, joints and project requirements. I can't prescribe an installation for your project.")
            elif re.search(r"\b(?:weigh|weight|recycled|VOC|colour|color|contains?|content)\b", question, re.I):
                replies.append(f"I don't have confirmed local information about that detail of {family['name']}. Please ask the team to check its current datasheet.")
            elif re.search(r"\b(?:tell me|what is|what are|what about|used for|purpose|function|application|compare|difference|vs|versus|looking for|interested in|I want|I need)\b", question, re.I) or re.search(r"\bwhat does\b.+\bdo[?.! ]*$", question, re.I) or normalise(question) in self.aliases or question.strip().isdigit():
                function = "" if self.release else family.get("primary_function", "")
                replies.append(f"{family['name']}: {function}" if function else f"I don't have a confirmed description of {family['name']} in the local information.")
            else:
                replies.append(f"I don't have confirmed local information about that detail of {family['name']}. Please ask the team to check its current datasheet.")
            replies.append(self.source(family))
        return "\n".join(replies)

    def dimensions(self, family: dict, question: str) -> str:
        if re.search(r"\b(?:depth|height)\b", question, re.I):
            return f"I don't have a confirmed depth or height field for {family['name']} in the local catalogue. Please ask the team to check its current datasheet."
        if not sku_catalogue.available():
            return f"I don't have confirmed catalogue dimensions for {family['name']} locally. Please ask the team to check the exact variant."
        rows = sku_catalogue.skus_for_family(family["family_id"], limit=200)
        wanted = [("thickness", "thickness_mm"), ("width", "width_mm"), ("length", "length_mm")]
        fields = [(label, key) for label, key in wanted if label in question.casefold() or (label == "thickness" and "thick" in question.casefold())]
        if not fields:
            fields = wanted
        number = re.search(r"\b(\d+(?:\.\d+)?)\s*mm\b", question, re.I)
        if number:
            if len(fields) != 1:
                return f"Do you mean {number.group(1)} mm thickness, width or length for {family['name']}?"
            key = fields[0][1]
            target = float(number.group(1))
            rows = [row for row in rows if row.get(key) is not None and abs(row[key] - target) < 0.000001]
            if not rows:
                return f"I don't have a confirmed {number.group(1)} mm {fields[0][0]} option for {family['name']} in the local catalogue. Sales needs to check the exact variant and current availability."
        values = []
        for label, key in fields:
            options = sorted({row[key] for row in rows if row.get(key) is not None})
            if options:
                values.append(f"{label}: {', '.join(f'{value:g}' for value in options[:8])} mm")
        if not values:
            return f"I don't have confirmed catalogue dimensions for {family['name']} locally. Please ask the team to check the exact variant."
        return (
            f"Documented catalogue options for {family['name']} - {'; '.join(values)}. "
            "These dimensions belong to different variants, not necessarily one combination; they are not a suitability recommendation or live stock confirmation.\n"
            f"Source: local product_skus catalogue, confirmed family link {family['family_id']}."
        )
