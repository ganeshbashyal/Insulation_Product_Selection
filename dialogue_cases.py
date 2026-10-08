"""Synthetic customer conversations shared by offline tests and evaluation."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DialogueCase:
    name: str
    messages: tuple[str, ...]
    category: str
    contains: tuple[str, ...]
    step: int | None = 0
    answer: tuple[str, str] | None = None


CASES = (
    DialogueCase("greeting", ("Hi",), "greeting", ("insulation",)),
    DialogueCase("thanks", ("Thanks",), "greeting", ("welcome",)),
    DialogueCase("r-value", ("What is R-value?",), "informational", ("thermal resistance", "source")),
    DialogueCase("u-value", ("What is U-value?",), "informational", ("thermal transmittance", "source")),
    DialogueCase("total-r", ("What is Total R-value?",), "informational", ("all layers", "source")),
    DialogueCase("product-r", ("What is Product R-value?",), "informational", ("single", "source")),
    DialogueCase("thermal-bridge", ("What is thermal bridging?",), "informational", ("bypassing", "source")),
    DialogueCase("sarking", ("What is sarking?",), "informational", ("membrane", "source")),
    DialogueCase("dew-point", ("What is dew point?",), "informational", ("condenses", "source")),
    DialogueCase("rw", ("What does Rw mean?",), "informational", ("sound reduction", "source")),
    DialogueCase("known-product", ("Tell me about NuWrap 5",), "informational", ("nuwrap", "source")),
    DialogueCase("product-use", ("What is NuWrap 5 used for?",), "informational", ("nuwrap", "source")),
    DialogueCase("manufacturer", ("Tell me about Thermotec",), "informational", ("which", "product")),
    DialogueCase("ambiguous-brand", ("Tell me about NuWave",), "informational", ("which", "nuwave")),
    DialogueCase("unknown-product", ("Tell me about ImaginaryBatt9000",), "informational", ("local", "information")),
    DialogueCase("missing-rating", ("What is NuWrap 5's Rw rating?",), "informational", ("verified",)),
    DialogueCase("stock", ("Is NuWrap 5 in stock?",), "size-availability", ("stock", "confirm")),
    DialogueCase("quantity", ("How much NuWrap 5 do I need?",), "size-availability", ("quantity", "team")),
    DialogueCase("price", ("What does NuWrap 5 cost?",), "commercial", ("sales",)),
    DialogueCase("compliance", ("Is NuWrap 5 NCC compliant?",), "escalate", ("cannot", "compliance")),
    DialogueCase("install-service", ("Can you install this?",), "service_refusal", ("supply",)),
    DialogueCase("tracking", ("Where is my order?",), "tracking", ("not connected",)),
    DialogueCase("freight", ("How much is delivery?",), "freight", ("not available",)),
    DialogueCase("remember-product", ("Tell me about NuWrap 5", "What is it used for?"), "informational", ("nuwrap", "source")),
    DialogueCase("change-product", ("Tell me about NuWrap 5", "Tell me about NuWave Mass Loaded Vinyl Acoustic Barrier"), "informational", ("airborne", "source")),
    DialogueCase("ambiguous-pronoun", ("What is it made of?",), "informational", ("which", "product")),
    DialogueCase("greet-then-select", ("Hi", "My external wall is cold"), "product-fit", ("existing", "new build"), 1),
    DialogueCase("skip-project-stage", ("My external wall is cold", "skip"), "product-fit", ("building used",), 1),
    DialogueCase("unknown-project-stage", ("My external wall is cold", "I don't know"), "product-fit", ("building used",), 1),
    DialogueCase("interrupt-name", ("My external wall is cold", "What is R-value?"), "informational", ("thermal resistance",), 1),
    DialogueCase("resume-name", ("My external wall is cold", "What is R-value?", "Residential retrofit"), "product-fit", ("wall is built",), 1, ("building_use", "residential")),
    DialogueCase("later-details", ("My wall is cold", "Thermal comfort, residential retrofit in Sydney 2000, no space constraints"), "product-fit", ("internal", "external"), 1, ("project", "residential retrofit")),
    DialogueCase("correct-application", ("My wall is cold", "Actually it is the roof, not the wall"), "product-fit", ("focus", "roofline"), 1, ("application", "roof")),
    DialogueCase("requirements-answer", ("My external wall is cold", "Thermal comfort, residential retrofit in Sydney 2000, no space constraints", "No NCC or fire requirement"), "product-fit", ("wall is built",), 1, ("requirements", "ncc")),
    DialogueCase("early-handoff", ("Retrofit thermal insulation behind a brick wall with plasterboard", "stop questions", "synthetic@example.com", "skip"), "product-fit", ("saved locally", "not booked"), 8),
    DialogueCase("decline-contact", ("Cold wall, no access and cannot remove the lining", "finish now", "no thanks"), "product-fit", ("saved locally",), 8),
    DialogueCase("clarify-brief", ("Help me choose insulation",), "product-fit", ("where",), 1),
    DialogueCase("construction-preserved", ("Cold external wall in my existing home", "Brick with plasterboard"), "product-fit", ("brick veneer", "solid"), 1, ("construction", "plasterboard")),
    DialogueCase("depth-not-product", ("Cold external wall in my existing home", "90mm cavity depth"), "product-fit", ("wall is built",), 1, ("cavity_depth", "90mm")),
    DialogueCase("complete-volunteered-brief", (
        "Cold existing external timber frame wall in my home in Sydney 2000, 90mm cavity depth, 20 square metres, lining will be removed, no insulation, no moisture, unknown airspace, no specified requirements, next month",
        "synthetic@example.com", "skip",
    ), "product-fit", ("saved locally", "not booked"), 8, ("cavity_depth", "90mm")),
    DialogueCase("insulation-definition", ("What is insulation?",), "informational", ("heat flow", "source")),
    DialogueCase("insulation-work", ("How does insulation work?",), "informational", ("conduction", "convection", "radiation", "source")),
    DialogueCase("casual-definition", ("Can you explain R-value",), "informational", ("thermal resistance", "source")),
    DialogueCase("bare-term", ("R-value",), "informational", ("thermal resistance", "source")),
)
