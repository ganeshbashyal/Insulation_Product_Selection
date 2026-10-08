"""Shared orchestration for local conversation channels."""
from __future__ import annotations

from dataclasses import dataclass
import re

import agent_core
import interaction_store
from policy_lint import PolicyLinter
from product_answers import ProductAnswers
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from rag_answerer import RAGAnswerer
from router import MessageRouter, RouterClassification, asks_question, asks_selection
from tools import ToolRegistry, default_registry


_EXPLICIT_CLOSURE_RE = re.compile(
    r"\b(?:"
    r"that(?:'s| is)\s+(?:all|everything|it|enough)\b"
    r"|i(?:'m| am)\s+(?:all\s+(?:set|done)|done|finished)\b"
    r"|all\s+set\b"
    r"|done\s+for\s+now\b"
    r"|finished\s+for\s+now\b"
    r"|no\s+more\s+questions\b"
    r"|nothing\s+else\b"
    r")",
    re.I,
)
_COURTESY_ONLY_RE = re.compile(
    r"^\s*(?:thanks?|thank\s+you|cheers|"
    r"(?:(?:i\s+)?(?:really\s+|truly\s+)?appreciate\s+(?:it|that|your help|your assistance|"
    r"the help|the assistance|the explanation))|much appreciated)"
    r"(?:\s+(?:very much|so much|a lot|again|for (?:your|the) "
    r"(?:help|assistance|explanation|information|details|support)|for that))*"
    r"[.! ]*$",
    re.I,
)


@dataclass(frozen=True)
class TurnResult:
    reply: str
    done: bool
    category: str
    retrieval_mode: str
    human_review_required: bool
    review_labels: tuple[str, ...] = ()


class ConversationService:
    """Apply routing, safety policy, and audit behavior consistently."""

    def __init__(
        self,
        *,
        use_llm: bool = False,
        router: MessageRouter | None = None,
        rag_answerer: RAGAnswerer | None = None,
        policy_linter: PolicyLinter | None = None,
        tool_registry: ToolRegistry | None = None,
    ):
        self.use_llm = use_llm
        # Local models improve wording, not the product/intent decision.
        self.router = router or MessageRouter(use_llm=False)
        self.product_answers = ProductAnswers(agent_core.FAMILIES)
        self.rag_answerer = rag_answerer
        if self.rag_answerer is None and self.product_answers.release is None:
            from rag_answerer import RAGAnswerer
            self.rag_answerer = RAGAnswerer()
        self.policy_linter = policy_linter or PolicyLinter(
            protected_families={family["name"] for family in agent_core.FAMILIES}
        )
        self.tool_registry = tool_registry or default_registry()

    def handle(
        self,
        conversation: agent_core.Conversation,
        message: str,
        *,
        site_id: str = "default",
        manufacturer_scope: str | None = None,
        use_llm: bool | None = None,
    ) -> TurnResult:
        phrase_with_model = self.use_llm if use_llm is None else use_llm
        explicit_closure = bool(
            _EXPLICIT_CLOSURE_RE.search(message) and not asks_question(message)
        )
        courtesy_only = bool(_COURTESY_ONLY_RE.fullmatch(message))
        conversation.recommendation = None
        family_introduction = self.product_answers.family_introduction(message)
        if conversation.mode == "selection" and conversation.answers.get("problem") and not conversation.done:
            if conversation.step >= len(agent_core.QUESTIONS):
                conversation.mode = "capture"
                conversation.discovery_ended_early = True
            else:
                conversation.mode = "discovery"
                conversation.pending_field = agent_core.discovery.next_field(conversation.answers, conversation.discovery_status)
        answering = conversation.mode in {"discovery", "capture", "callback"} and not asks_question(message)
        classification = self.router.classify(message, answering=answering)
        opening_brief = (
            conversation.mode == "enquiry"
            and not asks_question(message)
            and "application" in agent_core.extract_turn_details(message)
            and bool(re.search(r"\b(?:my|our|existing|retrofit|retrofitting|renovation|new build|want|need|cold|hot|noise)\b", message, re.I))
        )
        if opening_brief:
            classification = RouterClassification("product-fit", 1.0)
        if (classification.category == "product-fit" and conversation.mode == "enquiry"
                and (self.product_answers.definition(message) or family_introduction)
                and not asks_selection(message)):
            classification = RouterClassification("informational", 1.0)
        callback_request = bool(re.search(
            r"^(?:please\s+|(?:can|could)\s+(?:you|someone|the team)\s+)?(?:call me|contact me|call back|acll back)\b"
            r"|\b(?:I'd like|I want|I need|request|arrange)\s+(?:a\s+)?(?:callback|call back|acll back)\b", message, re.I,
        ))
        if callback_request:
            classification = RouterClassification("callback", 1.0)
        supplied_contact = (
            conversation.capturing_lead and not asks_question(message)
            and any(agent_core.parse_contact_details(message).values())
        )
        products = [] if supplied_contact else self.product_answers.resolve(message, manufacturer_scope)
        matched_product_option = False
        if conversation.product_options and not products and not message.strip().isdigit():
            words = set(re.findall(r"[a-z0-9]+", message.casefold()))
            option_matches = []
            for family_id in conversation.product_options:
                family = self.product_answers.by_id.get(family_id)
                if family is None:
                    continue
                name_words = set(re.findall(r"[a-z0-9]+", family.get("name", "").casefold()))
                score = len(words & name_words)
                if score:
                    option_matches.append((score, family))
            if option_matches:
                best_score = max(score for score, _ in option_matches)
                best_matches = [family for score, family in option_matches if score == best_score]
                if len(best_matches) == 1:
                    products = best_matches
                    matched_product_option = True
        if family_introduction and not asks_selection(message):
            products = []
            conversation.topic_products = []
            conversation.product_options = []
        if opening_brief or (conversation.mode == "discovery" and not asks_question(message) and not asks_selection(message) and (
            agent_core.extract_turn_details(message) or agent_core.discovery.observed(message)
        )):
            products = []
        if conversation.product_options and message.strip().isdigit():
            index = int(message.strip()) - 1
            if 0 <= index < len(conversation.product_options):
                products = [self.product_answers.by_id[conversation.product_options[index]]]
                matched_product_option = True
        references_product = bool(re.search(r"\b(?:it|its|this|that|them|their)\b", message, re.I))
        short_followup = bool(re.fullmatch(
            r"\s*(?:(?:and|what about|how about|the)\s+)?(?:width|thickness|length|sizes?|material|rating|availability)[?.! ]*",
            message, re.I,
        ))
        if not products and not supplied_contact and (short_followup or (references_product and asks_question(message))):
            products = [
                self.product_answers.by_id[key] for key in conversation.topic_products
                if key in self.product_answers.by_id
                and (not manufacturer_scope or manufacturer_scope.casefold() in {"compare both", "all"} or self.product_answers.by_id[key].get("manufacturer", "").casefold() == manufacturer_scope.casefold())
            ]
        contextual_family_id = conversation.family_review_id
        if not contextual_family_id and len(conversation.topic_products) == 1:
            contextual_family_id = conversation.topic_products[0]
        if (
            not products
            and not supplied_contact
            and contextual_family_id in self.product_answers.by_id
            and (asks_question(message) or re.search(r"\b(?:rating|r[\s-]?value|rw|nrc|conductivity|density|performs?|performance)\b", message, re.I))
            and not re.search(r"\b(?:suitable|suitability|recommend|should i use|right for my)\b", message, re.I)
        ):
            products = [self.product_answers.by_id[contextual_family_id]]
        if self.product_answers.release:
            from knowledge_release import visible_family_ids
            allowed = visible_family_ids(self.product_answers.release, site_id)
            products = [family for family in products if family["family_id"] in allowed]
            conversation.topic_products = [key for key in conversation.topic_products if key in allowed]
            conversation.product_options = [key for key in conversation.product_options if key in allowed]
        if (
            conversation.family_review_id in self.product_answers.by_id
            and len(products) > 1
            and not re.search(r"\b(?:compare|difference|vs|versus)\b", message, re.I)
        ):
            pinned = self.product_answers.by_id[conversation.family_review_id]
            if any(row["family_id"] == conversation.family_review_id for row in products):
                products = [pinned]
        if products:
            if len(products) == 1 or (len(products) == 2 and re.search(r"\b(?:compare|difference|vs|versus)\b", message, re.I)):
                conversation.topic_products = [row["family_id"] for row in products]
                conversation.product_options = []
            else:
                conversation.topic_products = []
                conversation.product_options = [row["family_id"] for row in products[:4]]

        # A technical requirement supplied to a pending intake question is a
        # fact to retain, not a request to certify a building.
        intake_answer = (
            conversation.mode in {"discovery", "capture", "callback"}
            and not conversation.done
            and not asks_question(message)
            and not products
        )
        if classification.category == "escalate" and intake_answer:
            conversation.review_required = True
            classification = RouterClassification("product-fit", 1.0)
        elif classification.category in {"product-fit", "informational"} and products and (
            not asks_selection(message) or matched_product_option
        ):
            classification = RouterClassification("informational", 1.0)
        elif intake_answer and classification.category in {"size-availability", "commercial"}:
            # "Budget is my priority" and "90 mm cavity" answer intake;
            # explicit price/order/stock questions still use their own route.
            if not re.search(r"\b(?:quote|price|order|buy|stock)\b", message, re.I):
                classification = RouterClassification("product-fit", 1.0)
        if supplied_contact or (
            (conversation.capturing_lead or conversation.mode == "discovery")
            and re.fullmatch(r"\s*(?:can I\s+)?(?:skip|no thanks|rather not)[?.! ]*", message, re.I)
        ):
            classification = RouterClassification("product-fit", 1.0)
        if explicit_closure or courtesy_only:
            classification = RouterClassification("greeting", 1.0)

        tool_result = self.tool_registry.dispatch(
            classification.category, message, conversation, site_id
        )
        retrieval_mode = "none"

        if classification.category == "greeting":
            if explicit_closure:
                reply = (
                    "No problem — I'll pause here. The details you've shared are unchanged; "
                    "you can continue whenever you're ready."
                )
            elif courtesy_only or re.search(r"thank|cheers", message, re.I):
                reply = "You're welcome. I can help with another product question whenever you need."
            else:
                reply = agent_core.OPENING
            if (
                not explicit_closure
                and conversation.mode in {"discovery", "capture", "callback"}
                and not conversation.done
            ):
                reply += "\n\n" + conversation.next_prompt()
        elif classification.category == "callback":
            conversation.review_required = True
            if conversation.done:
                has_contact = bool(conversation.lead.get("phone") or conversation.lead.get("email"))
                if has_contact and conversation.lead.get("callback_time"):
                    reply = (
                        f"Your callback preference ({conversation.lead['callback_time']}) and contact details "
                        "are already saved with this project for sales review. A callback is not booked automatically."
                    )
                else:
                    conversation.done = False
                    conversation.mode = "capture"
                    conversation.discovery_ended_early = True
                    conversation.step = len(agent_core.QUESTIONS)
                    conversation.lead.pop("declined", None)
                    conversation.lead_step = 1 if has_contact else 0
                    conversation.lead.setdefault("handoff_consent_status", "not_recorded")
                    reply = conversation.next_prompt()
            else:
                if not conversation.capturing_lead:
                    conversation.mode = "capture"
                    conversation.discovery_ended_early = True
                    conversation.step = len(agent_core.QUESTIONS)
                    conversation.lead_step = 0
                if not conversation.answers.get("problem") and agent_core._is_problem_description(message):
                    conversation.answers["problem"] = message.strip()
                reply = conversation.next_prompt()
        elif tool_result is not None:
            reply = tool_result.reply
            conversation.done = tool_result.done
            if classification.category in {"commercial", "escalate"}:
                conversation.review_required = True
        elif (
            conversation.done
            and conversation.topic_products
            and re.fullmatch(r"\s*(?:yes|yeah|yep|sure|okay|ok|that's right|that is right)[.! ]*", message, re.I)
        ):
            family = self.product_answers.by_id.get(conversation.topic_products[0])
            name = family["name"] if family else "that product"
            if conversation.lead.get("callback_time") and (
                conversation.lead.get("phone") or conversation.lead.get("email")
            ):
                reply = (
                    f"Sure — what would you like to know about {name}? Your callback preference is already "
                    f"saved for sales review ({conversation.lead['callback_time']}); a callback is not booked automatically."
                )
            else:
                reply = f"Sure — what would you like to know about {name}?"
        elif classification.is_informational:
            definition = self.product_answers.definition(message) if not products and not family_introduction else None
            if family_introduction:
                reply = family_introduction
                retrieval_mode = "family-description"
            elif products:
                reply = self.product_answers.answer(message, products)
                retrieval_mode = "product-evidence"
                if re.search(r"\b(?:rating|r[\s-]?value|rw|nrc|density|install|stock|verified|review)\b", message + " " + reply, re.I):
                    conversation.review_required = True
            elif definition:
                conversation.topic, reply = definition
                retrieval_mode = "local-glossary"
            elif self.product_answers.manufacturers(message):
                reply = "Which product from that manufacturer do you mean? Please share its name, or tell me what you need it for."
                retrieval_mode = "product-evidence"
            elif references_product:
                reply = "Which product do you mean? Please share its name so I can check the right local evidence."
                retrieval_mode = "product-evidence"
            else:
                # Wording opt-in must not trigger a corpus-wide embedding job.
                rag_result = ({"answer": "I don't have reviewed information for that question in this release. Please ask the team to check the source.",
                               "retrieval_mode": "release-unknown"} if self.product_answers.release
                              else self.rag_answerer.answer(message, use_llm=False))
                reply = rag_result["answer"]
                retrieval_mode = rag_result.get("retrieval_mode", "lexical")
                lint_result = self.policy_linter.lint(reply)
                if not lint_result.passed:
                    reply = "I don't have a verified answer to that in the local information. Please ask the team to check the source and project context."
        elif classification.category == "size-availability":
            if products:
                reply = self.product_answers.answer(message, products, sizes=True)
            elif re.search(r"\b(?:stock|available|availability)\b", message, re.I):
                reply = "Which product do you mean? I don't have live stock information; sales needs to confirm current availability."
            elif re.search(r"\b(?:how much|how many|quantity|coverage)\b", message, re.I):
                reply = "The team needs the product variant and project dimensions to confirm quantity or pack coverage."
            else:
                reply = "Which product do you mean? Please share its full name so I can check documented dimensions without mixing different families."
            retrieval_mode = "catalogue"
        else:
            reply = agent_core.reply(
                conversation,
                message,
                use_llm=phrase_with_model,
                manufacturer_scope=manufacturer_scope,
                site_id=site_id,
            )
            retrieval_mode = "needs-capture"

        if classification.category != "product-fit":
            if tool_result is not None:
                gate_status = tool_result.log_status or f"routed:{classification.category}"
                gate_reason = (
                    tool_result.log_reason
                    or f"Router classified this as {classification.category}."
                )
            else:
                gate_status = f"routed:{classification.category}"
                gate_reason = (
                    f"Router classified this as {classification.category} "
                    f"(confidence {classification.confidence:.2f}); "
                    "no product recommendation was made."
                )
            interaction_store.log_conversation(
                conversation_id=conversation.conversation_id,
                site_id=site_id,
                answers=conversation.answers,
                recommendation=conversation.recommendation,
                gate_status=conversation.gate[0] if conversation.gate else gate_status,
                gate_reason=conversation.gate[1] if conversation.gate else gate_reason,
                climate_zone=None,
                candidates=conversation.candidates,
            )

        review_labels = []
        if conversation.answers or conversation.mode in {"discovery", "capture", "callback"}:
            review_labels.append("customer_project_facts_unverified")
        if classification.category == "escalate" or re.search(
            r"\b(?:NCC|BAL|fire[- ]rating|compliance|certif(?:ied|ication)|engineering design)\b",
            message, re.I,
        ):
            review_labels.append("regulated_or_compliance_review_required")
        if conversation.discovery_status.get("application") == "conflict":
            review_labels.append("conflicting_application_requires_clarification")
        elif re.search(r"\b(?:actually|correction|I meant|rather than|instead of)\b", message, re.I):
            review_labels.append("customer_correction_recorded")
        if classification.category in {"commercial", "size-availability", "freight", "tracking"}:
            review_labels.append("sales_confirmation_required")
        if conversation.done or conversation.review_required:
            review_labels.append("internal_human_review_required")
        if conversation.done and conversation.lead.get("handoff_consent_status") != "granted":
            review_labels.append("neo_handoff_not_authorized_by_customer")
        if conversation.done and conversation.lead.get("handoff_consent_status") == "granted":
            review_labels.append("neo_handoff_requires_operator_approval")
        human_review_required = bool(
            review_labels
            or conversation.done
            or conversation.recommendation is not None
            or conversation.review_required
            or classification.category in {"commercial", "escalate"}
        )
        return TurnResult(
            reply=reply,
            done=conversation.done,
            category=classification.category,
            retrieval_mode=retrieval_mode,
            human_review_required=human_review_required,
            review_labels=tuple(dict.fromkeys(review_labels)),
        )
