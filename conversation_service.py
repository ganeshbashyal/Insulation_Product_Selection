"""Shared orchestration for local conversation channels."""
from __future__ import annotations

from dataclasses import dataclass

import agent_core
import interaction_store
from policy_lint import PolicyLinter
from rag_answerer import RAGAnswerer
from router import MessageRouter
from tools import ToolRegistry, default_registry


@dataclass(frozen=True)
class TurnResult:
    reply: str
    done: bool
    category: str
    retrieval_mode: str
    human_review_required: bool


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
        self.router = router or MessageRouter(use_llm=use_llm)
        self.rag_answerer = rag_answerer or RAGAnswerer()
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
    ) -> TurnResult:
        classification = self.router.classify(message)
        tool_result = self.tool_registry.dispatch(
            classification.category, message, conversation, site_id
        )
        retrieval_mode = "none"

        if tool_result is not None:
            reply = tool_result.reply
            conversation.done = tool_result.done
        elif classification.is_informational:
            rag_result = self.rag_answerer.answer(message, use_llm=self.use_llm)
            reply = rag_result["answer"]
            retrieval_mode = rag_result.get("retrieval_mode", "lexical")
        elif classification.category == "size-availability":
            reply = agent_core.answer_size_query(message)
            if reply is None:
                reply = (
                    "Please include the family or product name and any known "
                    "width, thickness or R-value so I can check the local catalogue."
                )
            retrieval_mode = "catalogue"
        else:
            reply = agent_core.reply(
                conversation,
                message,
                use_llm=self.use_llm,
                manufacturer_scope=manufacturer_scope,
                site_id=site_id,
            )
            retrieval_mode = "deterministic-ranking"

        if conversation.recommendation:
            lint_result = self.policy_linter.lint(
                reply, recommended_family=conversation.recommendation.get("name")
            )
            if not lint_result.passed:
                reply = lint_result.fallback_text

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
                answers={**conversation.answers, "_message": message},
                recommendation=None,
                gate_status=gate_status,
                gate_reason=gate_reason,
                climate_zone=None,
                candidates=[],
            )

        return TurnResult(
            reply=reply,
            done=conversation.done,
            category=classification.category,
            retrieval_mode=retrieval_mode,
            human_review_required=bool(
                conversation.done
                or conversation.recommendation is not None
                or classification.category in {"commercial", "escalate"}
            ),
        )
