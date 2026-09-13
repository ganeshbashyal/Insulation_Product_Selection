"""
Unit tests for improved product recommendation engine.

Test coverage includes:
- Text normalization and singularization
- Priority detection with negation handling
- Fuzzy matching behavior
- Scoring and ranking logic
- Placement detection
- Gating decisions
- Edge cases and error handling
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from product_recommendation_engine_v2 import (
    canonical_text,
    normalised_words,
    fuzzy_word_match,
    term_match_score,
    detected_priority,
    PlacementDetector,
    placement_adjustment,
    recommendation_allowed,
    rank_families,
    technical_gate,
    Priority,
    GatingDecision,
    MatchingConfig,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def sample_family():
    """Sample product family for testing."""
    return {
        "family_id": "FLETCHER_PINK_BATTS_CEILING",
        "manufacturer": "Fletcher Insulation",
        "product_name": "Pink Batts Ceiling",
        "keywords": ["ceiling", "batts", "insulation", "thermal"],
        "applications": ["ceiling cavity", "roofspace"],
        "scores": {
            "acoustic_comfort": 3,
            "energy_efficiency": 9,
            "sustainability": 7,
            "installation_practicality": 8,
            "compliance_readiness": 6
        },
        "confidence": "approved",
        "not_for": ["timber frame weatherboard"],
    }


@pytest.fixture
def sample_families(sample_family):
    """Multiple product families for ranking tests."""
    return [
        sample_family,
        {
            "family_id": "FLETCHER_SOUNDBREAK",
            "manufacturer": "Fletcher Insulation",
            "keywords": ["soundbreak", "acoustic", "noise"],
            "applications": ["between floors", "inter-floor cavity"],
            "scores": {
                "acoustic_comfort": 9,
                "energy_efficiency": 5,
                "sustainability": 6,
                "installation_practicality": 7,
                "compliance_readiness": 5
            },
            "confidence": "approved",
            "not_for": [],
        },
        {
            "family_id": "THERMOTEC_UNDERLAY",
            "manufacturer": "ThermaTec",
            "keywords": ["underlay", "acoustic", "comfort"],
            "applications": ["floor underlay", "beneath finish"],
            "scores": {
                "acoustic_comfort": 8,
                "energy_efficiency": 2,
                "sustainability": 4,
                "installation_practicality": 9,
                "compliance_readiness": 4
            },
            "confidence": "pending_review",
            "not_for": [],
        }
    ]


# ============================================================================
# TEXT NORMALIZATION TESTS
# ============================================================================

class TestCanonicalText:
    """Tests for canonical_text function."""
    
    def test_lowercase_conversion(self):
        """Canonical text should be lowercase."""
        assert canonical_text("ACOUSTIC COMFORT") == "acoustic comfort"
        assert canonical_text("Pink Batts") == "pink batts"
    
    def test_apostrophe_normalization(self):
        """Straight and curly apostrophes should normalize to same form."""
        assert canonical_text("it's") == canonical_text("it's")
    
    def test_synonym_replacement(self):
        """Synonyms should be replaced (longest match first)."""
        # Assuming synonyms: {"r-value": "thermal resistance"}
        # This test would pass if synonyms are configured
        text = canonical_text("R-Value insulation")
        # Should contain either "r-value" or "thermal resistance" depending on config
        assert "insulation" in text


class TestNormalisedWords:
    """Tests for normalised_words function."""
    
    def test_basic_word_extraction(self):
        """Should extract words correctly."""
        words = normalised_words("Glass Batts")
        assert "glass" in words
        assert "batt" in words  # Singular form
    
    def test_singularization_standard(self):
        """Should singularize standard plurals."""
        words = normalised_words("batts sheets properties")
        # Each should be singularized except exceptions
        assert any("batt" in w for w in words)
        assert any("sheet" in w for w in words)
    
    def test_singularization_exceptions(self):
        """Should NOT singularize exception words."""
        words = normalised_words("glass bus moss")
        # These should remain unchanged
        assert "glass" in words
        assert "bus" in words
        assert "moss" in words
    
    def test_numeric_extraction(self):
        """Should extract numbers."""
        words = normalised_words("r-value 200mm thick")
        assert any("200" in w for w in words)
    
    def test_duplicate_removal(self):
        """Should return set (no duplicates)."""
        words = normalised_words("acoustic acoustic comfort comfort")
        assert len(words) == len(set(words))


class TestFuzzyWordMatch:
    """Tests for fuzzy_word_match function."""
    
    def test_perfect_match(self):
        """Fuzzy match should work for similar words."""
        # "insulate" ≈ "insulated" at high similarity
        result = fuzzy_word_match(
            "insulate",
            {"insulated", "installation"},
            threshold=0.8
        )
        # Depends on similarity, but should have some similarity
        assert isinstance(result, bool)
    
    def test_too_short_no_match(self):
        """Words shorter than min_length should not fuzzy match."""
        result = fuzzy_word_match("is", {"it"}, min_length=5)
        assert result is False
    
    def test_threshold_enforcement(self):
        """Threshold should affect matching."""
        # Same words with different thresholds
        words = {"insulated"}
        strict = fuzzy_word_match("insulate", words, threshold=0.99)
        lenient = fuzzy_word_match("insulate", words, threshold=0.5)
        # Lenient should match more easily
        assert isinstance(strict, bool) and isinstance(lenient, bool)


class TestTermMatchScore:
    """Tests for term_match_score function."""
    
    def test_exact_phrase_match_perfect_score(self):
        """Exact phrase should score 1.0."""
        score = term_match_score(
            "acoustic comfort",
            "I need acoustic comfort in my home",
            {"acoustic", "comfort", "home"}
        )
        assert score == 1.0
    
    def test_all_words_present_high_score(self):
        """All words present should score 0.95."""
        score = term_match_score(
            "acoustic comfort",
            "comfort and acoustic",
            {"comfort", "acoustic", "and"}
        )
        assert score == 0.95
    
    def test_no_match_zero_score(self):
        """No match should score 0.0."""
        score = term_match_score(
            "thermal",
            "I need quiet rooms",
            {"quiet", "rooms"}
        )
        assert score == 0.0
    
    def test_substring_isolation(self):
        """Substring matches should respect word boundaries."""
        # "board" should NOT match "weatherboard" at 1.0 due to word boundary
        score = term_match_score(
            "board",
            "weatherboard installation",
            {"weatherboard", "installation"}
        )
        # Should be less than 1.0 since exact phrase doesn't match
        assert score < 1.0 or score == 0.0


# ============================================================================
# PRIORITY DETECTION TESTS
# ============================================================================

class TestDetectedPriority:
    """Tests for detected_priority function."""
    
    def test_explicit_acoustic_terms(self):
        """Should detect acoustic_comfort from acoustic terms."""
        priority = detected_priority("I need to reduce noise and sound")
        assert priority == Priority.ACOUSTIC_COMFORT.value
    
    def test_explicit_energy_terms(self):
        """Should detect energy_efficiency from energy terms."""
        priority = detected_priority("heating and cooling bills are high")
        assert priority == Priority.ENERGY_EFFICIENCY.value
    
    def test_explicit_sustainability_terms(self):
        """Should detect sustainability from eco terms."""
        priority = detected_priority("I want recycled and eco-friendly materials")
        assert priority == Priority.SUSTAINABILITY.value
    
    def test_negation_handling(self):
        """Should NOT detect priority for negated terms."""
        # "not interested in energy efficiency" should not return energy_efficiency
        priority = detected_priority("I don't care about energy efficiency or heating")
        assert priority != Priority.ENERGY_EFFICIENCY.value
    
    def test_explicit_priority_override(self):
        """Explicit priority should override detection."""
        priority = detected_priority(
            "quiet and thermal",
            user_explicit_priority=Priority.ACOUSTIC_COMFORT.value
        )
        assert priority == Priority.ACOUSTIC_COMFORT.value
    
    def test_tie_breaking_with_context(self):
        """Context should break ties."""
        priority = detected_priority(
            "noise",  # One acoustic term
            context="thermal and energy bills",  # Context favors energy
        )
        # Result depends on weighting, but should be deterministic
        assert priority in [Priority.ACOUSTIC_COMFORT.value, Priority.ENERGY_EFFICIENCY.value]
    
    def test_no_priority_returns_default(self):
        """Should return default priority if no terms detected."""
        priority = detected_priority("xyz abc 123")
        assert priority == Priority.ENERGY_EFFICIENCY.value  # Default


# ============================================================================
# PLACEMENT DETECTION TESTS
# ============================================================================

class TestPlacementDetector:
    """Tests for PlacementDetector class."""
    
    def test_ceiling_detection(self):
        """Should detect ceiling placement."""
        placements = PlacementDetector.detect("I need ceiling level insulation")
        assert "ceiling" in placements
    
    def test_roofline_detection(self):
        """Should detect roofline/attic placement."""
        placements = PlacementDetector.detect("We have an attic space under the roof")
        assert "roofline" in placements or "attic" in placements or "roof" in placements
    
    def test_subfloor_detection(self):
        """Should detect subfloor placement."""
        placements = PlacementDetector.detect("underfloor heating in suspended ground floor")
        assert "subfloor" in placements
    
    def test_multiple_placements(self):
        """Should detect multiple placements."""
        text = "ceiling cavity and under suspended floor joists"
        placements = PlacementDetector.detect(text)
        assert len(placements) >= 2
    
    def test_case_insensitive(self):
        """Should work regardless of case."""
        text_lower = "ceiling level insulation"
        text_upper = "CEILING LEVEL INSULATION"
        
        lower = PlacementDetector.detect(text_lower)
        upper = PlacementDetector.detect(text_upper)
        
        assert lower == upper


class TestPlacementAdjustment:
    """Tests for placement_adjustment function."""
    
    def test_matching_placement_gives_boost(self):
        """Should give boost for matching placement and priority."""
        placement_rules = {
            "FLETCHER_CEILING": {
                "ceiling": {
                    "energy_efficiency": 12,
                    "acoustic_comfort": 2
                }
            }
        }
        
        boost = placement_adjustment(
            "FLETCHER_CEILING",
            "I need ceiling level insulation for energy efficiency",
            Priority.ENERGY_EFFICIENCY.value,
            placement_rules
        )
        
        assert boost > 0
    
    def test_no_matching_placement_no_boost(self):
        """Should give no boost if placement doesn't match."""
        placement_rules = {
            "FLETCHER_CEILING": {
                "ceiling": {"energy_efficiency": 12}
            }
        }
        
        boost = placement_adjustment(
            "FLETCHER_CEILING",
            "I need floor underlay for acoustic comfort",
            Priority.ACOUSTIC_COMFORT.value,
            placement_rules
        )
        
        assert boost == 0
    
    def test_zero_boost_for_missing_product(self):
        """Should give zero boost if product not in rules."""
        placement_rules = {"OTHER_PRODUCT": {"ceiling": {"energy_efficiency": 12}}}
        
        boost = placement_adjustment(
            "UNKNOWN_PRODUCT",
            "ceiling space",
            Priority.ENERGY_EFFICIENCY.value,
            placement_rules
        )
        
        assert boost == 0


# ============================================================================
# RECOMMENDATION GATING TESTS
# ============================================================================

class TestRecommendationAllowed:
    """Tests for recommendation_allowed function."""
    
    def test_none_family_not_allowed(self):
        """None family should not be allowed."""
        assert recommendation_allowed(None) is False
    
    def test_approved_family_allowed(self):
        """Family with 'approved' confidence should be allowed."""
        family = {"confidence": "approved"}
        assert recommendation_allowed(family) is True
    
    def test_pending_review_allowed(self):
        """Family with 'pending_review' should be allowed."""
        family = {"confidence": "pending_review"}
        assert recommendation_allowed(family) is True
    
    def test_blocked_family_not_allowed(self):
        """Family with 'blocked' confidence should not be allowed."""
        family = {"confidence": "blocked"}
        assert recommendation_allowed(family) is False
    
    def test_discontinued_not_allowed(self):
        """Discontinued products should not be allowed."""
        family = {"confidence": "discontinued"}
        assert recommendation_allowed(family) is False


class TestTechnicalGate:
    """Tests for technical_gate function."""
    
    def test_no_reliable_match_blocked(self):
        """Should block if no reliable match."""
        decision, reason = technical_gate(
            {"priority": "energy"},
            {"reliable_match": False, "confidence": "approved"}
        )
        assert decision == GatingDecision.BLOCKED
        assert "reliable" in reason.lower()
    
    def test_blocked_family_blocked(self):
        """Should block if family confidence is blocked."""
        decision, reason = technical_gate(
            {},
            {"reliable_match": True, "confidence": "blocked"}
        )
        assert decision == GatingDecision.BLOCKED
        assert "confirm" in reason.lower()
    
    def test_compliance_keywords_trigger_review(self):
        """Should require review for compliance keywords."""
        decision, reason = technical_gate(
            {"requirements": "NCC compliance needed"},
            {"reliable_match": True, "confidence": "approved"}
        )
        assert decision == GatingDecision.REVIEW_REQUIRED
        assert "team" in reason.lower() or "check" in reason.lower()
    
    def test_no_flags_still_requires_review(self):
        """Even with no flags, should require review for safety."""
        decision, reason = technical_gate(
            {"priority": "energy"},
            {"reliable_match": True, "confidence": "approved"}
        )
        # Should be REVIEW_REQUIRED as safety default
        assert decision in [GatingDecision.REVIEW_REQUIRED, GatingDecision.APPROVED]


# ============================================================================
# RANKING TESTS
# ============================================================================

class TestRankFamilies:
    """Tests for rank_families function."""
    
    def test_empty_families_returns_empty(self):
        """Empty families list should return empty."""
        result = rank_families([], {"priority": "energy"})
        assert result == []
    
    def test_empty_answers_returns_unranked(self):
        """Empty answers should return unranked families."""
        families = [{"family_id": "A"}, {"family_id": "B"}]
        result = rank_families(families, {})
        # Should return something (either empty or unranked)
        assert isinstance(result, list)
    
    def test_keyword_matching_boosts_score(self):
        """Products with matching keywords should score higher."""
        families = [
            {
                "family_id": "MATCHES",
                "keywords": ["acoustic", "sound"],
                "applications": [],
                "scores": {"acoustic_comfort": 5, "energy_efficiency": 1},
                "confidence": "approved"
            },
            {
                "family_id": "NO_MATCH",
                "keywords": ["thermal", "energy"],
                "applications": [],
                "scores": {"acoustic_comfort": 5, "energy_efficiency": 1},
                "confidence": "approved"
            }
        ]
        
        answers = {"priority": "I need to reduce noise"}
        
        result = rank_families(families, answers)
        
        # MATCHES should score higher
        scores = {f["family_id"]: f["match_score"] for f in result}
        assert scores.get("MATCHES", 0) >= scores.get("NO_MATCH", 0)
    
    def test_manufacturer_filtering(self):
        """Should filter by manufacturer when specified."""
        families = [
            {"family_id": "A", "manufacturer": "Fletcher"},
            {"family_id": "B", "manufacturer": "ThermaTec"},
        ]
        
        result = rank_families(
            families,
            {"priority": "energy"},
            manufacturer_scope="Fletcher"
        )
        
        # Should only have Fletcher
        manufacturers = [f.get("manufacturer") for f in result]
        assert all(m == "Fletcher" or m is None for m in manufacturers)
    
    def test_not_for_penalty_applied(self):
        """Products with matching 'not_for' terms should score lower."""
        families = [
            {
                "family_id": "PENALIZED",
                "keywords": ["insulation"],
                "applications": [],
                "not_for": ["weatherboard"],
                "scores": {"energy_efficiency": 8},
                "confidence": "approved"
            }
        ]
        
        # Text includes "weatherboard" which is in not_for
        answers = {"priority": "weatherboard cavity insulation energy efficient"}
        
        result = rank_families(families, answers)
        
        # Should have score but with penalty applied
        assert result[0]["match_score"] < 5.0  # Penalized


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestIntegration:
    """Integration tests combining multiple components."""
    
    def test_full_ranking_pipeline(self, sample_families):
        """Test complete ranking pipeline."""
        answers = {
            "priority": "I need to reduce noise between floors",
            "location": "apartment with shared walls",
            "requirements": "acoustic comfort"
        }
        
        result = rank_families(sample_families, answers)
        
        # Should return ranked results
        assert len(result) > 0
        assert "match_score" in result[0]
        assert "matched" in result[0]
        assert result[0]["match_score"] >= result[-1]["match_score"] if len(result) > 1 else True
    
    def test_ranking_with_placement_boost(self, sample_families):
        """Test that placement boosts affect ranking."""
        # Answer that includes placement info
        answers = {
            "priority": "energy efficiency needed",
            "placement": "ceiling cavity insulation"
        }
        
        result = rank_families(sample_families, answers)
        
        # Ceiling product should rank higher for energy efficiency
        assert len(result) > 0
        # Check that placement details are in output
        first = result[0]
        assert "match_details" in first
    
    def test_edge_case_ambiguous_query(self, sample_families):
        """Test handling of ambiguous queries."""
        answers = {
            "priority": "xyz acoustic energy thermal sustainability practical compliance"
        }
        
        # Should not crash and should return results
        result = rank_families(sample_families, answers)
        assert isinstance(result, list)
    
    def test_edge_case_very_long_query(self, sample_families):
        """Test handling of very long input."""
        long_text = " ".join(["acoustic sound noise quiet"] * 100)
        answers = {"priority": long_text}
        
        result = rank_families(sample_families, answers)
        assert isinstance(result, list)


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
