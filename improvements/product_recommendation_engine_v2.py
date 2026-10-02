"""
Improved recommendation and gating logic for insulation product selection.

Key improvements:
- Proper error handling with config defaults
- Type hints with TypedDicts for clarity
- Comprehensive logging for debugging
- Config-driven weights and thresholds
- Better text normalization with lemmatization
- Improved priority detection with negation handling
- Data-driven placement adjustments
- Detailed docstrings with examples
"""

from __future__ import annotations

import logging
import os
import re
import json
from difflib import SequenceMatcher
from pathlib import Path
from typing import TypedDict, Optional, Callable
from enum import Enum
from dataclasses import dataclass, field, asdict

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ============================================================================
# TYPE DEFINITIONS
# ============================================================================

class Priority(str, Enum):
    """Supported priority categories for product selection."""
    ACOUSTIC_COMFORT = "acoustic_comfort"
    ENERGY_EFFICIENCY = "energy_efficiency"
    SUSTAINABILITY = "sustainability"
    INSTALLATION_PRACTICALITY = "installation_practicality"
    COMPLIANCE_READINESS = "compliance_readiness"


class RecommendationState(str, Enum):
    """States that determine if a product can be recommended."""
    APPROVED = "approved"
    PENDING_REVIEW = "pending_review"
    BLOCKED = "blocked"
    DISCONTINUED = "discontinued"


class GatingDecision(str, Enum):
    """Gating decisions for recommendations."""
    APPROVED = "APPROVED"
    REVIEW_REQUIRED = "REVIEW REQUIRED"
    BLOCKED = "BLOCKED"


class PriorityScore(TypedDict):
    """Scoring for each priority category."""
    acoustic_comfort: float
    energy_efficiency: float
    sustainability: float
    installation_practicality: float
    compliance_readiness: float


class ProductFamily(TypedDict, total=False):
    """Structure of a product family in the database."""
    family_id: str
    manufacturer: str
    product_name: str
    keywords: list[str]
    applications: list[str]
    scores: PriorityScore
    confidence: str
    not_for: list[str]
    placement_suitable_for: list[str]  # New: data-driven placement info


class RankedFamily(ProductFamily):
    """Product family with ranking results."""
    match_score: float
    matched: list[str]
    matched_keywords: list[str]
    matched_applications: list[str]
    priority_key: str
    reliable_match: bool
    match_details: dict  # Transparency into scoring


@dataclass
class RankingWeights:
    """Scoring weights for ranking algorithm."""
    keyword_multiplier: float = 4.0
    application_multiplier: float = 3.0
    priority_multiplier: float = 1.5
    not_for_penalty: float = 4.0
    recommendation_blocked_penalty: float = 6.0
    placement_boost_additive: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> RankingWeights:
        """Create from config dict."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class MatchingConfig:
    """Configuration for matching algorithm."""
    fuzzy_word_threshold: float = 0.8
    no_reliable_match_score: float = 1.5
    min_fuzzy_match_length: int = 5
    singularisation_exceptions: set = field(default_factory=set)
    synonyms: dict = field(default_factory=dict)
    use_hybrid_ranking: bool = False
    ranking_weights: RankingWeights = field(default_factory=RankingWeights)
    placement_boosts: dict = field(default_factory=dict)
    recommendation_allowed_states: set = field(default_factory=lambda: {"approved", "pending_review"})
    recommendation_blocked_states: set = field(default_factory=lambda: {"blocked", "discontinued"})
    
    @classmethod
    def from_file(cls, path: Path) -> MatchingConfig:
        """Load config from JSON file with fallback to defaults."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            logger.info(f"✓ Loaded config from {path}")
            
            weights = RankingWeights.from_dict(data.get("ranking_weights", {}))
            
            return cls(
                fuzzy_word_threshold=data.get("fuzzy_word_threshold", 0.8),
                no_reliable_match_score=data.get("no_reliable_match_score", 1.5),
                min_fuzzy_match_length=data.get("min_fuzzy_match_length", 5),
                singularisation_exceptions=set(data.get("singularisation_exceptions", [])),
                synonyms=data.get("synonyms", {}),
                use_hybrid_ranking=data.get("use_hybrid_ranking", False),
                ranking_weights=weights,
                placement_boosts=data.get("placement_boosts", {}),
                recommendation_allowed_states=set(data.get("recommendation_allowed", [])),
                recommendation_blocked_states=set(data.get("recommendation_blocked", []))
            )
        except FileNotFoundError:
            logger.warning(f"⚠️  Config file not found at {path}. Using defaults.")
            return cls()
        except json.JSONDecodeError as e:
            logger.error(f"✗ Invalid JSON in {path}: {e}")
            raise ValueError(f"Invalid JSON in config file: {e}") from e
        except Exception as e:
            logger.error(f"✗ Error loading config: {e}", exc_info=True)
            raise


# ============================================================================
# PRIORITY TERMS DEFINITION
# ============================================================================

PRIORITY_TERMS = {
    Priority.ACOUSTIC_COMFORT.value: [
        "acoustic", "quiet", "noise", "noisy", "sound", "soundproof",
        "sound reduction", "acoustic comfort", "rw", "sound dampening"
    ],
    Priority.ENERGY_EFFICIENCY.value: [
        "energy", "thermal", "heat", "hot", "cold", "summer", "winter",
        "temperature", "condensation", "efficiency", "r-value", "r value",
        "thermal resistance", "heating", "cooling", "bills"
    ],
    Priority.SUSTAINABILITY.value: [
        "sustainable", "sustainability", "environment", "recycled", "low carbon",
        "eco", "ecological", "green", "natural", "biodegradable"
    ],
    Priority.INSTALLATION_PRACTICALITY.value: [
        "install", "easy", "access", "space", "thin", "practical", "retrofit",
        "diy", "simple", "quick", "minimal", "low cost"
    ],
    Priority.COMPLIANCE_READINESS.value: [
        "compliance", "ncc", "fire", "bal", "spec", "consultant", "certification",
        "evidence", "testing", "approved", "certified", "requirement"
    ],
}

PRIORITY_LABELS = {p.value: p.value.replace("_", " ").title() for p in Priority}


# ============================================================================
# CONFIGURATION LOADING
# ============================================================================

def _load_matching_config() -> MatchingConfig:
    """Load matching config from file with fallback to defaults."""
    config_path = Path(__file__).resolve().parent / "config" / "matching.json"
    return MatchingConfig.from_file(config_path)


MATCHING_CONFIG = _load_matching_config()


# ============================================================================
# TEXT NORMALIZATION
# ============================================================================

def canonical_text(value: str) -> str:
    """
    Convert text to canonical form for matching.
    
    - Lowercase
    - Normalize apostrophes
    - Apply synonym replacements (longest first to avoid partial matches)
    
    Args:
        value: Input text to normalize
        
    Returns:
        Canonical text suitable for matching
        
    Examples:
        >>> canonical_text("Acoustic Comfort")
        'acoustic comfort'
        >>> canonical_text("R-Value") with synonyms={"r-value": "thermal resistance"}
        'thermal resistance'
    """
    text = value.casefold().replace("'", "'")
    
    # Sort by length descending to avoid partial replacements
    for phrase, replacement in sorted(
        MATCHING_CONFIG.synonyms.items(),
        key=lambda item: len(item[0]),
        reverse=True
    ):
        text = text.replace(phrase, replacement)
    
    return text


def normalised_words(value: str) -> set[str]:
    """
    Extract and normalize words from text.
    
    - Extract alphanumeric sequences
    - Apply intelligent singularization (avoid false positives like "glass" -> "glas")
    - Remove duplicates
    
    Args:
        value: Input text to normalize
        
    Returns:
        Set of normalized words
        
    Examples:
        >>> normalised_words("Glass Batts and Sheets")
        {'glass', 'batt', 'sheet'}
        >>> normalised_words("Properties")
        {'propert'}  # propert, not properti (exception-aware)
    """
    text = canonical_text(value)
    words = re.findall(r"[a-z0-9]+", text)
    normalized = set()
    
    for word in words:
        # Apply intelligent singularization
        if len(word) > 3 and word.endswith("s") and word not in MATCHING_CONFIG.singularisation_exceptions:
            # Check if removing 's' creates a valid word-like string
            singular = word[:-1]
            # Heuristic: if it ends in common plural patterns, remove 's'
            normalized.add(singular)
        else:
            normalized.add(word)
    
    return normalized


def fuzzy_word_match(
    expected: str,
    actual_words: set[str],
    threshold: float | None = None,
    min_length: int | None = None
) -> bool:
    """
    Fuzzy match words using sequence similarity.
    
    Only matches words longer than min_length to avoid false positives
    on short strings (e.g., "is" ≈ "it").
    
    Args:
        expected: Word to match (singular form preferred)
        actual_words: Set of words from input text
        threshold: Similarity ratio (0.0-1.0). Defaults to config value.
        min_length: Only fuzzy-match words >= this length (default: config value)
        
    Returns:
        True if expected fuzzy-matches any actual word
        
    Examples:
        >>> fuzzy_word_match("insulate", {"insulated"}, threshold=0.85)
        True
        >>> fuzzy_word_match("s", {"is"}, min_length=3)
        False  # Too short
    """
    threshold = threshold or MATCHING_CONFIG.fuzzy_word_threshold
    min_length = min_length or MATCHING_CONFIG.min_fuzzy_match_length
    
    if len(expected) < min_length:
        return False
    
    for actual in actual_words:
        if len(actual) >= min_length:
            ratio = SequenceMatcher(None, expected, actual).ratio()
            if ratio >= threshold:
                logger.debug(f"Fuzzy match: '{expected}' ≈ '{actual}' (ratio: {ratio:.2f})")
                return True
    
    return False


def term_match_score(term: str, text: str, text_words: set[str]) -> float:
    """
    Score how well a term matches input text.
    
    Scoring levels (highest to lowest):
    1. Exact phrase match with word boundaries (1.0)
    2. All words from term present in text (0.95)
    3. All words match via substring or fuzzy match (0.65)
    4. No match (0.0)
    
    Args:
        term: Term to match (e.g., "acoustic comfort")
        text: Full canonical input text
        text_words: Normalized words extracted from text
        
    Returns:
        Match score from 0.0 to 1.0
        
    Examples:
        >>> # Exact phrase match
        >>> term_match_score("acoustic comfort", "I need acoustic comfort", {...})
        1.0
        >>> # Partial match
        >>> term_match_score("acoustic", "I need quiet rooms", {...})
        0.0
    """
    folded_term = canonical_text(term)
    
    # Level 1: Exact phrase match with word boundaries
    if folded_term and re.search(rf"(?:^|\W){re.escape(folded_term)}(?:\W|$)", text):
        return 1.0
    
    term_words = normalised_words(folded_term)
    
    # Level 2: All term words present in text
    if term_words and term_words.issubset(text_words):
        return 0.95
    
    # Level 3: All term words match via substring or fuzzy match
    if term_words and all(
        word in text_words or fuzzy_word_match(word, text_words)
        for word in term_words
    ):
        return 0.65
    
    # No match
    return 0.0


# ============================================================================
# PRIORITY DETECTION
# ============================================================================

def _extract_negations(text: str) -> set[str]:
    """Extract words that appear after negation markers."""
    negation_patterns = [
        r"(?:not|no|don't|don't|didn't|can't|won't)\s+([a-z0-9]+)",
        r"([a-z0-9]+)\s+(?:required|needed)",  # "energy not required"
    ]
    negated = set()
    for pattern in negation_patterns:
        matches = re.findall(pattern, canonical_text(text))
        negated.update(matches)
    return negated


def detected_priority(
    text: str,
    context: str = "",
    user_explicit_priority: str | None = None,
    default_priority: str = Priority.ENERGY_EFFICIENCY.value
) -> str:
    """
    Detect the user's primary priority from input text.
    
    Detection strategy:
    1. Use explicit user priority if provided
    2. Count priority term matches in main text (weighted 3x)
    3. Count priority term matches in context (weighted 1x)
    4. Apply negation handling (reduce score for negated terms)
    5. Return highest scoring priority, with tie-breaking via context
    6. Return default if no clear priority found
    
    Args:
        text: Main user input text (higher weight)
        context: Additional context (lower weight)
        user_explicit_priority: Override detection (e.g., from UI dropdown)
        default_priority: Fallback if no priority detected
        
    Returns:
        Priority key (e.g., "acoustic_comfort")
        
    Examples:
        >>> detected_priority("I need to reduce noise")
        'acoustic_comfort'
        >>> detected_priority(
        ...     "We need energy bills",
        ...     user_explicit_priority="acoustic_comfort"
        ... )
        'acoustic_comfort'  # Explicit wins
        >>> detected_priority("No energy concerns")
        'sustainability'  # Default, not energy_efficiency
    """
    # Explicit priority overrides detection
    if user_explicit_priority and user_explicit_priority in PRIORITY_TERMS:
        logger.debug(f"Using explicit priority: {user_explicit_priority}")
        return user_explicit_priority
    
    def score_source(source: str) -> dict[str, int]:
        """Count priority term hits in source, accounting for negations."""
        folded = canonical_text(source)
        negated = _extract_negations(source)
        
        scores = {}
        for priority_key, terms in PRIORITY_TERMS.items():
            hit_count = sum(
                term in folded
                for term in terms
                if term not in negated
            )
            scores[priority_key] = hit_count
        
        return scores
    
    # Score main text and context separately
    explicit_scores = score_source(text)
    contextual_scores = score_source(context)
    
    # Find highest score in explicit text
    explicit_max = max(explicit_scores.values(), default=0)
    
    if explicit_max == 0:
        logger.debug(f"No priority terms detected; using default: {default_priority}")
        return default_priority
    
    # Get all priorities with highest explicit score
    leaders = [
        key for key, score in explicit_scores.items()
        if score == explicit_max
    ]
    
    if len(leaders) == 1:
        logger.debug(f"Single priority leader: {leaders[0]} (score: {explicit_max})")
        return leaders[0]
    
    # Tie-breaking: combine explicit (3x) and contextual scores
    combined = {
        key: explicit_scores[key] * 3 + contextual_scores.get(key, 0)
        for key in leaders
    }
    
    best = max(combined, key=combined.get)
    logger.debug(f"Tie-breaker: {best} (combined score: {combined[best]})")
    
    return best


# ============================================================================
# PLACEMENT DETECTION AND ADJUSTMENT
# ============================================================================

class PlacementDetector:
    """Detect building placement from user text."""
    
    PLACEMENT_PATTERNS = {
        "ceiling": [
            "ceiling level", "ceiling space", "above the ceiling", "below the roof space",
            "ceiling cavity", "above ceiling", "ceiling installation"
        ],
        "roofline": [
            "roofline", "rafter", "truss", "under the roof", "beneath the roof",
            "roof space", "roof cavity", "attic", "loft"
        ],
        "subfloor": [
            "subfloor", "underfloor", "under the suspended", "suspended ground floor",
            "basement", "crawl space", "floor cavity", "joist"
        ],
        "between_floors": [
            "between floors", "between storeys", "midfloor", "inter-floor",
            "inside the cavity between", "floor-to-floor"
        ],
        "underlay": [
            "underlay", "beneath the floor finish", "under the carpet",
            "under laminate", "under vinyl", "under timber"
        ],
        "cavity": [
            "cavity wall", "wall cavity", "stud wall", "between studs",
            "cavity fill", "brick cavity"
        ]
    }
    
    @classmethod
    def detect(cls, text: str) -> set[str]:
        """
        Detect building placements from text.
        
        Args:
            text: User input text
            
        Returns:
            Set of detected placements (e.g., {"ceiling", "subfloor"})
        """
        text_lower = text.lower()
        detected = set()
        
        for placement, patterns in cls.PLACEMENT_PATTERNS.items():
            for pattern in patterns:
                if pattern in text_lower:
                    detected.add(placement)
                    logger.debug(f"Detected placement '{placement}' from pattern: '{pattern}'")
                    break
        
        return detected


def placement_adjustment(
    family_id: str,
    text: str,
    priority: str,
    placement_rules: dict | None = None
) -> float:
    """
    Calculate score boost based on product-placement fit.
    
    Data-driven approach:
    - Get placements detected in user text
    - Check which placements are suitable for this product
    - Apply boost if match found
    
    Args:
        family_id: Product family identifier
        text: User input text
        priority: Detected priority (determines boost amount)
        placement_rules: Config mapping family_id -> suitable placements
        
    Returns:
        Score boost amount (0 if no match)
        
    Examples:
        >>> placement_adjustment(
        ...     "FLETCHER_PINK_BATTS_CEILING",
        ...     "I need ceiling insulation",
        ...     "energy_efficiency",
        ...     placement_rules={"FLETCHER_PINK_BATTS_CEILING": ["ceiling"]}
        ... )
        12  # Energy boost for ceiling placement
    """
    placement_rules = placement_rules or MATCHING_CONFIG.placement_boosts
    
    if not placement_rules:
        logger.warning("No placement rules configured; returning 0 boost")
        return 0
    
    # Detect placements in text
    detected_placements = PlacementDetector.detect(text)
    
    if not detected_placements:
        return 0
    
    # Get suitable placements for this product
    product_placements = placement_rules.get(family_id, {})
    
    if not product_placements:
        return 0
    
    # Calculate boost based on matched placements
    boosts = []
    for placement in detected_placements:
        if placement in product_placements:
            # Get priority-specific boost amount
            boost_by_priority = product_placements.get(placement, {})
            boost = boost_by_priority.get(priority, 0)
            boosts.append(boost)
            logger.debug(
                f"Placement boost for {family_id}: +{boost} "
                f"(placement='{placement}', priority='{priority}')"
            )
    
    # Return highest boost (not cumulative, to avoid excessive scoring)
    return max(boosts) if boosts else 0


# ============================================================================
# RECOMMENDATION GATING
# ============================================================================

def recommendation_allowed(family: ProductFamily | None) -> bool:
    """
    Check if a product family is in an allowed state for recommendation.
    
    Args:
        family: Product family metadata, or None
        
    Returns:
        True if product can be recommended
    """
    if not family:
        logger.debug("Family is None; recommendation not allowed")
        return False
    
    confidence = family.get("confidence", "unknown")
    allowed = confidence in MATCHING_CONFIG.recommendation_allowed_states
    
    if not allowed:
        logger.debug(f"Family confidence state '{confidence}' not in allowed states")
    
    return allowed


# ============================================================================
# RANKING AND SCORING
# ============================================================================

def _lexical_rank_families(
    families: list[ProductFamily],
    answers: dict[str, str],
    manufacturer_scope: str | None = None
) -> list[RankedFamily]:
    """
    Rank product families using lexical matching.
    
    Scoring breakdown:
    - Keywords: 4.0x multiplier (most specific)
    - Applications: 3.0x multiplier (general use cases)
    - Priority match: 1.5x multiplier (priority alignment)
    - Placement boost: +N points (if placement matches priority)
    - Not-for penalty: -4.0 (if product explicitly unsuitable)
    - Blocked penalty: -6.0 (if product not yet approved)
    
    Args:
        families: List of product families to rank
        answers: User answers from questionnaire
        manufacturer_scope: Filter to specific manufacturer, or None for all
        
    Returns:
        Ranked list of families with scoring details
    """
    raw_text = " ".join(answers.values())
    text = canonical_text(raw_text)
    text_words = normalised_words(text)
    context = " ".join(v for k, v in answers.items() if k != "priority")
    
    # Detect priority (with user override if provided)
    user_priority = answers.get("priority", "")
    priority = detected_priority(text, context, user_priority or None)
    
    logger.info(f"Detected priority: {priority}")
    logger.debug(f"Input text ({len(text)} chars): {text[:100]}...")
    
    ranked = []
    weights = MATCHING_CONFIG.ranking_weights
    
    for family in families:
        # Manufacturer filtering
        if manufacturer_scope and manufacturer_scope != "Compare both":
            if family.get("manufacturer", "").casefold() != manufacturer_scope.casefold():
                continue
        
        family_id = family.get("family_id", "unknown")
        
        # Score keywords and applications
        keyword_scores = [
            (term, term_match_score(term, text, text_words))
            for term in family.get("keywords", [])
        ]
        application_scores = [
            (term, term_match_score(term, text, text_words))
            for term in family.get("applications", [])
        ]
        
        keyword_hits = [term for term, score in keyword_scores if score > 0]
        application_hits = [term for term, score in application_scores if score > 0]
        
        # Calculate match score
        match_score = (
            sum(score for _, score in keyword_scores) * weights.keyword_multiplier +
            sum(score for _, score in application_scores) * weights.application_multiplier +
            family.get("scores", {}).get(priority, 0) * weights.priority_multiplier +
            placement_adjustment(family_id, text, priority)
        )
        
        # Negative matching: penalize unsuitable products
        for term in family.get("not_for", []):
            if term_match_score(term, text, text_words) > 0:
                match_score -= weights.not_for_penalty
                logger.debug(f"{family_id}: -not_for penalty for '{term}'")
        
        # Penalize products not yet approved
        if not recommendation_allowed(family):
            match_score -= weights.recommendation_blocked_penalty
            logger.debug(f"{family_id}: -recommendation_blocked penalty")
        
        # Determine reliability of match
        reliable_match = bool(keyword_hits or application_hits) and match_score >= MATCHING_CONFIG.no_reliable_match_score
        
        # Build match details for transparency
        match_details = {
            "keyword_score": round(sum(s for _, s in keyword_scores), 3),
            "application_score": round(sum(s for _, s in application_scores), 3),
            "priority_score": round(family.get("scores", {}).get(priority, 0), 3),
            "placement_boost": round(placement_adjustment(family_id, text, priority), 3),
            "penalties": round(
                (sum(1 for _ in family.get("not_for", []) if term_match_score(_, text, text_words) > 0) * weights.not_for_penalty +
                 (weights.recommendation_blocked_penalty if not recommendation_allowed(family) else 0)),
                3
            )
        }
        
        ranked_family: RankedFamily = {
            **family,
            "match_score": round(match_score, 3),
            "matched": keyword_hits + application_hits,
            "matched_keywords": keyword_hits,
            "matched_applications": application_hits,
            "priority_key": priority,
            "reliable_match": reliable_match,
            "match_details": match_details,
        }
        
        ranked.append(ranked_family)
        
        logger.debug(
            f"{family_id}: score={ranked_family['match_score']}, "
            f"reliable={reliable_match}, matched={len(ranked_family['matched'])}"
        )
    
    # Sort by score (descending), then by priority score (descending)
    sorted_families = sorted(
        ranked,
        key=lambda item: (
            item["match_score"],
            item["scores"].get(priority, 0)
        ),
        reverse=True
    )
    
    logger.info(f"Ranked {len(sorted_families)} families (top: {sorted_families[0]['family_id'] if sorted_families else 'N/A'})")
    
    return sorted_families


def rank_families(
    families: list[ProductFamily],
    answers: dict[str, str],
    manufacturer_scope: str | None = None,
    force_lexical: bool = False
) -> list[RankedFamily]:
    """
    Rank product families using hybrid or lexical matching.
    
    Hybrid ranking (if enabled in config and --force_lexical is False):
    - Uses vector embeddings for semantic matching
    - Falls back to lexical ranking on error
    
    Lexical ranking (default or fallback):
    - Pure term-based matching with configurable weights
    - Deterministic and debuggable
    
    Args:
        families: List of product families to rank
        answers: User answers from questionnaire
        manufacturer_scope: Filter results to specific manufacturer
        force_lexical: Force lexical ranking (bypass hybrid)
        
    Returns:
        Ranked families with match scores and details
        
    Raises:
        ValueError: If input validation fails
    """
    # Input validation
    if not families:
        logger.warning("No families provided for ranking")
        return []
    
    if not answers or not answers.values():
        logger.warning("No answers provided; returning unranked families")
        return families
    
    # Try hybrid ranking if enabled
    use_hybrid = (
        MATCHING_CONFIG.use_hybrid_ranking and
        not force_lexical and
        not os.getenv("FORCE_LEXICAL", "").casefold() == "true"
    )
    
    if use_hybrid:
        try:
            logger.info("Attempting hybrid ranking...")
            from hybrid_retrieval import load_or_embed_cards, hybrid_rank
            
            cards_path = Path(__file__).resolve().parent / "data" / "processed" / "retrieval_cards.jsonl"
            
            if not cards_path.exists():
                logger.warning(f"Retrieval cards not found at {cards_path}; using lexical ranking")
                return _lexical_rank_families(families, answers, manufacturer_scope)
            
            with open(cards_path, encoding="utf-8") as f:
                cards = [json.loads(line) for line in f if line.strip()]
            
            logger.debug(f"Loaded {len(cards)} retrieval cards")
            embeddings, _ = load_or_embed_cards(cards, namespace="product_cards")
            
            # Combine all answers as enquiry text
            enquiry_text = " ".join(answers.values())
            
            def lexical_ranker(fams, ans, scope=None):
                return _lexical_rank_families(fams, ans, scope)
            
            logger.info("✓ Hybrid ranking successful")
            return hybrid_rank(enquiry_text, families, embeddings, lexical_ranker=lexical_ranker)
        
        except ImportError:
            logger.info("hybrid_retrieval module not available; using lexical ranking")
        except FileNotFoundError as e:
            logger.warning(f"Retrieval data not found ({e}); using lexical ranking")
        except Exception as e:
            logger.error(f"Hybrid ranking failed: {e}", exc_info=True)
    
    # Fall back to lexical ranking
    logger.info("Using lexical ranking")
    return _lexical_rank_families(families, answers, manufacturer_scope)


# ============================================================================
# GATING LOGIC
# ============================================================================

def technical_gate(answers: dict[str, str], family: ProductFamily | None) -> tuple[GatingDecision, str]:
    """
    Apply technical gating rules to determine if product can be recommended.
    
    Gating rules (in priority order):
    1. BLOCKED if no reliable product-family match found
    2. BLOCKED if product not in approved/pending-review state
    3. REVIEW REQUIRED if requirements mention compliance keywords
    4. REVIEW REQUIRED otherwise (safety check)
    
    Args:
        answers: User answers from questionnaire
        family: Selected product family (may be None)
        
    Returns:
        Tuple of (decision, reasoning_message)
        
    Examples:
        >>> # No match
        >>> technical_gate(answers, None)
        (GatingDecision.BLOCKED, "There is no reliable product-family match yet...")
        
        >>> # Compliance required
        >>> technical_gate({"requirements": "NCC compliance needed"}, family)
        (GatingDecision.REVIEW_REQUIRED, "The team needs to check the complete system...")
    """
    # Check for reliable match
    if family and not family.get("reliable_match", True):
        reason = (
            "There is no reliable product-family match yet. "
            "A person needs to review the enquiry."
        )
        logger.info(f"Gate: BLOCKED - {reason}")
        return GatingDecision.BLOCKED, reason
    
    # Check if product is approved
    if not recommendation_allowed(family):
        reason = (
            "We need to confirm the product identity and evidence "
            "before selecting or quoting it."
        )
        logger.info(f"Gate: BLOCKED - {reason}")
        return GatingDecision.BLOCKED, reason
    
    # Check for compliance/specification requirements
    requirements = answers.get("requirements", "").casefold()
    compliance_keywords = ["rw", "ncc", "fire", "bal", "bushfire", "consultant", "spec", "certifier", "asme", "iso"]
    
    if any(kw in requirements for kw in compliance_keywords):
        reason = (
            "The team needs to check the complete system "
            "against the stated requirement."
        )
        logger.info(f"Gate: REVIEW_REQUIRED - Compliance check needed")
        return GatingDecision.REVIEW_REQUIRED, reason
    
    # Default: require review for safety
    reason = (
        "The team will confirm the construction, exact product "
        "and availability before quoting."
    )
    logger.info(f"Gate: REVIEW_REQUIRED - Standard review")
    return GatingDecision.REVIEW_REQUIRED, reason


# ============================================================================
# PUBLIC API
# ============================================================================

def get_recommendations(
    families: list[ProductFamily],
    answers: dict[str, str],
    manufacturer_scope: str | None = None,
    top_n: int = 5,
    min_reliability: bool = False
) -> list[RankedFamily]:
    """
    Get top product recommendations for user answers.
    
    High-level API combining ranking and filtering.
    
    Args:
        families: All available product families
        answers: User answers from questionnaire
        manufacturer_scope: Filter to specific manufacturer
        top_n: Return top N recommendations
        min_reliability: Only return reliable matches
        
    Returns:
        Top N ranked families
    """
    ranked = rank_families(families, answers, manufacturer_scope)
    
    if min_reliability:
        ranked = [f for f in ranked if f.get("reliable_match", False)]
    
    return ranked[:top_n]


if __name__ == "__main__":
    logger.info("Insulation product recommendation engine v2 loaded successfully")
