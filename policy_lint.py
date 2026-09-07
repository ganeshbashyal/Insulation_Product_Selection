"""Policy lint: validate generated text against BOT_POLICY constraints.

Softer mode: rejects assertions/guarantees, not mere mentions.
- SKU assertions ("this 50mm model", not just "50mm")
- Compliance claims (NCC, fire, BAL, AS, etc.)
- Guarantee language ("guaranteed", "will", "ensure", "promise")
- Other family names (only recommended family allowed)
"""
from __future__ import annotations

import re

# Patterns for compliance-related terms (strict — reject all)
COMPLIANCE_TERMS = re.compile(
    r"\b(NCC|Australian\s+Standard|AS\s+\d+|fire[\s-]?rat|BAL[\s-]?\d+|complian|certifi|approv|standard|regulat)\b",
    re.IGNORECASE,
)

# Patterns for guarantee/promise language (strict — reject all)
GUARANTEE_LANGUAGE = re.compile(
    r"\b(guarant|will[\s]+\w+|ensure|promise|certif[^i]|safe\s+as|she[']?ll be right|protect|prevent|stop|block|resist)\b",
    re.IGNORECASE,
)

# Patterns for SKU-like mentions (softer — only reject if seems like assertion)
SKU_ASSERTION_PATTERNS = [
    r"(?:this|our|the|this\s+)?(\d+mm)[^\w]",  # "this 50mm", "the 50mm"
    r"(?:in|available|comes\s+in)\s+([a-z]+\s+)?(\d+[a-z]+)",  # "in 50mm", "available 100mm"
    r"grade\s+([A-Z]+\d+)",  # "Grade A1", "Grade F"
    r"density.*?(\d+\s*kg)",  # "density 25 kg"
]
SKU_ASSERTION_RE = re.compile("|".join(SKU_ASSERTION_PATTERNS), re.IGNORECASE)

# Family names to protect (get from agent_core.FAMILIES)
PROTECTED_FAMILY_NAMES = set()


class PolicyLintResult:
    """Result of policy validation."""

    def __init__(self, passed: bool, violations: list[str] = None, fallback_text: str = ""):
        self.passed = passed
        self.violations = violations or []
        self.fallback_text = fallback_text


class PolicyLinter:
    """Validate generated text against BOT_POLICY constraints."""

    def __init__(self, protected_families: set[str] = None):
        self.protected_families = protected_families or set()

    def lint(self, text: str, recommended_family: str | None = None) -> PolicyLintResult:
        """
        Validate text. Returns PolicyLintResult with pass/fail + violations.
        recommended_family is the ONLY family name allowed in the text.
        """
        if not text or not isinstance(text, str):
            return PolicyLintResult(passed=True)

        violations = []

        # Check for compliance claims
        if COMPLIANCE_TERMS.search(text):
            violations.append("Compliance claim detected (NCC, fire, BAL, etc.)")

        # Check for guarantee language
        if GUARANTEE_LANGUAGE.search(text):
            violations.append("Guarantee/promise language detected (will, ensure, guaranteed, etc.)")

        # Check for SKU assertions (softer validation)
        if SKU_ASSERTION_RE.search(text):
            violations.append("SKU or product specification assertion detected")

        # Check for other family names (only allow recommended family)
        if recommended_family:
            for family in self.protected_families:
                if family.lower() != recommended_family.lower() and family.lower() in text.lower():
                    violations.append(f"Family name mentioned: {family} (only {recommended_family} is allowed)")

        passed = len(violations) == 0

        return PolicyLintResult(
            passed=passed,
            violations=violations,
            fallback_text=self._fallback_text(recommended_family),
        )

    def _fallback_text(self, family_name: str | None = None) -> str:
        """Generate safe fallback text when policy validation fails."""
        if family_name:
            return f"**{family_name}** looks like the best fit. I'll confirm the details before moving forward."
        return "Thank you for that information. Let me have our team review and get back to you."
