# Response Time Optimization Analysis

## Current Request Flow & Bottlenecks

### Request Flow Timeline

```
Request → Controller → Services → LLM/Vector/DB → Response
```

**Estimated Current Times:**

1. **Vector Search (ChromaDB)**: 100-300ms
2. **LLM Call (Gemini API)**: 2000-5000ms ⚠️ **BIGGEST BOTTLENECK**
3. **Database Write**: 20-50ms
4. **JSON Parsing & Processing**: 10-30ms
5. **Session Management**: <1ms

**Total: ~2.5-5.5 seconds** (meets 5s target, but can be improved)

---

## Critical Optimizations (High Impact)

### 1. **Async LLM Calls** 🔥 **CRITICAL**

**Current**: Synchronous blocking LLM call
**Impact**: 2-5 seconds saved
**Implementation**:

- Use `asyncio.to_thread()` or async HTTP client for Gemini API
- Make `generate_answer_with_followup` truly async
- Use async database operations

**Files to modify**:

- `src/services/qa_service.py` - Make LLM call async
- `src/controllers/qa_controller.py` - Handle async properly
- `src/utils/config.py` - Add async Gemini client support

### 2. **Async Database Operations** 🔥 **HIGH IMPACT**

**Current**: Synchronous SQLAlchemy blocking the event loop
**Impact**: 20-50ms saved + better concurrency
**Implementation**:

- Switch to `asyncpg` driver
- Use `SQLAlchemy 2.0` async engine
- Make repository methods async

**Files to modify**:

- `database.py` - Use async engine
- `src/repository/conversation_repository.py` - Make async
- `src/routes/qa_routes.py` - Use async database dependency

### 3. **Question Answer Caching** 🔥 **HIGH IMPACT**

**Current**: Every question triggers LLM call
**Impact**: 2-5 seconds saved for cached questions
**Implementation**:

- Cache exact question matches
- Cache similar questions (fuzzy matching)
- Use Redis or in-memory cache with TTL

**Cache Strategy**:

```python
# Exact match cache
cache_key = hashlib.md5(question.lower().strip().encode()).hexdigest()
if cache.exists(cache_key):
    return cached_answer  # 0ms response!

# Similar question cache (check first 3-5 most similar)
similar_questions = find_similar_in_db(question)
if similar_questions and similarity > 0.85:
    return similar_questions[0].answer  # Reuse answer
```

### 4. **Parallel Operations** ⚡ **MEDIUM IMPACT**

**Current**: Sequential operations
**Impact**: 100-300ms saved
**Implementation**:

- Run vector search and session check in parallel
- Pre-fetch previous context while waiting for vector results

---

## Medium Priority Optimizations

### 5. **Database Connection Pooling**

**Current**: Basic pooling
**Optimization**: Tune pool settings

```python
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,          # Increase from default 5
    max_overflow=20,        # Allow more connections
    pool_timeout=30,
    pool_recycle=3600      # Recycle connections after 1 hour
)
```

### 6. **Reduce Vector Search Scope**

**Current**: Retrieves top 5 documents (k=5)
**Optimization**:

- Reduce to k=3 for faster search
- Add early stopping if high confidence match found

### 7. **Optimize Prompt Length**

**Current**: Long prompts with examples
**Optimization**:

- Shorten prompt (reduce by ~30-40%)
- Remove redundant examples
- Use system messages more efficiently

### 8. **Stream LLM Response** ⚡ **USER EXPERIENCE**

**Current**: Wait for complete response
**Optimization**: Stream response as it's generated

- First token in ~500ms instead of 2-5s
- Better perceived performance

---

## Low Priority Optimizations

### 9. **Database Indexes**

- Ensure all query fields are indexed (already done)
- Add composite indexes if needed

### 10. **Reduce JSON Parsing Overhead**

- Current parsing is already optimized
- Consider using `orjson` instead of `json` (5-10% faster)

### 11. **ChromaDB Optimization**

- Use persistent storage (already done)
- Consider reducing embedding dimensions if possible
- Cache frequently accessed embeddings

---

## Implementation Priority

### Phase 1: Quick Wins (1-2 hours) → **Target: 4-5 seconds**

1. ✅ Add connection pooling configuration
2. ✅ Reduce vector search to k=3
3. ✅ Shorten prompt length

### Phase 2: High Impact (4-6 hours) → **Target: 2-3 seconds**

1. ✅ Implement question caching (exact + similar)
2. ✅ Make LLM call async
3. ✅ Parallelize vector search and context building

### Phase 3: Advanced (8-12 hours) → **Target: 1-2 seconds**

1. ✅ Full async database operations
2. ✅ Streaming responses
3. ✅ Advanced caching with Redis

---

## Detailed Implementation Guide

### 1. Async LLM Calls

```python
# src/services/qa_service.py
import asyncio
import httpx

async def generate_answer_with_followup_async(...):
    # Run LLM call in thread pool to avoid blocking
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: _sync_generate(prompt_text)
    )
    return result
```

### 2. Question Caching

```python
# src/services/cache_service.py (NEW FILE)
from functools import lru_cache
import hashlib
from typing import Optional

_cache = {}
MAX_CACHE_SIZE = 1000

def get_cached_answer(question: str) -> Optional[str]:
    key = hashlib.md5(question.lower().strip().encode()).hexdigest()
    return _cache.get(key)

def cache_answer(question: str, answer: str, follow_up: str):
    key = hashlib.md5(question.lower().strip().encode()).hexdigest()
    if len(_cache) >= MAX_CACHE_SIZE:
        # Remove oldest entry (simple FIFO)
        _cache.pop(next(iter(_cache)))
    _cache[key] = {
        'answer': answer,
        'follow_up': follow_up,
        'timestamp': time.time()
    }
```

### 3. Similar Question Search in DB

```python
# Add to src/repository/conversation_repository.py
def find_similar_question(self, question: str, threshold: float = 0.85) -> Optional[Conversation]:
    """Find similar question using full-text search and similarity"""
    # Use PostgreSQL pg_trgm for similarity matching
    similar = self.db.execute(
        text("""
            SELECT *, similarity(question, :q) as sim
            FROM conversations
            WHERE similarity(question, :q) > :threshold
            ORDER BY sim DESC
            LIMIT 1
        """),
        {'q': question, 'threshold': threshold}
    ).first()
    return similar
```

### 4. Parallel Operations

```python
# In qa_controller.py
import asyncio

# Run vector search and session check in parallel
vector_task = asyncio.create_task(
    asyncio.to_thread(self.qa_service.retrieve_context, question_text)
)
session_task = asyncio.create_task(
    asyncio.to_thread(self.context_service.check_question_relation, ...)
)

context_block, is_related = await asyncio.gather(
    vector_task,
    session_task
)
```

---

## Expected Results After Optimizations

### Current (Baseline)

- Average: **3-5 seconds**
- P95: **6-8 seconds**
- P99: **8-10 seconds**

### After Phase 1 (Quick Wins)

- Average: **2-4 seconds**
- P95: **4-5 seconds**
- P99: **5-6 seconds**

### After Phase 2 (High Impact)

- Average: **1-2 seconds** (cached: <100ms)
- P95: **2-3 seconds**
- P99: **3-4 seconds**

### After Phase 3 (Advanced)

- Average: **0.5-1.5 seconds** (cached: <50ms)
- P95: **1.5-2 seconds**
- P99: **2-2.5 seconds**

---

## Monitoring & Metrics

Add timing middleware to track:

```python
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    # Log: endpoint, time, cached_hit
    return response
```

---

## Notes

- **LLM calls are inherently slow** (2-5s) - caching is critical
- **Vector search is fast** (~100-300ms) - already optimized
- **Database is fast** (~20-50ms) - async will help with concurrency
- **Focus on caching** for biggest impact
- **Async operations** improve concurrent request handling
