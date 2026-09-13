# Migration Guide: v1 → v2 Recommendation Engine

**Status:** Ready for Implementation  
**Risk Level:** Medium (new features, some breaking changes)  
**Rollback Plan:** Keep v1 running in parallel for 1-2 weeks

---

## Quick Start

### 1. Install Dependencies
```bash
# New dependencies
pip install nltk  # For lemmatization (optional, currently commented out)
pip install pytest  # For running tests

# No new core dependencies, v2 uses stdlib + existing imports
```

### 2. Replace Configuration
```bash
# Backup old config
cp config/matching.json config/matching_v1.json

# Use new config
cp matching_config_v2.json config/matching.json
```

### 3. Deploy New Engine
```bash
# Backup old code
cp product_recommendation.py product_recommendation_v1.py

# Deploy new code
cp product_recommendation_engine_v2.py product_recommendation.py
```

### 4. Test Thoroughly
```bash
# Run test suite
python -m pytest test_recommendation_engine_v2.py -v

# Run on sample data
python test_sample_ranking.py
```

### 5. Canary Deployment (10% traffic)
```python
# In your Streamlit app
import os
from product_recommendation_engine_v2 import rank_families

# Assign 10% of users to v2
use_v2 = (hash(session_id) % 100) < 10

if use_v2:
    ranked = rank_families(families, answers)  # v2
else:
    ranked = old_rank_families(families, answers)  # v1
```

---

## Breaking Changes

### 1. Import Path Changed
**Before:**
```python
from product_recommendation import (
    canonical_text,
    normalised_words,
    rank_families,
    technical_gate,
)
```

**After:**
```python
from product_recommendation_engine_v2 import (
    canonical_text,
    normalised_words,
    rank_families,
    technical_gate,
    Priority,  # NEW: Enum
    GatingDecision,  # NEW: Enum
    PlacementDetector,  # NEW: Class
)
```

### 2. Return Type of `rank_families()`
**Before:**
```python
families: list[dict]  # Plain dicts

# Accessing:
score = families[0]["match_score"]
```

**After:**
```python
families: list[RankedFamily]  # TypedDict with more fields

# Same access works, but now you have:
families[0]["match_details"]  # NEW: Scoring breakdown
families[0]["priority_key"]  # Always set
families[0]["reliable_match"]  # Boolean flag
```

**Migration:**
```python
# Old code still works! TypedDict is dict-compatible
result = rank_families(families, answers)

# But you can now access new fields for transparency
if result:
    print(result[0]["match_details"])  # NEW
    print(result[0]["reliable_match"])  # NEW
```

### 3. `technical_gate()` Return Type Changed
**Before:**
```python
decision, reason = technical_gate(answers, family)
# decision: "BLOCKED" | "REVIEW REQUIRED"
# reason: str
```

**After:**
```python
decision, reason = technical_gate(answers, family)
# decision: GatingDecision.BLOCKED | GatingDecision.REVIEW_REQUIRED
# reason: str
```

**Migration:**
```python
# Backward compatible: GatingDecision is a string enum
decision, reason = technical_gate(answers, family)

if decision == "BLOCKED":  # Still works
    pass

if decision == GatingDecision.BLOCKED:  # Also works
    pass

if decision.value == "BLOCKED":  # Also works
    pass
```

### 4. Configuration Structure Enhanced
**Before:**
```json
{
  "fuzzy_word_threshold": 0.8,
  "no_reliable_match_score": 1.5,
  "synonyms": {...}
}
```

**After:**
```json
{
  "fuzzy_word_threshold": 0.8,
  "no_reliable_match_score": 1.5,
  "min_fuzzy_match_length": 5,
  "ranking_weights": {
    "keyword_multiplier": 4.0,
    "application_multiplier": 3.0,
    ...
  },
  "placement_boosts": {
    "FLETCHER_PINK_BATTS_CEILING": {...}
  }
}
```

**Migration:**
```python
# v2 loads old config, but uses sensible defaults for new fields
# No config migration needed, but recommended:

# Load old config
old_config = json.load(open("matching.json"))

# Use new template, fill in old values
new_config = {
    "fuzzy_word_threshold": old_config.get("fuzzy_word_threshold", 0.8),
    ...
    "ranking_weights": {
        "keyword_multiplier": 4.0,  # Use default
        "application_multiplier": 3.0,
        ...
    }
}

json.dump(new_config, open("matching.json", "w"))
```

### 5. `placement_adjustment()` Signature Changed
**Before:**
```python
def placement_adjustment(family_id: str, text: str, priority: str) -> float:
    # Hardcoded product names inside function
    # No config option
```

**After:**
```python
def placement_adjustment(
    family_id: str,
    text: str,
    priority: str,
    placement_rules: dict | None = None  # NEW parameter
) -> float:
    # placement_rules from config
    # Can override for testing
```

**Migration:**
```python
# Old code: placement_adjustment("FLETCHER_PINK_BATTS_CEILING", text, priority)
# Still works! New parameter is optional with default from config

# New code can pass config:
result = placement_adjustment(family_id, text, priority, placement_rules=config)
```

### 6. New Dependency on Logging Module
**Before:**
- Silent failures with no logging
- Exception handling without visibility

**After:**
- Structured logging to file
- Warnings and errors logged
- Debug output available with `LOG_LEVEL=DEBUG`

**Migration:**
```python
# No code changes needed
# Logs appear in:
logs/recommendations_2026-09-01.jsonl
logs/errors_2026-09-01.jsonl

# To see debug output:
export LOG_LEVEL=DEBUG
python app.py
```

---

## Non-Breaking Changes (New Features)

### 1. New Priority Class
```python
from product_recommendation_engine_v2 import Priority

priority = Priority.ACOUSTIC_COMFORT.value  # "acoustic_comfort"

# Provides type safety:
for p in Priority:
    print(p.value)  # acoustic_comfort, energy_efficiency, ...
```

### 2. New GatingDecision Enum
```python
from product_recommendation_engine_v2 import GatingDecision

decision, reason = technical_gate(answers, family)

if decision == GatingDecision.APPROVED:
    # Recommend with confidence
    pass
elif decision == GatingDecision.REVIEW_REQUIRED:
    # Require expert review before quoting
    pass
elif decision == GatingDecision.BLOCKED:
    # Do not recommend
    pass
```

### 3. New PlacementDetector Class
```python
from product_recommendation_engine_v2 import PlacementDetector

placements = PlacementDetector.detect("I need ceiling cavity insulation")
# Returns: {"ceiling"}

placements = PlacementDetector.detect("ceiling and between floors")
# Returns: {"ceiling", "between_floors"}
```

### 4. New MatchingConfig Class
```python
from product_recommendation_engine_v2 import MatchingConfig

# Load from file with defaults fallback
config = MatchingConfig.from_file(Path("config/matching.json"))

# Access config safely
print(config.fuzzy_word_threshold)
print(config.ranking_weights.keyword_multiplier)
```

### 5. New RankingWeights Dataclass
```python
from product_recommendation_engine_v2 import RankingWeights

weights = config.ranking_weights
print(f"Keywords: {weights.keyword_multiplier}x")
print(f"Applications: {weights.application_multiplier}x")

# Easy to modify for testing
test_weights = RankingWeights(keyword_multiplier=5.0)
```

### 6. Enhanced Logging
```python
import logging
import os

# Set log level
os.environ["LOG_LEVEL"] = "DEBUG"

# Get logger
logger = logging.getLogger("product_recommendation_engine_v2")

# Logs now include:
# - Exact matching scores
# - Priority detection reasoning
# - Placement boost details
# - Errors with full tracebacks
```

### 7. Match Details Transparency
```python
ranked = rank_families(families, answers)

for product in ranked:
    print(f"\n{product['product_name']}")
    print(f"Total Score: {product['match_score']:.2f}")
    
    # NEW: Scoring breakdown
    details = product['match_details']
    print(f"  Keywords: {details['keyword_score']:.2f}")
    print(f"  Applications: {details['application_score']:.2f}")
    print(f"  Priority: {details['priority_score']:.2f}")
    print(f"  Placement Bonus: +{details['placement_boost']:.2f}")
    print(f"  Penalties: -{details['penalties']:.2f}")
    
    # Useful for debugging why a product ranked high/low
```

---

## Testing Your Migration

### 1. Unit Tests
```bash
# Run all tests
pytest test_recommendation_engine_v2.py -v

# Run specific test class
pytest test_recommendation_engine_v2.py::TestCanonicalText -v

# Run with coverage
pytest test_recommendation_engine_v2.py --cov=product_recommendation_engine_v2
```

### 2. Regression Tests
Compare v1 and v2 on sample data:
```python
# test_regression.py
import json
from pathlib import Path
from product_recommendation_v1 import rank_families as rank_v1
from product_recommendation_engine_v2 import rank_families as rank_v2

def test_regression():
    # Load test data
    families = json.load(open("test_data/families.json"))
    answers = json.load(open("test_data/sample_queries.json"))
    
    for i, answer in enumerate(answers):
        result_v1 = rank_v1(families, answer)
        result_v2 = rank_v2(families, answer)
        
        # Top product should be same (or very close)
        top_v1 = result_v1[0]["family_id"]
        top_v2 = result_v2[0]["family_id"]
        
        if top_v1 != top_v2:
            print(f"Query {i}: Different top product!")
            print(f"  v1: {top_v1} (score: {result_v1[0]['match_score']})")
            print(f"  v2: {top_v2} (score: {result_v2[0]['match_score']})")
            # Investigate why they differ
```

### 3. Performance Tests
```python
import time

def benchmark_ranking():
    families = load_large_family_set()  # 1000+ families
    answers = load_benchmark_queries()  # 100 queries
    
    start = time.time()
    for answer in answers:
        rank_families(families, answer)
    elapsed = time.time() - start
    
    avg_per_query = 1000 * elapsed / len(answers)
    print(f"Average: {avg_per_query:.1f}ms per query")
    
    # Target: <500ms (p95 < 1000ms)
    assert avg_per_query < 1000, f"Too slow: {avg_per_query}ms"
```

### 4. End-to-End Tests in Streamlit
```python
# In your Streamlit app, add test mode:

import streamlit as st

if st.secrets.get("TEST_MODE"):
    st.write("🧪 Test Mode Enabled")
    
    # Load test data
    test_families = load_test_families()
    test_query = st.text_input("Test query:", value="I need quiet acoustic insulation ceiling")
    
    if test_query:
        result = rank_families(test_families, {"priority": test_query})
        
        st.write(f"**Top Result:** {result[0]['product_name']}")
        st.write(f"**Score:** {result[0]['match_score']:.2f}")
        
        st.json(result[0]['match_details'])
```

---

## Rollback Plan

If v2 causes issues:

### Option 1: Immediate Rollback
```bash
# Revert to v1
cp product_recommendation_v1.py product_recommendation.py
cp config/matching_v1.json config/matching.json

# Restart app
python -m streamlit run app.py
```

### Option 2: A/B Test Fallback
```python
# If v2 has errors, fall back to v1
try:
    from product_recommendation_engine_v2 import rank_families as rank_v2
    result = rank_v2(families, answers)
except Exception as e:
    logger.error(f"v2 failed: {e}, falling back to v1")
    from product_recommendation_v1 import rank_families as rank_v1
    result = rank_v1(families, answers)
```

### Option 3: Gradual Rollout
```python
# Start at 5% of users
use_v2 = (hash(session_id) % 100) < 5

# Monitor error rates, satisfaction, etc.
# If good, increase to 25%, 50%, 100%
```

---

## Checklist for Deployment

- [ ] Run full test suite: `pytest test_recommendation_engine_v2.py -v`
- [ ] Test with your actual product catalog
- [ ] Compare results with v1 on sample queries
- [ ] Set `LOG_LEVEL=DEBUG` and review logs
- [ ] Deploy to staging environment
- [ ] Run load tests (100+ concurrent users)
- [ ] Get product team sign-off on results
- [ ] Set up monitoring and alerting
- [ ] Deploy with canary (5-10% traffic first)
- [ ] Monitor for 24-48 hours
- [ ] If stable, roll out to 100%
- [ ] Keep v1 available for 1-2 weeks for quick rollback

---

## Support & Troubleshooting

### Issue: ConfigFileNotFoundError
**Cause:** Configuration file not found
**Solution:**
```bash
cp matching_config_v2.json config/matching.json
# OR set env var:
export CONFIG_PATH=/path/to/matching.json
```

### Issue: SyntaxError with Type Hints
**Cause:** Python < 3.10 (doesn't support `str | None` syntax)
**Solution:**
```python
# Use typing.Optional instead
from typing import Optional

def my_func(x: Optional[str]) -> Optional[int]:
    pass

# OR upgrade to Python 3.10+
python --version  # Should be 3.10+
```

### Issue: Slower Response Times
**Cause:** Additional logging/transparency calculations
**Solution:**
```python
# Disable debug logging in production
os.environ["LOG_LEVEL"] = "WARNING"

# Profile the code
python -m cProfile -s cumulative app.py
```

### Issue: Different Ranking Results
**Cause:** Improved algorithm (feature, not bug!)
**Solution:**
```python
# This is expected - v2 has better text matching
# Review results with product team
# Adjust PRIORITY_TERMS or ranking_weights if needed

# Compare v1 vs v2 on same query
from product_recommendation_v1 import rank_families as rank_v1
from product_recommendation_engine_v2 import rank_families as rank_v2

v1_result = rank_v1(families, answers)
v2_result = rank_v2(families, answers)

print(f"v1 top: {v1_result[0]['family_id']} ({v1_result[0]['match_score']})")
print(f"v2 top: {v2_result[0]['family_id']} ({v2_result[0]['match_score']})")
```

---

## Performance Optimization Tips

### 1. Cache Config Loading
```python
from functools import lru_cache

@lru_cache(maxsize=1)
def get_matching_config():
    return MatchingConfig.from_file(CONFIG_PATH)

# Load once, reuse many times
config = get_matching_config()
```

### 2. Pre-compile Regex
```python
import re

# Instead of creating regex each time:
# pattern = re.search(rf"\b{re.escape(term)}\b", text)

# Pre-compile:
PLACEMENT_PATTERNS = {
    "ceiling": re.compile(r"ceiling|attic|loft", re.IGNORECASE),
    "roofline": re.compile(r"roof|rafter|truss", re.IGNORECASE),
}

# Use: PLACEMENT_PATTERNS["ceiling"].search(text)
```

### 3. Batch Processing
```python
# If ranking 1000+ products:
families_batch_1 = families[:500]
families_batch_2 = families[500:]

result_1 = rank_families(families_batch_1, answers)
result_2 = rank_families(families_batch_2, answers)

all_results = sorted(result_1 + result_2, key=lambda x: x['match_score'], reverse=True)
```

### 4. Use Hybrid Ranking for Large Catalogs
```python
# If > 500 products, enable hybrid ranking
# It's faster than lexical on large sets due to embedding pre-computation

config.use_hybrid_ranking = True
```

---

## Questions?

- **Bug Reports:** Create issue with logs and sample query
- **Performance Issues:** Run profiler (`cProfile`)
- **Ranking Issues:** Check `match_details` for scoring breakdown
- **Config Problems:** Check `CONFIG_PATH` and JSON syntax

---

**Deployment Date Target:** September 2026  
**Support Period:** 2 weeks after rollout
