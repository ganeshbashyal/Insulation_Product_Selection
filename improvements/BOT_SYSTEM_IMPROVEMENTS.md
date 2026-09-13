# Insulation Product Selection Bot - System Improvement Roadmap

**Date:** September 2026  
**Status:** Comprehensive Recommendations  
**Priority:** Phase-based implementation guide

---

## Executive Summary

The improved recommendation engine (v2) fixes critical issues in text matching, configuration management, and observability. However, the engine is only one component of a larger system. This document outlines improvements across:

1. **Data Architecture** – Product catalogs, embeddings, versioning
2. **Bot Logic** – Question flow, branching, context preservation
3. **User Experience** – UI/UX, feedback mechanisms, transparency
4. **Operations** – Monitoring, A/B testing, continuous improvement
5. **Compliance & Safety** – Audit trails, expert review workflows

---

## 1. DATA ARCHITECTURE IMPROVEMENTS

### 1.1 Product Catalog Structure

**Current Problem:**
- Product data likely stored in flat JSON/CSV
- No versioning of product specifications
- No tracking of when product confidence changed
- Hard to backfill historical product information

**Recommended Solution:**

```
/data/
  /products/
    /v1/  (versioned snapshots)
      catalog.json
      product_metadata.jsonl
      placement_suitability.json
      performance_scores.json
    /v2/
      ...
  /archives/
    /deprecated/
      old_products.json
      discontinuation_log.csv
  /validation/
    product_schema.json
    rules.yaml
```

**Benefits:**
- ✅ Can revert if data is corrupted
- ✅ Track product changes over time
- ✅ Audit trail for compliance
- ✅ A/B test different product datasets

**Implementation:** 1-2 days
- Create versioning system
- Set up data validation pipeline
- Document product data schema

---

### 1.2 Product Family Enrichment

**Add these fields to each product family:**

```python
{
  # Core (existing)
  "family_id": "FLETCHER_PINK_BATTS_CEILING",
  "manufacturer": "Fletcher Insulation",
  "keywords": [...],
  "applications": [...],
  
  # NEW: Metadata
  "created_date": "2023-01-15",
  "last_updated": "2026-09-01",
  "confidence": "approved",
  "confidence_last_reviewed": "2026-09-01",
  "confidence_reviewer": "technical_team@insulation.com",
  
  # NEW: Performance benchmarks
  "typical_r_value": 2.5,
  "typical_rw_rating": 55,
  "cost_per_sqm": 45.50,
  "installation_time_per_sqm_hours": 0.25,
  
  # NEW: Constraints & conditions
  "requires_vapor_barrier": true,
  "fire_rating": "BAL-40",
  "environmental_poa": ["australian_made"],
  "minimum_order_quantity": 10,
  "lead_time_days": 5,
  
  # NEW: Related products (cross-sells/upsells)
  "complements": ["FLETCHER_BARRIER_20", "ACOUSTIC_TAPE_500"],
  "alternatives": ["KNAUF_EARTHWOOL"],
  
  # NEW: Customer segments
  "best_for_segments": ["diy", "contractor", "commercial"],
  
  # NEW: Recent customer feedback
  "rating": 4.2,
  "review_count": 42,
  "common_issues": ["installation_difficulty", "dust_handling"]
}
```

**Benefits:**
- ✅ Enables cost-aware recommendations ("budget conscious")
- ✅ Tracks product life cycle
- ✅ Enables segment-specific recommendations
- ✅ Surfaces common issues early
- ✅ Compliance: audit trail of who approved what when

**Implementation:** 2-3 days
- Extend product schema
- Migrate existing data
- Build data validation

---

### 1.3 Semantic Vector Storage (For Hybrid Ranking)

**Current Problem:**
- Hybrid ranking references "hybrid_retrieval" module but no guidance on setup
- Unclear where embeddings live, who computes them, update frequency

**Recommended Architecture:**

```
/embeddings/
  /v1/
    cards_sentences.jsonl       # Original texts
    cards_embeddings.bin        # Binary embeddings (one per line)
    metadata.json               # Embedding config:
                                # - model: "sentence-transformers/all-mpnet-base-v2"
                                # - date_created: "2026-09-01"
                                # - row_count: 1024
                                # - vector_dim: 768
    similarity_index.faiss      # FAISS index for fast search

/models/
  /embeddings/
    all-mpnet-base-v2/          # Downloaded model
    all-MiniLM-L6-v2/           # Smaller alternative
```

**Setup Process:**

```bash
# 1. Generate embeddings from product cards
python generate_embeddings.py \
  --input data/v1/product_metadata.jsonl \
  --model sentence-transformers/all-mpnet-base-v2 \
  --output embeddings/v1/ \
  --batch-size 32

# 2. Build FAISS index for fast similarity search
python build_faiss_index.py \
  --embeddings embeddings/v1/cards_embeddings.bin \
  --output embeddings/v1/similarity_index.faiss

# 3. Test retrieval
python test_retrieval.py \
  --query "I need acoustic comfort between floors" \
  --top-k 5
```

**Benefits:**
- ✅ Enables semantic matching ("soundproof" ≈ "noise reduction")
- ✅ Captures user intent beyond keywords
- ✅ Faster than lexical matching on large catalogs
- ✅ Can swap models/re-embed without code changes

**Implementation:** 3-5 days
- Set up embedding pipeline
- Generate and store embeddings
- Create retrieval service wrapper

---

## 2. BOT LOGIC & QUESTIONNAIRE IMPROVEMENTS

### 2.1 Structured Question Flow with Context

**Current Problem:**
- Unclear how questions are asked
- No context preservation between Q&A pairs
- No branching logic (ask different Q's based on answers)

**Recommended Structure:**

```python
from enum import Enum
from dataclasses import dataclass
from typing import Callable

class QuestionType(Enum):
    SINGLE_CHOICE = "single_choice"      # Radio buttons
    MULTIPLE_CHOICE = "multiple_choice"  # Checkboxes
    FREE_TEXT = "free_text"              # Text input
    SLIDER = "slider"                     # 1-10 scale
    BUTTON_ARRAY = "button_array"         # Quick answers

@dataclass
class Question:
    """Structured question for user questionnaire."""
    id: str
    type: QuestionType
    text: str
    description: str = ""
    
    # For single/multiple choice
    options: list[str] = None
    
    # Validation
    required: bool = True
    min_selection: int = 1
    max_selection: int = None
    
    # Conditional display
    condition: Callable[[dict], bool] = None  # Display if func(answers) == True
    
    # Recommendations for UI
    ui_hint: str = None  # "wide", "compact", "inline"
    help_text: str = None
    example: str = None

# Example questions
QUESTIONS = [
    Question(
        id="priority",
        type=QuestionType.BUTTON_ARRAY,
        text="What's most important to you?",
        options=[
            "🔇 Reduce noise",
            "🌡️ Save on heating/cooling",
            "♻️ Eco-friendly materials",
            "🔨 Easy to install",
            "📋 Building compliance"
        ],
        description="Select the top priority for your project"
    ),
    
    Question(
        id="location",
        type=QuestionType.SINGLE_CHOICE,
        text="Where do you need insulation?",
        options=[
            "Ceiling/roof space",
            "Walls (cavity)",
            "Under suspended floor",
            "Between floors",
            "Under floor finishes"
        ],
        condition=lambda ans: ans.get("priority") is not None
    ),
    
    Question(
        id="r_value_preference",
        type=QuestionType.SLIDER,
        text="How much thermal resistance (R-value)?",
        description="1 (minimal) → 10 (maximum insulation)",
        condition=lambda ans: "thermal" in ans.get("priority", "").lower()
    ),
    
    Question(
        id="budget_range",
        type=QuestionType.SINGLE_CHOICE,
        text="Budget per square meter?",
        options=["<$30", "$30-60", "$60-100", "$100+", "No budget constraint"],
        ui_hint="compact"
    ),
    
    Question(
        id="special_requirements",
        type=QuestionType.FREE_TEXT,
        text="Any special requirements? (optional)",
        required=False,
        placeholder="e.g., 'NCC compliance needed', 'must be thin', 'fire-rated'"
    )
]
```

**Flow Logic:**

```python
class QuestionnaireFlow:
    """Manage question flow with conditional logic."""
    
    def __init__(self, questions: list[Question]):
        self.questions = questions
        self.answers = {}
    
    def get_next_question(self) -> Question | None:
        """Get next question to display."""
        for q in self.questions:
            if q.id not in self.answers:
                # Check if condition is met
                if q.condition and not q.condition(self.answers):
                    continue  # Skip this question
                return q
        return None  # All questions answered
    
    def answer_question(self, question_id: str, answer: str | list):
        """Record answer and validate."""
        self.answers[question_id] = answer
    
    def progress_percentage(self) -> int:
        """Show progress bar."""
        visible_qs = [q for q in self.questions if q.condition is None or q.condition(self.answers)]
        answered = sum(1 for q in visible_qs if q.id in self.answers)
        return int(100 * answered / len(visible_qs)) if visible_qs else 0
```

**Benefits:**
- ✅ Better UX: only ask relevant questions
- ✅ More data: follow-up questions drill deeper
- ✅ Clearer flow: users know what to expect
- ✅ A/B testable: swap questions, track outcomes

**Implementation:** 2-3 days
- Define question schema
- Implement flow logic
- Update Streamlit UI to use flow

---

### 2.2 Multi-Turn Context Preservation

**Current Problem:**
- If user says "I need quiet acoustic insulation for ceiling spaces," all context is lost after ranking
- User can't easily modify just one aspect ("actually, budget is tight")
- No conversation memory

**Recommended Solution:**

```python
from dataclasses import dataclass, asdict
from datetime import datetime

@dataclass
class ConversationTurn:
    """Single turn in conversation."""
    turn_id: int
    timestamp: datetime
    user_input: str
    system_response: str
    recommended_products: list[dict]
    user_feedback: str = None  # "helpful", "not helpful", "dislike"

class ConversationMemory:
    """Preserve conversation history and allow refinement."""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.turns: list[ConversationTurn] = []
        self.initial_answers: dict = {}
    
    def add_turn(self, user_input: str, products: list[dict]):
        """Record new turn."""
        turn = ConversationTurn(
            turn_id=len(self.turns),
            timestamp=datetime.now(),
            user_input=user_input,
            system_response=...,
            recommended_products=products
        )
        self.turns.append(turn)
    
    def refine_search(self, refinement: str):
        """Allow user to refine without starting over.
        
        Examples:
        - "show me cheaper options" → adjust budget
        - "need faster installation" → boost practicality score
        - "acoustic is more important now" → reweight priority
        """
        # Parse refinement intent
        # Re-rank keeping previous context
        pass
    
    def get_context_summary(self) -> str:
        """Summarize conversation for display."""
        if not self.turns:
            return ""
        return f"Showing recommendations for: {self.turns[0].user_input}"

# Usage in bot:
memory = ConversationMemory(session_id="user_123_session_456")

# First turn
products = rank_families(families, answers)
memory.add_turn("I need quiet insulation in ceiling", products)
display_products(products)

# User refines:
refinement = st.text_input("Refine search (optional):")
if refinement:
    refined_products = memory.refine_search(refinement)
    memory.add_turn(refinement, refined_products)
    display_products(refined_products)

# Later: replay conversation
for turn in memory.turns:
    st.write(f"**Turn {turn.turn_id}:** {turn.user_input}")
    display_products(turn.recommended_products)
```

**Benefits:**
- ✅ Better UX: users don't repeat themselves
- ✅ Data capture: understand what refinements users make
- ✅ Debugging: replay conversations for analysis
- ✅ Learning: identify patterns in unsuccessful searches

**Implementation:** 2 days
- Add ConversationMemory class
- Integrate with Streamlit session_state
- Build refinement parsing

---

## 3. USER EXPERIENCE IMPROVEMENTS

### 3.1 Transparency in Scoring

**Current Problem:**
- Users don't know WHY a product was recommended
- Black-box scoring erodes trust
- Hard to debug user complaints ("why isn't X recommended?")

**Recommended Solution:**

```python
def display_ranking_with_transparency(ranked_products: list[RankedFamily]):
    """Show products with breakdown of scoring."""
    import streamlit as st
    
    for rank, product in enumerate(ranked_products[:5], 1):
        with st.expander(f"#{rank}: {product['product_name']} ({product['match_score']:.2f} points)"):
            
            # Score breakdown
            col1, col2 = st.columns(2)
            
            with col1:
                st.metric(
                    "Keyword Match",
                    f"{product['match_details']['keyword_score']:.2f} pts",
                    help="How well product keywords match your requirements"
                )
                st.metric(
                    "Application Match",
                    f"{product['match_details']['application_score']:.2f} pts",
                    help="How well product applications match your use case"
                )
            
            with col2:
                st.metric(
                    "Priority Alignment",
                    f"{product['match_details']['priority_score']:.2f} pts",
                    help=f"Fit with your priority: {product['priority_key']}"
                )
                st.metric(
                    "Placement Bonus",
                    f"+{product['match_details']['placement_boost']:.2f} pts",
                    help="Boost for matching your installation location"
                )
            
            # Matched terms
            st.write("**Matched requirements:**")
            matched_keywords = product.get('matched_keywords', [])
            matched_apps = product.get('matched_applications', [])
            
            if matched_keywords:
                st.write(f"• Keywords: {', '.join(matched_keywords)}")
            if matched_apps:
                st.write(f"• Applications: {', '.join(matched_apps)}")
            
            # Reliability indicator
            if product['reliable_match']:
                st.success("✅ Reliable match (confident recommendation)")
            else:
                st.warning("⚠️ Low confidence match (expert review recommended)")
            
            # Technical specs
            st.write("**Technical Details:**")
            st.table({
                "R-Value": product.get('typical_r_value', 'N/A'),
                "Sound Rating": product.get('typical_rw_rating', 'N/A'),
                "Price/sqm": product.get('cost_per_sqm', 'N/A'),
                "Lead Time": f"{product.get('lead_time_days', 'N/A')} days",
            })
            
            # Feedback mechanism
            st.write("**Was this helpful?**")
            feedback = st.radio(
                label="Feedback",
                options=["👍 Yes", "👎 No", "🤷 Not sure"],
                key=f"feedback_{product['family_id']}"
            )
```

**Benefits:**
- ✅ Transparency builds trust
- ✅ Users can understand mismatches ("oh, I didn't mention R-value")
- ✅ Data for debugging: "users said X is wrong"
- ✅ Educational: users learn about product attributes

**Implementation:** 1-2 days
- Add match_details to ranking engine (already done in v2 ✓)
- Build Streamlit display components

---

### 3.2 Product Comparison View

**Current Problem:**
- Users see products one by one
- Can't easily compare alternatives
- Hidden penalties/boosts not visible

**Recommended Solution:**

```python
def display_product_comparison(products: list[RankedFamily], top_n: int = 5):
    """Show products side-by-side for comparison."""
    import streamlit as st
    import pandas as pd
    
    comparison_data = []
    for p in products[:top_n]:
        comparison_data.append({
            "Product": p['product_name'],
            "Manufacturer": p['manufacturer'],
            "Match Score": p['match_score'],
            "R-Value": p.get('typical_r_value', '—'),
            "Sound Rating": p.get('typical_rw_rating', '—'),
            "Price/sqm": f"${p.get('cost_per_sqm', '—')}",
            "Installation": f"{p.get('installation_time_per_sqm_hours', '—')}h/sqm",
            "Rating": f"⭐ {p.get('rating', 'N/A')}",
        })
    
    df = pd.DataFrame(comparison_data)
    st.dataframe(df, use_container_width=True)
    
    # Highlight best in each category
    st.write("**Best in category:**")
    cols = st.columns(3)
    
    top_match = max(products[:top_n], key=lambda p: p['match_score'])
    cols[0].metric("Best Match", top_match['product_name'], top_match['match_score'])
    
    top_budget = min(products[:top_n], key=lambda p: p.get('cost_per_sqm', float('inf')))
    cols[1].metric("Most Affordable", top_budget['product_name'], f"${top_budget.get('cost_per_sqm', 'N/A')}")
    
    top_rated = max(products[:top_n], key=lambda p: p.get('rating', 0))
    cols[2].metric("Highest Rated", top_rated['product_name'], f"⭐ {top_rated.get('rating', 'N/A')}")
```

**Benefits:**
- ✅ Better decision-making: see trade-offs
- ✅ Handles budget constraints: users can pick cheaper alternative
- ✅ Highlights differentiation: rating, lead time, etc.

**Implementation:** 1 day
- Create comparison dataframe
- Build Streamlit display

---

### 3.3 Mobile-Optimized UI

**Current Problem:**
- Streamlit is desktop-first
- Mobile users abandon the bot
- "Questionnaire on phone" is painful

**Recommended Solution:**

```python
# Check platform and adapt UI
import streamlit as st
from pathlib import Path

def is_mobile():
    """Detect if user is on mobile."""
    # Streamlit doesn't expose user-agent easily, but can use JavaScript
    return False  # Placeholder

# Mobile-optimized layout
if is_mobile():
    # Single column, larger buttons, minimal scrolling
    st.set_page_config(layout="narrow")
    
    # Use radio buttons instead of dropdowns
    priority = st.radio("Priority:", options, horizontal=False)
    
    # Use full-width buttons
    if st.button("Show Results", use_container_width=True):
        pass
else:
    # Desktop: multi-column for efficiency
    st.set_page_config(layout="wide")
    col1, col2 = st.columns(2)
    with col1:
        priority = st.selectbox("Priority:", options)
```

**Better Approach:** Build native mobile apps or use a mobile-friendly framework (React, Flutter).

**Alternatives to Consider:**
1. **React + TypeScript** – Full control over UI/UX
2. **Flutter** – Single codebase for iOS + Android
3. **Expo** – React Native, fast deployment
4. **Streamlit Cloud** – Keep Streamlit but improve mobile CSS

**Implementation:** 5-10 days (if React) or 1-2 weeks (if Flutter)

---

## 4. OPERATIONS & MONITORING

### 4.1 Comprehensive Logging & Observability

**Current Problem:**
- Error handling says "Fall back silently" (line 92 in v1)
- No visibility into why recommendations fail
- Can't debug user complaints

**Recommended Solution:**

```python
import logging
import json
from datetime import datetime
from dataclasses import dataclass

@dataclass
class RecommendationLog:
    """Structured log of recommendation request."""
    timestamp: datetime
    session_id: str
    user_input: str
    detected_priority: str
    products_ranked: int
    top_recommendation: dict
    execution_time_ms: float
    engine_version: str = "v2"
    error: str = None
    
    def to_dict(self):
        return {
            k: str(v) if isinstance(v, datetime) else v
            for k, v in self.__dict__.items()
        }

# Structured logging
def rank_families_with_logging(...):
    """Wrapper that logs all ranking requests."""
    import time
    start = time.time()
    
    logger.info(f"Ranking request: {len(families)} families, answers={len(answers)}")
    
    try:
        result = rank_families(families, answers, manufacturer_scope)
        
        log_entry = RecommendationLog(
            timestamp=datetime.now(),
            session_id=get_session_id(),
            user_input=" ".join(answers.values()),
            detected_priority=result[0].get('priority_key', 'unknown') if result else 'none',
            products_ranked=len(result),
            top_recommendation=result[0] if result else None,
            execution_time_ms=(time.time() - start) * 1000
        )
        
        # Log to file
        with open(f"logs/recommendations_{datetime.now().date()}.jsonl", "a") as f:
            f.write(json.dumps(log_entry.to_dict()) + "\n")
        
        logger.info(f"✓ Ranking complete ({log_entry.execution_time_ms:.1f}ms)")
        
        return result
    
    except Exception as e:
        log_entry = RecommendationLog(
            timestamp=datetime.now(),
            session_id=get_session_id(),
            user_input=" ".join(answers.values()),
            detected_priority='error',
            products_ranked=0,
            top_recommendation=None,
            execution_time_ms=(time.time() - start) * 1000,
            error=str(e)
        )
        
        logger.error(f"✗ Ranking failed: {e}", exc_info=True)
        
        # Still log the error for analysis
        with open(f"logs/errors_{datetime.now().date()}.jsonl", "a") as f:
            f.write(json.dumps(log_entry.to_dict()) + "\n")
        
        raise
```

**Log Analysis Dashboard:**

```python
# analyze_logs.py
import pandas as pd
import streamlit as st
from pathlib import Path

st.title("📊 Recommendation Analytics")

# Load logs
logs = []
for log_file in Path("logs").glob("recommendations_*.jsonl"):
    for line in log_file.open():
        logs.append(json.loads(line))

df = pd.DataFrame(logs)

# Metrics
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Requests", len(df))
col2.metric("Avg Response Time", f"{df['execution_time_ms'].mean():.1f}ms")
col3.metric("Error Rate", f"{df['error'].notna().sum() / len(df) * 100:.1f}%")
col4.metric("Unique Sessions", df['session_id'].nunique())

# Priority distribution
st.bar_chart(df['detected_priority'].value_counts())

# Top recommendations
st.write("Most-recommended products:")
top_products = df['top_recommendation'].apply(lambda x: x.get('product_name') if x else None).value_counts()
st.table(top_products.head(10))

# Errors
if df['error'].notna().sum() > 0:
    st.write("Recent Errors:")
    error_df = df[df['error'].notna()][['timestamp', 'error']].tail(10)
    st.dataframe(error_df)
```

**Benefits:**
- ✅ Complete audit trail for compliance
- ✅ Debug user issues: replay their session
- ✅ Performance monitoring: detect slowdowns
- ✅ Usage analytics: see what features are used

**Implementation:** 2-3 days
- Add structured logging
- Set up log storage
- Build analytics dashboard

---

### 4.2 A/B Testing Framework

**Current Problem:**
- Can't test algorithm changes safely
- All users get same ranking logic
- No data on what works better

**Recommended Solution:**

```python
import hashlib
from enum import Enum

class Variant(str, Enum):
    CONTROL = "control"      # Original lexical ranking
    HYBRID = "hybrid"        # Hybrid ranking
    EXPERIMENTAL = "experimental"

def get_user_variant(session_id: str) -> Variant:
    """Deterministically assign variant based on session."""
    # Consistent: same user always gets same variant
    hash_val = int(hashlib.md5(session_id.encode()).hexdigest(), 16)
    
    if hash_val % 100 < 50:
        return Variant.CONTROL
    elif hash_val % 100 < 75:
        return Variant.HYBRID
    else:
        return Variant.EXPERIMENTAL

def rank_families_with_ab_test(families, answers, session_id):
    """Rank using variant assigned to user."""
    variant = get_user_variant(session_id)
    
    if variant == Variant.CONTROL:
        result = _lexical_rank_families(families, answers)
    elif variant == Variant.HYBRID:
        result = rank_families(families, answers, use_hybrid=True)
    else:  # EXPERIMENTAL
        result = _experimental_ranking(families, answers)
    
    # Log which variant was used
    logger.info(f"Session {session_id} assigned to {variant} variant")
    
    return result, variant

# A/B test dashboard
def show_ab_test_results():
    """Compare variant performance."""
    logs = load_recommendation_logs()
    df = pd.DataFrame(logs)
    
    # Extract variant from log (need to add this)
    df['variant'] = df['session_id'].apply(get_user_variant)
    
    # Metrics by variant
    metrics = df.groupby('variant').agg({
        'session_id': 'nunique',  # Users
        'execution_time_ms': ['mean', 'std'],
        'error': lambda x: (x.notna().sum() / len(x) * 100)
    })
    
    st.table(metrics)
    
    # Click-through rate if feedback is available
    if 'feedback' in df.columns:
        ctr = df.groupby('variant')['feedback'].apply(lambda x: (x == '👍').sum() / len(x))
        st.bar_chart(ctr)
```

**Benefits:**
- ✅ Test changes safely with subset of users
- ✅ Measure impact: response time, user satisfaction, error rate
- ✅ Iterative improvement: release winners
- ✅ Learning: understand what drives good recommendations

**Implementation:** 2 days
- Add variant assignment logic
- Track variant in logs
- Build comparison dashboard

---

### 4.3 Performance Monitoring & Alerting

**Recommended Metrics to Track:**

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| P95 Response Time | <500ms | >1000ms |
| P99 Response Time | <2s | >5s |
| Error Rate | <1% | >5% |
| Recommendation Accuracy | >80% | <60% |
| User Satisfaction | >4.0/5.0 | <3.0/5.0 |
| Config Load Failures | 0% | >0% |
| Embedding Service Up | 99.9% | <99.0% |

**Implementation:**

```python
# monitoring.py
import time
import psutil
from dataclasses import dataclass

@dataclass
class SystemMetrics:
    cpu_percent: float
    memory_percent: float
    response_time_ms: float
    timestamp: datetime

def check_system_health():
    """Check if system is healthy."""
    cpu = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory().percent
    
    if cpu > 90 or memory > 90:
        logger.warning(f"High resource usage: CPU={cpu}%, Memory={memory}%")
        # Send alert
        send_slack_alert(f"🚨 System overload: CPU={cpu}%, Memory={memory}%")

# Integration with Streamlit
def show_system_health():
    """Display system status in Streamlit."""
    import streamlit as st
    
    metrics = get_current_metrics()
    
    col1, col2, col3 = st.columns(3)
    
    cpu_color = "🟢" if metrics.cpu_percent < 70 else "🟡" if metrics.cpu_percent < 90 else "🔴"
    mem_color = "🟢" if metrics.memory_percent < 70 else "🟡" if metrics.memory_percent < 90 else "🔴"
    response_color = "🟢" if metrics.response_time_ms < 500 else "🟡" if metrics.response_time_ms < 1000 else "🔴"
    
    col1.metric(f"{cpu_color} CPU Usage", f"{metrics.cpu_percent:.1f}%")
    col2.metric(f"{mem_color} Memory", f"{metrics.memory_percent:.1f}%")
    col3.metric(f"{response_color} Response Time", f"{metrics.response_time_ms:.0f}ms")
```

**Implementation:** 1-2 days
- Add system metrics collection
- Set up alerts (Slack, PagerDuty)
- Build health dashboard

---

## 5. COMPLIANCE & EXPERT REVIEW WORKFLOWS

### 5.1 Expert Review Process

**Current Problem:**
- "Technical gate" returns REVIEW_REQUIRED but unclear how to implement
- No process for expert verification
- Recommendations might be incorrect but no feedback loop

**Recommended Solution:**

```python
from enum import Enum
from datetime import datetime

class ReviewStatus(str, Enum):
    PENDING = "pending"          # Awaiting expert review
    APPROVED = "approved"        # Expert approved
    APPROVED_WITH_NOTES = "approved_with_notes"
    REJECTED = "rejected"        # Expert rejected
    NEEDS_MORE_INFO = "needs_more_info"

@dataclass
class ExpertReview:
    """Record of expert review."""
    session_id: str
    recommendation_id: str
    user_query: str
    recommended_product: dict
    
    review_status: ReviewStatus
    reviewer_id: str  # Expert email
    review_timestamp: datetime
    review_notes: str
    
    confidence_score: int = None  # 1-5 scale
    approval_reason: str = None
    rejection_reason: str = None

def log_expert_review(review: ExpertReview):
    """Record review in database."""
    # Save to database or file
    with open("reviews/expert_reviews.jsonl", "a") as f:
        f.write(json.dumps({
            k: str(v) if isinstance(v, (datetime, ReviewStatus)) else v
            for k, v in asdict(review).items()
        }) + "\n")

# Streamlit interface for experts
def expert_review_dashboard():
    """Interface for experts to review pending recommendations."""
    import streamlit as st
    
    st.title("👨‍⚕️ Expert Review Queue")
    
    # Get pending reviews
    pending = load_pending_reviews()
    
    if not pending:
        st.success("✓ All recommendations reviewed!")
        return
    
    # Display one recommendation at a time
    review = pending[0]
    
    st.write(f"**Session:** {review['session_id']}")
    st.write(f"**User Query:** {review['user_query']}")
    
    st.subheader("Recommended Product")
    product = review['recommended_product']
    st.write(f"**{product['product_name']}** by {product['manufacturer']}")
    st.write(product['description'])
    
    # Review form
    st.subheader("Your Review")
    
    status = st.radio(
        "Decision:",
        options=[s.value for s in ReviewStatus],
        format_func=lambda x: x.replace("_", " ").title()
    )
    
    confidence = st.slider("Confidence in decision:", 1, 5)
    
    notes = st.text_area("Notes (optional):")
    
    if st.button("Submit Review", type="primary"):
        expert_review = ExpertReview(
            session_id=review['session_id'],
            recommendation_id=review['recommendation_id'],
            user_query=review['user_query'],
            recommended_product=product,
            review_status=ReviewStatus(status),
            reviewer_id=st.secrets.get("expert_email"),
            review_timestamp=datetime.now(),
            review_notes=notes,
            confidence_score=confidence
        )
        
        log_expert_review(expert_review)
        st.success(f"✓ Review submitted!")
        st.rerun()
```

**Benefits:**
- ✅ Quality control: humans verify AI recommendations
- ✅ Feedback loop: teach the algorithm from rejections
- ✅ Accountability: track who approved what
- ✅ Learning: identify weak algorithm patterns

**Implementation:** 2-3 days
- Create ExpertReview dataclass
- Build Streamlit dashboard
- Set up review queue

---

### 5.2 Feedback Loop: Learn from Rejections

**Current Problem:**
- Expert rejects a recommendation but algorithm has no way to learn
- Same mistake happens again

**Recommended Solution:**

```python
def analyze_rejection_patterns():
    """Identify why recommendations are being rejected."""
    reviews = load_expert_reviews()
    
    rejected = [r for r in reviews if r['review_status'] == ReviewStatus.REJECTED]
    
    # Pattern analysis
    patterns = {
        'priority_misdetection': [],
        'wrong_placement_understanding': [],
        'product_not_suitable': [],
        'budget_constraint_ignored': [],
        'compliance_issue': []
    }
    
    for review in rejected:
        user_query = review['user_query']
        notes = review['review_notes']
        
        # NLP analysis: what was wrong?
        if 'priority' in notes.lower():
            patterns['priority_misdetection'].append(user_query)
        elif 'placement' in notes.lower():
            patterns['wrong_placement_understanding'].append(user_query)
        # ... more patterns
    
    # Report patterns
    st.write("**Common Rejection Reasons:**")
    for pattern, queries in patterns.items():
        if queries:
            st.write(f"- {pattern}: {len(queries)} rejections")
            st.caption(f"Example: {queries[0][:100]}...")
    
    # Recommendations for fixing algorithm
    st.write("**Suggested Fixes:**")
    
    if len(patterns['priority_misdetection']) > 5:
        st.warning("❌ Priority detection is unreliable")
        st.write("Recommendation: Retrain priority detection model or adjust PRIORITY_TERMS weights")
    
    if len(patterns['wrong_placement_understanding']) > 5:
        st.warning("❌ Placement detection is unreliable")
        st.write("Recommendation: Add more placement patterns to PlacementDetector.PLACEMENT_PATTERNS")
    
    # Generate training data
    if st.button("Generate Training Data from Rejections"):
        training_data = generate_training_data(rejected)
        st.download_button(
            "Download training_data.jsonl",
            data=training_data,
            file_name="training_data_from_rejections.jsonl"
        )
```

**Benefits:**
- ✅ Continuous improvement: algorithm gets better with each rejection
- ✅ Data-driven: fix what's actually broken, not guesses
- ✅ Feedback loop: closes the gap between AI and expert judgment

**Implementation:** 2-3 days
- Build rejection analyzer
- Create pattern detection
- Generate training data

---

### 5.3 Audit Trail for Compliance

**Current Problem:**
- Building regulations (NCC, BAL, etc.) require proof of due diligence
- No way to show "we checked this product was suitable"
- Liability risk

**Recommended Solution:**

```python
@dataclass
class AuditTrailEntry:
    """Record for compliance audit."""
    timestamp: datetime
    session_id: str
    action: str  # "recommendation", "review", "approval"
    actor: str  # "algorithm" or user email
    
    user_query: str
    recommended_product_id: str
    confidence_score: float
    
    gating_decision: str  # APPROVED, REVIEW_REQUIRED, BLOCKED
    gating_reason: str
    
    expert_review_id: str = None  # If reviewed by human
    approval_by: str = None  # Expert email if approved
    approval_timestamp: datetime = None

def create_compliance_report(session_id: str):
    """Generate audit report for regulatory compliance."""
    entries = load_audit_trail(session_id)
    
    report = f"""
    COMPLIANCE AUDIT REPORT
    =======================
    Session: {session_id}
    Generated: {datetime.now()}
    
    RECOMMENDATION SUMMARY
    ----------------------
    """
    
    for entry in entries:
        report += f"""
    
    Timestamp: {entry['timestamp']}
    Action: {entry['action']}
    Product: {entry['recommended_product_id']}
    User Query: {entry['user_query']}
    Confidence: {entry['confidence_score']}
    Gating Decision: {entry['gating_decision']}
    Reason: {entry['gating_reason']}
    """
        
        if entry['expert_review_id']:
            report += f"""
    Expert Review:
    - Reviewer: {entry['approval_by']}
    - Date: {entry['approval_timestamp']}
    """
    
    report += """
    
    CERTIFICATION
    ---------------
    This recommendation was:
    ✓ Generated by approved algorithm (v2.0)
    ✓ Passed technical gating checks
    ✓ [Expert reviewed if REVIEW_REQUIRED]
    ✓ Logged with full audit trail
    
    For compliance questions, contact: compliance@insulation.com
    """
    
    return report

# Streamlit interface
def download_audit_report(session_id: str):
    """Allow users to download compliance report."""
    import streamlit as st
    
    if st.button("📋 Generate Compliance Report"):
        report = create_compliance_report(session_id)
        st.download_button(
            "Download PDF",
            data=report,
            file_name=f"audit_report_{session_id}.txt",
            mime="text/plain"
        )
```

**Benefits:**
- ✅ Regulatory compliance: audit trail shows due diligence
- ✅ Liability protection: documented decision process
- ✅ Transparency: can show customers how product was selected

**Implementation:** 2 days
- Create AuditTrailEntry
- Add logging at key points
- Build report generator

---

## 6. IMPLEMENTATION ROADMAP

### Phase 1: Improve Core Engine (1 week)
- ✅ Deploy recommendation engine v2 (code provided)
- ✅ Create improved config system
- ✅ Add comprehensive logging
- **Effort:** 3-4 days | **Impact:** High (fixes critical bugs)

### Phase 2: Product Data (1-2 weeks)
- Add enriched fields to product families
- Version product catalog
- Set up embedding pipeline
- **Effort:** 5-7 days | **Impact:** Medium (enables future features)

### Phase 3: Bot Logic & UX (2-3 weeks)
- Structured question flow with branching
- Conversation memory for multi-turn interaction
- Transparency in scoring (breakdown display)
- Product comparison view
- **Effort:** 7-10 days | **Impact:** High (major UX improvement)

### Phase 4: Operations (2 weeks)
- Structured logging & analytics dashboard
- A/B testing framework
- System health monitoring
- **Effort:** 5-7 days | **Impact:** Medium (operational visibility)

### Phase 5: Compliance & Expert Review (1 week)
- Expert review dashboard
- Rejection pattern analysis
- Audit trail & compliance reports
- **Effort:** 3-5 days | **Impact:** High (risk mitigation)

### Phase 6: Mobile & Polish (2-3 weeks)
- Mobile-optimized UI or native app
- Performance optimization
- User testing & iteration
- **Effort:** 7-10 days | **Impact:** Medium (reach improvement)

**Total Effort:** ~1-2 months for full implementation  
**Recommended Approach:** Parallel work (core engine, product data, operations)

---

## 7. SUCCESS METRICS

### Measure these before & after improvements:

| Metric | Current | Target | How to Measure |
|--------|---------|--------|-----------------|
| **User Satisfaction** | Unknown | >4.0/5.0 | Post-recommendation survey |
| **Task Completion Rate** | Unknown | >85% | Track through GA |
| **Recommendation Accuracy** | Unknown | >85% | Expert review rate |
| **Response Time (P95)** | Unknown | <500ms | Application logs |
| **Error Rate** | Unknown | <1% | Application logs |
| **Conversion to Quote** | Unknown | >40% | CRM integration |
| **Mobile Adoption** | Unknown | >30% | GA by device |
| **Expert Review Time** | Unknown | <5min/review | Track in dashboard |
| **Algorithm Improvement Rate** | Unknown | 5% quarter-over-quarter | A/B test results |

---

## 8. CRITICAL NEXT STEPS

### Before launching to users:

1. ✅ **Deploy recommendation engine v2** (fixes known issues)
2. ✅ **Add comprehensive logging** (understand failures)
3. **Set up expert review process** (quality gate)
4. **A/B test against current system** (measure improvement)
5. **Create compliance audit trail** (regulatory)
6. **Set up monitoring & alerts** (detect problems early)

### Questions for leadership:

- Who owns the expert review process? (hire/train reviewers)
- What's the compliance requirement? (affects audit trail requirements)
- Should we build native mobile, or improve mobile web?
- Budget for embeddings infrastructure (Ollama, vector DB)?
- Timeline to launch improvements? (affects phasing)

---

## 9. REFERENCES & RESOURCES

### Code Quality
- [Python Logging Best Practices](https://docs.python.org/3/library/logging.html)
- [Type Hints in Python](https://peps.python.org/pep-0484/)
- [Testing Strategies](https://docs.pytest.org/)

### Machine Learning / Ranking
- [Learning to Rank](https://en.wikipedia.org/wiki/Learning_to_rank)
- [FAISS (Facebook AI Similarity Search)](https://github.com/facebookresearch/faiss)
- [Sentence Transformers](https://www.sbert.net/)
- [A/B Testing in Production](https://www.exp-platform.com/)

### Product Recommendations
- [Recommendation System Design](https://eugeneyan.com/writing/recommendation-systems/)
- [Cold Start Problem](https://towardsdatascience.com/solve-the-cold-start-problem-in-recommendation-systems-d41c1b90e57)

### Operations
- [Observability for Python Apps](https://opentelemetry.io/)
- [Structured Logging](https://www.structlog.org/)
- [Feature Flags](https://www.getunleash.io/)

---

**Document Version:** 1.0  
**Last Updated:** September 2026  
**Next Review:** October 2026
