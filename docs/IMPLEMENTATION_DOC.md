        breakdown: {
          ratings: Object.fromEntries(
            breakdown.rows.map(r => [r.rating, parseInt(r.count)])
          )
        },
        trends: trends.rows,
        low_rated_conversations: lowRated.rows
      }
    });

} catch (error) {
console.error('Analytics error:', error);
res.status(500).json({ error: 'Failed to retrieve analytics' });
}
});

```

#### 3. Get FAQ Effectiveness Report
```

GET /api/v1/companies/:id/faqs/effectiveness
Authorization: Bearer <admin-jwt-token>

Response (200 OK):
{
"success": true,
"data": {
"faqs": [
{
"faq_id": "faq-uuid-1",
"question": "How do I reset my password?",
"total_references": 145,
"helpful_count": 132,
"unhelpful_count": 13,
"effectiveness_rate": 0.91
},
{
"faq_id": "faq-uuid-2",
"question": "What are your refund terms?",
"total_references": 89,
"helpful_count": 45,
"unhelpful_count": 44,
"effectiveness_rate": 0.51 // Needs review
}
],
"recommendations": [
{
"faq_id": "faq-uuid-2",
"issue": "low_effectiveness",
"suggestion": "Consider rewriting or adding more detail"
}
]
}
}

````

```javascript
app.get('/api/v1/companies/:id/faqs/effectiveness', authenticateAdmin, async (req, res) => {
  const { id: company_id } = req.params;

  try {
    const effectiveness = await db.query(`
      SELECT
        f.id as faq_id,
        f.question,
        COUNT(*) as total_references,
        COUNT(CASE WHEN ff.was_helpful = TRUE THEN 1 END) as helpful_count,
        COUNT(CASE WHEN ff.was_helpful = FALSE THEN 1 END) as unhelpful_count,
        COUNT(CASE WHEN ff.was_helpful = TRUE THEN 1 END)::FLOAT / COUNT(*) as effectiveness_rate
      FROM faqs f
      JOIN faq_feedback ff ON ff.faq_id = f.id
      WHERE f.company_id = $1
      GROUP BY f.id, f.question
      HAVING COUNT(*) >= 10  -- Minimum sample size
      ORDER BY effectiveness_rate ASC
    `, [company_id]);

    // Identify FAQs needing improvement (< 60% effectiveness)
    const recommendations = effectiveness.rows
      .filter(faq => faq.effectiveness_rate < 0.60)
      .map(faq => ({
        faq_id: faq.faq_id,
        issue: 'low_effectiveness',
        suggestion: 'Consider rewriting or adding more detail',
        current_rate: faq.effectiveness_rate
      }));

    res.status(200).json({
      success: true,
      data: {
        faqs: effectiveness.rows,
        recommendations
      }
    });
  } catch (error) {
    res.status(500).json({ error: 'Failed to retrieve FAQ effectiveness' });
  }
});
````

### Verification Checklist

- [ ] Feedback API accepts ratings (1-5) and thumbs up/down
- [ ] Sentiment calculated correctly from rating/feedback type
- [ ] FAQ effectiveness tracked when AI cites sources
- [ ] Analytics dashboard shows accurate aggregations
- [ ] NPS score calculated correctly (% promoters - % detractors)
- [ ] Low-rated conversations flagged for review
- [ ] Materialized view refreshed daily for performance
- [ ] Feedback linked to specific messages when provided
- [ ] Anonymous users can submit feedback
- [ ] Admin can export feedback data (CSV/JSON)

---

## Feature 10: Session Cache & Context Management

### Business Requirements

- Cache recent conversation context for fast access
- Store user query embeddings to avoid recomputation
- Maintain ephemeral state (typing indicators, presence)
- Automatic expiry of stale cache entries
- Fallback to database when cache misses

### Database Schema (Postgres Fallback)

```sql
CREATE TABLE chat_sessions_cache (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  session_data JSONB NOT NULL,
  expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_chat_sessions_cache_conversation ON chat_sessions_cache(conversation_id);
CREATE INDEX idx_chat_sessions_cache_expires_at ON chat_sessions_cache(expires_at);

-- Session data structure:
-- {
--   "last_messages": [
--     { "sender": "user", "content": "...", "timestamp": "..." }
--   ],
--   "user_context": {
--     "last_query_embedding": [0.123, ...],
--     "matched_faqs": ["faq-uuid-1", "faq-uuid-2"],
--     "confidence_history": [0.89, 0.92, 0.75]
--   },
--   "model_state": {
--     "temperature": 0.7,
--     "max_tokens": 500
--   }
-- }
```

### Redis Cache Implementation (Preferred)

```javascript
const Redis = require("ioredis");

const redis = new Redis({
  host: process.env.REDIS_HOST,
  port: process.env.REDIS_PORT,
  password: process.env.REDIS_PASSWORD,
  db: 0,
  retryStrategy: (times) => Math.min(times * 50, 2000),
});

const CACHE_TTL = 1800; // 30 minutes
const MESSAGE_HISTORY_LIMIT = 20;

// Cache key patterns
const KEYS = {
  conversation: (id) => `conv:${id}`,
  messages: (id) => `conv:${id}:messages`,
  embedding: (id) => `conv:${id}:last_embedding`,
  context: (id) => `conv:${id}:context`,
  typing: (id) => `conv:${id}:typing`,
};

// Cache conversation context
async function cacheConversationContext(conversationId, context) {
  try {
    await redis.setex(
      KEYS.context(conversationId),
      CACHE_TTL,
      JSON.stringify(context)
    );
  } catch (error) {
    console.error("Cache write error:", error);
    // Fallback to database
    await db.query(
      `
      INSERT INTO chat_sessions_cache (conversation_id, session_data, expires_at)
      VALUES ($1, $2, NOW() + INTERVAL '30 minutes')
      ON CONFLICT (conversation_id) DO UPDATE SET
        session_data = EXCLUDED.session_data,
        expires_at = EXCLUDED.expires_at,
        updated_at = NOW()
    `,
      [conversationId, context]
    );
  }
}

// Retrieve conversation context
async function getConversationContext(conversationId) {
  try {
    // Try Redis first
    const cached = await redis.get(KEYS.context(conversationId));
    if (cached) {
      return JSON.parse(cached);
    }

    // Fallback to database
    const result = await db.query(
      `
      SELECT session_data
      FROM chat_sessions_cache
      WHERE conversation_id = $1 AND expires_at > NOW()
    `,
      [conversationId]
    );

    if (result.rows.length > 0) {
      const data = result.rows[0].session_data;
      // Repopulate Redis cache
      await cacheConversationContext(conversationId, data);
      return data;
    }

    // No cache, build from database
    return await buildContextFromDB(conversationId);
  } catch (error) {
    console.error("Cache read error:", error);
    return await buildContextFromDB(conversationId);
  }
}

// Build context from database (cache miss)
async function buildContextFromDB(conversationId) {
  const messages = await db.query(
    `
    SELECT sender, content, created_at, metadata
    FROM messages
    WHERE conversation_id = $1
    ORDER BY created_at DESC
    LIMIT $2
  `,
    [conversationId, MESSAGE_HISTORY_LIMIT]
  );

  const context = {
    last_messages: messages.rows.reverse(),
    user_context: {
      matched_faqs: [],
      confidence_history: [],
    },
    model_state: {
      temperature: 0.7,
      max_tokens: 500,
    },
    created_at: new Date().toISOString(),
  };

  // Cache for future use
  await cacheConversationContext(conversationId, context);

  return context;
}

// Cache message with optimized structure
async function cacheMessage(conversationId, message) {
  try {
    // Use Redis List for message history (FIFO)
    await redis.lpush(KEYS.messages(conversationId), JSON.stringify(message));

    // Trim to last N messages
    await redis.ltrim(
      KEYS.messages(conversationId),
      0,
      MESSAGE_HISTORY_LIMIT - 1
    );

    // Set expiry on the list
    await redis.expire(KEYS.messages(conversationId), CACHE_TTL);
  } catch (error) {
    console.error("Message cache error:", error);
  }
}

// Get cached message history
async function getCachedMessages(conversationId, limit = 10) {
  try {
    const messages = await redis.lrange(
      KEYS.messages(conversationId),
      0,
      limit - 1
    );

    return messages.map((msg) => JSON.parse(msg)).reverse();
  } catch (error) {
    console.error("Message retrieval error:", error);
    return [];
  }
}

// Cache user query embedding
async function cacheQueryEmbedding(conversationId, query, embedding) {
  try {
    await redis.setex(
      KEYS.embedding(conversationId),
      CACHE_TTL,
      JSON.stringify({ query, embedding, timestamp: Date.now() })
    );
  } catch (error) {
    console.error("Embedding cache error:", error);
  }
}

// Get cached embedding if query is similar
async function getCachedEmbedding(conversationId, query) {
  try {
    const cached = await redis.get(KEYS.embedding(conversationId));
    if (!cached) return null;

    const data = JSON.parse(cached);

    // Check if query is identical (simple optimization)
    if (data.query.toLowerCase() === query.toLowerCase()) {
      return data.embedding;
    }

    // For more sophisticated matching, use string similarity
    const similarity = stringSimilarity(data.query, query);
    if (similarity > 0.95) {
      return data.embedding;
    }

    return null;
  } catch (error) {
    console.error("Embedding retrieval error:", error);
    return null;
  }
}

// Simple string similarity (Levenshtein-based)
function stringSimilarity(str1, str2) {
  const longer = str1.length > str2.length ? str1 : str2;
  const shorter = str1.length > str2.length ? str2 : str1;

  if (longer.length === 0) return 1.0;

  const editDistance = levenshteinDistance(longer, shorter);
  return (longer.length - editDistance) / longer.length;
}

function levenshteinDistance(str1, str2) {
  const matrix = [];

  for (let i = 0; i <= str2.length; i++) {
    matrix[i] = [i];
  }

  for (let j = 0; j <= str1.length; j++) {
    matrix[0][j] = j;
  }

  for (let i = 1; i <= str2.length; i++) {
    for (let j = 1; j <= str1.length; j++) {
      if (str2.charAt(i - 1) === str1.charAt(j - 1)) {
        matrix[i][j] = matrix[i - 1][j - 1];
      } else {
        matrix[i][j] = Math.min(
          matrix[i - 1][j - 1] + 1,
          matrix[i][j - 1] + 1,
          matrix[i - 1][j] + 1
        );
      }
    }
  }

  return matrix[str2.length][str1.length];
}

// Typing indicators (ephemeral)
async function setTypingIndicator(conversationId, userId, isTyping) {
  const key = KEYS.typing(conversationId);

  if (isTyping) {
    await redis.sadd(key, userId);
    await redis.expire(key, 10); // Auto-expire after 10 seconds
  } else {
    await redis.srem(key, userId);
  }
}

async function getTypingUsers(conversationId) {
  try {
    return await redis.smembers(KEYS.typing(conversationId));
  } catch (error) {
    return [];
  }
}

// Batch cleanup of expired cache entries
async function cleanupExpiredSessions() {
  try {
    // Cleanup database cache
    const result = await db.query(`
      DELETE FROM chat_sessions_cache
      WHERE expires_at < NOW()
      RETURNING id
    `);

    console.log(`Cleaned up ${result.rowCount} expired session cache entries`);

    // Redis handles TTL automatically, but we can scan for orphaned keys
    const pattern = "conv:*";
    const stream = redis.scanStream({ match: pattern, count: 100 });

    let cleanedCount = 0;

    stream.on("data", async (keys) => {
      for (const key of keys) {
        const ttl = await redis.ttl(key);
        if (ttl === -1) {
          // Key exists but has no expiry (orphaned)
          await redis.expire(key, CACHE_TTL);
          cleanedCount++;
        }
      }
    });

    stream.on("end", () => {
      console.log(`Set expiry on ${cleanedCount} orphaned Redis keys`);
    });
  } catch (error) {
    console.error("Cache cleanup error:", error);
  }
}
```

### Optimized AI Response with Caching

```javascript
async function generateAIResponseWithCache(
  companyId,
  conversationId,
  userMessage
) {
  const startTime = Date.now();

  try {
    // Step 1: Try to get cached context
    let context = await getConversationContext(conversationId);

    // Step 2: Check if we can reuse cached embedding
    let userEmbedding = await getCachedEmbedding(conversationId, userMessage);

    if (!userEmbedding) {
      // Generate new embedding
      const embeddingResponse = await openai.embeddings.create({
        model: "text-embedding-ada-002",
        input: userMessage,
      });

      userEmbedding = embeddingResponse.data[0].embedding;

      // Cache for future use
      await cacheQueryEmbedding(conversationId, userMessage, userEmbedding);
    }

    // Step 3: Get cached messages
    const cachedMessages = await getCachedMessages(conversationId, 10);

    // Step 4: Semantic search (use cached embedding)
    const relevantFAQs = await semanticSearchWithVector(
      userEmbedding,
      companyId,
      { limit: 3, threshold: 0.65 }
    );

    // Step 5: Build prompt and call LLM (same as before)
    const aiResponse = await callLLMWithContext(
      userMessage,
      cachedMessages,
      relevantFAQs,
      context.model_state
    );

    // Step 6: Update context cache
    context.user_context.matched_faqs = relevantFAQs.map((f) => f.faq_id);
    context.user_context.confidence_history.push(aiResponse.confidence_score);

    await cacheConversationContext(conversationId, context);

    // Step 7: Cache the new message
    await cacheMessage(conversationId, {
      sender: "user",
      content: userMessage,
      timestamp: new Date().toISOString(),
    });

    await cacheMessage(conversationId, {
      sender: "ai",
      content: aiResponse.content,
      timestamp: new Date().toISOString(),
    });

    return {
      ...aiResponse,
      cache_hit: !!userEmbedding,
      processing_time_ms: Date.now() - startTime,
    };
  } catch (error) {
    console.error("Cached AI response error:", error);
    throw error;
  }
}

// Semantic search using pre-computed embedding
async function semanticSearchWithVector(embedding, companyId, options = {}) {
  const { limit = 5, threshold = 0.75 } = options;

  const results = await db.query(
    `
    SELECT 
      f.id,
      f.question,
      f.answer,
      f.category,
      1 - (e.embedding <=> $1::vector) AS similarity_score
    FROM faq_embeddings e
    JOIN faqs f ON f.id = e.faq_id
    WHERE 
      e.company_id = $2
      AND f.is_active = TRUE
      AND 1 - (e.embedding <=> $1::vector) >= $3
    ORDER BY e.embedding <=> $1::vector
    LIMIT $4
  `,
    [`[${embedding.join(",")}]`, companyId, threshold, limit]
  );

  return results.rows.map((row) => ({
    faq_id: row.id,
    question: row.question,
    answer: row.answer,
    category: row.category,
    similarity_score: parseFloat(row.similarity_score.toFixed(4)),
  }));
}
```

### Background Job: Cache Cleanup

```javascript
// Cron: Every 5 minutes
async function scheduledCacheCleanup() {
  await cleanupExpiredSessions();
}

// Cron configuration
const cron = require("node-cron");

// Run every 5 minutes
cron.schedule("*/5 * * * *", async () => {
  console.log("Running cache cleanup...");
  await scheduledCacheCleanup();
});
```

### Verification Checklist

- [ ] Redis connection established with retry logic
- [ ] Cache TTL set to 30 minutes for all entries
- [ ] Message history limited to last 20 messages
- [ ] Embedding cache reduces API calls (track hit rate)
- [ ] Context retrieval falls back to database on cache miss
- [ ] Typing indicators expire after 10 seconds
- [ ] Cleanup job removes expired database cache entries
- [ ] Cache hit rate monitored (target: > 60%)
- [ ] Average response time reduced by caching (measure before/after)
- [ ] Postgres fallback works when Redis unavailable

---

## Feature 11: Audit Logs & Events

### Business Requirements

- Comprehensive event logging for security and compliance
- Track all critical system actions
- Support forensic analysis and debugging
- Enable compliance reporting (SOC2, GDPR, HIPAA)
- Immutable log records

### Database Schema

```sql
CREATE TABLE audit_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id),
  company_id UUID REFERENCES companies(id),
  agent_id UUID REFERENCES support_agents(id),
  action TEXT NOT NULL,                    -- Event type (e.g., 'USER_LOGIN', 'FAQ_CREATED')
  entity_type TEXT,                        -- 'user', 'company', 'faq', 'conversation', etc.
  entity_id UUID,                          -- ID of affected entity
  details JSONB DEFAULT '{}'::jsonb,       -- Event-specific data
  ip_address INET,
  user_agent TEXT,
  status TEXT DEFAULT 'success',           -- 'success', 'failure'
  error_message TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX idx_audit_logs_user ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_company ON audit_logs(company_id);
CREATE INDEX idx_audit_logs_action ON audit_logs(action);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at DESC);
CREATE INDEX idx_audit_logs_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX idx_audit_logs_status ON audit_logs(status) WHERE status = 'failure';

-- Composite index for dashboard queries
CREATE INDEX idx_audit_logs_company_created ON audit_logs(company_id, created_at DESC);

-- Prevent modifications (immutability)
CREATE RULE audit_logs_no_update AS ON UPDATE TO audit_logs DO INSTEAD NOTHING;
CREATE RULE audit_logs_no_delete AS ON DELETE TO audit_logs DO INSTEAD NOTHING;

-- Partitioning for performance (optional, for high-volume systems)
-- CREATE TABLE audit_logs_2025_01 PARTITION OF audit_logs
-- FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
```

### Event Types Taxonomy

```javascript
const AUDIT_EVENTS = {
  // Authentication & Authorization
  USER_REGISTERED: "USER_REGISTERED",
  USER_LOGIN: "USER_LOGIN",
  USER_LOGOUT: "USER_LOGOUT",
  USER_LOGIN_FAILED: "USER_LOGIN_FAILED",
  PASSWORD_RESET_REQUESTED: "PASSWORD_RESET_REQUESTED",
  PASSWORD_CHANGED: "PASSWORD_CHANGED",
  OTP_SENT: "OTP_SENT",
  OTP_VERIFIED: "OTP_VERIFIED",

  // Company Management
  COMPANY_CREATED: "COMPANY_CREATED",
  COMPANY_UPDATED: "COMPANY_UPDATED",
  API_KEY_GENERATED: "API_KEY_GENERATED",
  API_KEY_ROTATED: "API_KEY_ROTATED",
  WEBHOOK_CONFIGURED: "WEBHOOK_CONFIGURED",

  // Plan & Billing
  PLAN_UPGRADED: "PLAN_UPGRADED",
  PLAN_DOWNGRADED: "PLAN_DOWNGRADED",
  QUOTA_EXCEEDED: "QUOTA_EXCEEDED",
  QUOTA_RESET: "QUOTA_RESET",
  QUOTA_ADJUSTED: "QUOTA_ADJUSTED",

  // FAQ Management
  FAQ_CREATED: "FAQ_CREATED",
  FAQ_UPDATED: "FAQ_UPDATED",
  FAQ_DELETED: "FAQ_DELETED",
  FAQ_BULK_UPLOADED: "FAQ_BULK_UPLOADED",
  FAQ_EMBEDDING_GENERATED: "FAQ_EMBEDDING_GENERATED",
  FAQ_EMBEDDING_FAILED: "FAQ_EMBEDDING_FAILED",

  // Conversations
  CONVERSATION_STARTED: "CONVERSATION_STARTED",
  MESSAGE_SENT: "MESSAGE_SENT",
  CONVERSATION_ESCALATED: "CONVERSATION_ESCALATED",
  CONVERSATION_CLOSED: "CONVERSATION_CLOSED",
  AI_RESPONSE_GENERATED: "AI_RESPONSE_GENERATED",

  // Agent Actions
  AGENT_CREATED: "AGENT_CREATED",
  AGENT_LOGIN: "AGENT_LOGIN",
  AGENT_ASSIGNED: "AGENT_ASSIGNED",
  AGENT_MESSAGE_SENT: "AGENT_MESSAGE_SENT",
  AGENT_STATUS_CHANGED: "AGENT_STATUS_CHANGED",

  // File Operations
  FILE_UPLOADED: "FILE_UPLOADED",
  FILE_DOWNLOADED: "FILE_DOWNLOADED",
  FILE_DELETED: "FILE_DELETED",
  FILE_SCAN_COMPLETED: "FILE_SCAN_COMPLETED",
  FILE_INFECTED: "FILE_INFECTED",

  // Feedback
  FEEDBACK_SUBMITTED: "FEEDBACK_SUBMITTED",

  // System Events
  SYSTEM_ERROR: "SYSTEM_ERROR",
  RATE_LIMIT_EXCEEDED: "RATE_LIMIT_EXCEEDED",
  UNAUTHORIZED_ACCESS: "UNAUTHORIZED_ACCESS",
};
```

### Audit Logger Service

```javascript
class AuditLogger {
  static async log({
    action,
    user_id = null,
    company_id = null,
    agent_id = null,
    entity_type = null,
    entity_id = null,
    details = {},
    ip_address = null,
    user_agent = null,
    status = "success",
    error_message = null,
  }) {
    try {
      await db.query(
        `
        INSERT INTO audit_logs (
          action, user_id, company_id, agent_id,
          entity_type, entity_id, details,
          ip_address, user_agent, status, error_message
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
      `,
        [
          action,
          user_id,
          company_id,
          agent_id,
          entity_type,
          entity_id,
          JSON.stringify(details),
          ip_address,
          user_agent,
          status,
          error_message,
        ]
      );
    } catch (error) {
      // Log failures should never break the application
      console.error("Audit log write failed:", error);

      // Fallback: write to file or external logging service
      await this.fallbackLog({
        action,
        error: error.message,
        timestamp: new Date().toISOString(),
      });
    }
  }

  static async fallbackLog(data) {
    const fs = require("fs").promises;
    const logFile = `./logs/audit_fallback_${
      new Date().toISOString().split("T")[0]
    }.log`;

    try {
      await fs.appendFile(logFile, JSON.stringify(data) + "\n");
    } catch (error) {
      console.error("Fallback logging failed:", error);
    }
  }

  // Helper methods for common events
  static async logLogin(
    userId,
    companyId,
    ipAddress,
    userAgent,
    success = true
  ) {
    await this.log({
      action: success
        ? AUDIT_EVENTS.USER_LOGIN
        : AUDIT_EVENTS.USER_LOGIN_FAILED,
      user_id: userId,
      company_id: companyId,
      ip_address: ipAddress,
      user_agent: userAgent,
      status: success ? "success" : "failure",
      error_message: success ? null : "Invalid credentials",
    });
  }

  static async logFAQChange(
    action,
    faqId,
    companyId,
    userId,
    oldData = null,
    newData = null
  ) {
    const details = {};

    if (oldData && newData) {
      // Calculate diff
      details.changes = Object.keys(newData).reduce((diff, key) => {
        if (JSON.stringify(oldData[key]) !== JSON.stringify(newData[key])) {
          diff[key] = { old: oldData[key], new: newData[key] };
        }
        return diff;
      }, {});
    }

    await this.log({
      action,
      user_id: userId,
      company_id: companyId,
      entity_type: "faq",
      entity_id: faqId,
      details,
    });
  }

  static async logConversationEvent(
    action,
    conversationId,
    companyId,
    details = {}
  ) {
    await this.log({
      action,
      company_id: companyId,
      entity_type: "conversation",
      entity_id: conversationId,
      details,
    });
  }
}

module.exports = { AuditLogger, AUDIT_EVENTS };
```

### Audit Log Query API

````javascript
// Get audit logs (admin)
app.get('/api/v1/admin/audit-logs', authenticateAdmin, async (req, res) => {
  const { company_id } = req.auth;
  const {
    action,
    entity_type,
    start_date,
    end_date,
    user_id,
    status,
    page = 1,
    limit = 50
  } = req.query;

  try {
    let whereConditions = ['company_id = $1'];
    let params = [company_id];
    let paramIndex = 2;

    if (action) {
      whereConditions.push(`action = ${paramIndex}`);
      params.push(action);
      paramIndex++;
    }

    if (entity_type) {
      whereConditions.push(`entity_type = ${paramIndex}`);
      params.push(entity_type);
      paramIndex++;
    }

    if (start_date) {
      whereConditions.push(`created_at >= ${paramIndex}`);
      params.push(start_date);
      paramIndex++;
    }

    if (end_date) {
      whereConditions.push(`created_at <= ${paramIndex}`);
      params.push(end_date);
      paramIndex++;
    }

    if (user_id) {
      whereConditions.push(`user_id = ${paramIndex}`);
      params.push(user_id);
      paramIndex++;
    }

    if (status) {
      whereConditions.push(`status = ${paramIndex}`);
      params.push(status);
      paramIndex++;
    }

    const offset = (page - 1) * limit;

    // Get total count
    const countQuery = `
      SELECT COUNT(*) as total
      FROM audit_logs
      WHERE ${whereConditions.join(' AND ')}
    `;

    const countResult = await db.query(countQuery, params);
    const total = parseInt(countResult.rows[0].total);

    // Get paginated results
    const logsQuery = `
      SELECT
        id,
        action,
        entity_type,
        entity_id,
        user_id,
        agent_id,
        details,
        ip_address,
        status,
        created_at
      FROM audit_logs
      WHERE ${whereConditions.join(' AND ')}
      ORDER BY created_at DESC
      LIMIT ${paramIndex} OFFSET ${paramIndex + 1}
    `;

    params.push(limit, offset);

    const logs = await db.query(logsQuery, params);

    res.status(200).json({
      success: true,
      data: {
        logs: logs.rows,
        pagination: {
          page: parseInt(page),
          limit: parseInt(limit),
          total,
          pages: Math.ceil(total / limit)
        }
      }
    });
  } catch (error) {
    console.error('Audit log query error:', error);
    res.status(500).json({ error: 'Failed to retrieve audit logs' });
  }
});

// Export audit logs (CSV)
app.get('/api/v1/admin/audit-logs/export', authenticateAdmin, async (req, res) => {
  const { company_id }- Agent messaging interface
- Performance metrics tracking

**Success Criteria**:
- Escalated conversations routed to available agents
- Agents can claim and respond to conversations
- Metrics capture response and resolution times

### Sprint 5 (Weeks 9-10): Attachments & Feedback
**Goal**: File uploads and user feedback

**Deliverables**:
- Tables: `attachments`, `chat_feedback`
- S3 integration with presigned URLs
- Attachment upload/download flow
- Feedback collection API
- Dashboard analytics for feedback

**Success Criteria**:
- Files upload directly to S3 via presigned URLs
- Attachments linked to messages correctly
- Feedback aggregations display accurately

### Sprint 6 (Weeks 11-12): Polish & Production
**Goal**: Optimization, monitoring, and launch prep

**Deliverables**:
- Session cache implementation (Redis)
- Background job monitoring (Bull Board)
- Performance optimization (indexes, query tuning)
- Load testing (target: 100 concurrent chats)
- Security audit and penetration testing
- Documentation and API reference

**Success Criteria**:
- Load tests pass without degradation
- No critical security vulnerabilities
- API documentation complete and accurate

---

## Feature 8: Attachments (S3 File Uploads)

### Business Requirements
- Secure file uploads from users and agents
- Support images, documents, logs (PDF, PNG, JPG, TXT, CSV)
- Storage quota enforcement per plan
- Automatic cleanup of orphaned files
- Virus scanning for uploaded files

### Database Schema

```sql
CREATE TABLE attachments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id UUID REFERENCES messages(id) ON DELETE CASCADE,
  conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  file_name TEXT NOT NULL,
  file_key TEXT NOT NULL,                  -- S3 object key
  file_url TEXT NOT NULL,                  -- CloudFront or S3 public URL
  file_type TEXT NOT NULL,                 -- MIME type
  file_size BIGINT NOT NULL,               -- Bytes
  uploaded_by TEXT NOT NULL,               -- 'user', 'agent'
  uploader_id TEXT,                        -- Agent UUID if applicable
  scan_status TEXT DEFAULT 'pending',      -- 'pending', 'clean', 'infected', 'failed'
  scan_result JSONB,
  is_deleted BOOLEAN DEFAULT FALSE,
  uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  expires_at TIMESTAMP WITH TIME ZONE      -- Optional TTL for temp files
);

CREATE INDEX idx_attachments_message ON attachments(message_id);
CREATE INDEX idx_attachments_conversation ON attachments(conversation_id);
CREATE INDEX idx_attachments_company ON attachments(company_id);
CREATE INDEX idx_attachments_scan_status ON attachments(scan_status);
CREATE INDEX idx_attachments_expires_at ON attachments(expires_at) WHERE expires_at IS NOT NULL;

-- Allowed file types configuration
CREATE TABLE allowed_file_types (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
  mime_type TEXT NOT NULL,
  extension TEXT NOT NULL,
  max_size_mb INT DEFAULT 10,
  is_enabled BOOLEAN DEFAULT TRUE,
  UNIQUE(company_id, mime_type)
);

-- Insert default allowed types
INSERT INTO allowed_file_types (company_id, mime_type, extension, max_size_mb) VALUES
(NULL, 'image/png', 'png', 10),
(NULL, 'image/jpeg', 'jpg', 10),
(NULL, 'image/gif', 'gif', 10),
(NULL, 'application/pdf', 'pdf', 25),
(NULL, 'text/plain', 'txt', 5),
(NULL, 'text/csv', 'csv', 10),
(NULL, 'application/json', 'json', 5);
-- NULL company_id means global default
````

### S3 Setup & Configuration

```javascript
const AWS = require("aws-sdk");

const s3 = new AWS.S3({
  accessKeyId: process.env.AWS_ACCESS_KEY_ID,
  secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY,
  region: process.env.AWS_REGION,
});

const S3_BUCKET = process.env.S3_BUCKET_NAME;
const CLOUDFRONT_DOMAIN = process.env.CLOUDFRONT_DOMAIN; // Optional CDN

// File validation
const ALLOWED_MIME_TYPES = {
  "image/png": { ext: "png", maxSize: 10 * 1024 * 1024 },
  "image/jpeg": { ext: "jpg", maxSize: 10 * 1024 * 1024 },
  "image/gif": { ext: "gif", maxSize: 10 * 1024 * 1024 },
  "application/pdf": { ext: "pdf", maxSize: 25 * 1024 * 1024 },
  "text/plain": { ext: "txt", maxSize: 5 * 1024 * 1024 },
  "text/csv": { ext: "csv", maxSize: 10 * 1024 * 1024 },
  "application/json": { ext: "json", maxSize: 5 * 1024 * 1024 },
};

function validateFileUpload(fileName, fileType, fileSize, companyId) {
  // Check if file type is allowed
  if (!ALLOWED_MIME_TYPES[fileType]) {
    return {
      valid: false,
      error: `File type '${fileType}' not allowed`,
    };
  }

  const typeConfig = ALLOWED_MIME_TYPES[fileType];

  // Check file size
  if (fileSize > typeConfig.maxSize) {
    return {
      valid: false,
      error: `File size exceeds maximum of ${
        typeConfig.maxSize / (1024 * 1024)
      }MB`,
    };
  }

  // Check file extension matches
  const ext = fileName.split(".").pop().toLowerCase();
  if (ext !== typeConfig.ext) {
    return {
      valid: false,
      error: `File extension '.${ext}' doesn't match type '${fileType}'`,
    };
  }

  return { valid: true };
}

// Generate S3 object key with company scoping
function generateFileKey(companyId, conversationId, fileName) {
  const timestamp = Date.now();
  const uuid = require("crypto").randomUUID();
  const sanitizedName = fileName.replace(/[^a-zA-Z0-9.-]/g, "_");

  return `companies/${companyId}/conversations/${conversationId}/${timestamp}_${uuid}_${sanitizedName}`;
}
```

### API Endpoints

#### 1. Request Presigned Upload URL

```
POST /api/v1/uploads/presign
Authorization: Bearer <jwt-token> or X-API-Key: <api-key>
Content-Type: application/json

Request Body:
{
  "conversation_id": "conv-uuid",
  "file_name": "screenshot.png",
  "file_type": "image/png",
  "file_size": 245678
}

Implementation:
```

```javascript
app.post("/api/v1/uploads/presign", authenticate, async (req, res) => {
  const { conversation_id, file_name, file_type, file_size } = req.body;
  const { company_id } = req.auth;

  try {
    // Validate file
    const validation = validateFileUpload(
      file_name,
      file_type,
      file_size,
      company_id
    );
    if (!validation.valid) {
      return res.status(400).json({ error: validation.error });
    }

    // Check storage quota
    const limits = await getPlanLimits(company_id);
    const fileSizeMB = file_size / (1024 * 1024);

    if (limits.current_storage_mb + fileSizeMB > limits.max_storage_mb) {
      return res.status(402).json({
        error: "Storage quota exceeded",
        current: limits.current_storage_mb,
        max: limits.max_storage_mb,
        upgrade_url: "/pricing",
      });
    }

    // Generate S3 key
    const fileKey = generateFileKey(company_id, conversation_id, file_name);

    // Generate presigned URL (valid for 5 minutes)
    const presignedUrl = s3.getSignedUrl("putObject", {
      Bucket: S3_BUCKET,
      Key: fileKey,
      Expires: 300, // 5 minutes
      ContentType: file_type,
      ServerSideEncryption: "AES256",
    });

    // Store pending upload record
    await redis.setex(
      `upload:pending:${fileKey}`,
      600, // 10 minutes TTL
      JSON.stringify({
        company_id,
        conversation_id,
        file_name,
        file_type,
        file_size,
      })
    );

    res.status(200).json({
      success: true,
      data: {
        upload_url: presignedUrl,
        file_key: fileKey,
        expires_in: 300,
      },
    });
  } catch (error) {
    console.error("Presign error:", error);
    res.status(500).json({ error: "Failed to generate upload URL" });
  }
});
```

#### 2. Confirm Upload Completion

```
POST /api/v1/uploads/complete
Authorization: Bearer <jwt-token>
Content-Type: application/json

Request Body:
{
  "message_id": "msg-uuid",
  "conversation_id": "conv-uuid",
  "file_key": "companies/.../timestamp_uuid_screenshot.png",
  "file_name": "screenshot.png",
  "file_type": "image/png",
  "file_size": 245678
}

Implementation:
```

```javascript
app.post("/api/v1/uploads/complete", authenticate, async (req, res) => {
  const {
    message_id,
    conversation_id,
    file_key,
    file_name,
    file_type,
    file_size,
  } = req.body;
  const { company_id } = req.auth;

  try {
    // Verify upload in Redis
    const pendingData = await redis.get(`upload:pending:${file_key}`);
    if (!pendingData) {
      return res.status(400).json({ error: "Upload not found or expired" });
    }

    // Verify file exists in S3
    try {
      await s3
        .headObject({
          Bucket: S3_BUCKET,
          Key: file_key,
        })
        .promise();
    } catch (error) {
      return res.status(400).json({ error: "File not found in storage" });
    }

    // Generate CloudFront or S3 URL
    const fileUrl = CLOUDFRONT_DOMAIN
      ? `https://${CLOUDFRONT_DOMAIN}/${file_key}`
      : `https://${S3_BUCKET}.s3.${process.env.AWS_REGION}.amazonaws.com/${file_key}`;

    // Store attachment record
    const attachment = await db.query(
      `
      INSERT INTO attachments (
        message_id, conversation_id, company_id,
        file_name, file_key, file_url, file_type, file_size,
        uploaded_by, uploader_id
      )
      VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
      RETURNING id, uploaded_at
    `,
      [
        message_id,
        conversation_id,
        company_id,
        file_name,
        file_key,
        fileUrl,
        file_type,
        file_size,
        req.auth.type === "agent" ? "agent" : "user",
        req.auth.type === "agent" ? req.auth.agent_id : null,
      ]
    );

    // Update storage quota
    await db.query(
      `
      UPDATE plan_limits
      SET current_storage_mb = current_storage_mb + $1
      WHERE company_id = $2
    `,
      [file_size / (1024 * 1024), company_id]
    );

    // Queue virus scan
    await queue.add("attachments.scan", {
      attachment_id: attachment.rows[0].id,
      file_key,
    });

    // Clean up Redis
    await redis.del(`upload:pending:${file_key}`);

    // Audit log
    await auditLog.create({
      company_id,
      action: "FILE_UPLOADED",
      details: {
        attachment_id: attachment.rows[0].id,
        file_name,
        file_size,
        conversation_id,
      },
    });

    res.status(201).json({
      success: true,
      data: {
        attachment_id: attachment.rows[0].id,
        file_url: fileUrl,
        uploaded_at: attachment.rows[0].uploaded_at,
      },
    });
  } catch (error) {
    console.error("Upload completion error:", error);
    res.status(500).json({ error: "Failed to complete upload" });
  }
});
```

#### 3. Get Download URL (with access control)

```
GET /api/v1/attachments/:id/download
Authorization: Bearer <jwt-token>

Response (200 OK):
{
  "success": true,
  "data": {
    "download_url": "https://cloudfront.../signed-url",
    "expires_in": 300,
    "file_name": "screenshot.png",
    "file_size": 245678
  }
}

Implementation with CloudFront signed URLs:
```

```javascript
const cloudfront = new AWS.CloudFront.Signer(
  process.env.CLOUDFRONT_KEY_PAIR_ID,
  process.env.CLOUDFRONT_PRIVATE_KEY
);

app.get("/api/v1/attachments/:id/download", authenticate, async (req, res) => {
  const { id: attachment_id } = req.params;
  const { company_id } = req.auth;

  try {
    // Fetch attachment and verify access
    const attachment = await db.query(
      `
      SELECT 
        a.file_key,
        a.file_name,
        a.file_size,
        a.file_url,
        a.scan_status
      FROM attachments a
      JOIN conversations c ON c.id = a.conversation_id
      WHERE a.id = $1 AND c.company_id = $2 AND a.is_deleted = FALSE
    `,
      [attachment_id, company_id]
    );

    if (attachment.rows.length === 0) {
      return res.status(404).json({ error: "Attachment not found" });
    }

    const file = attachment.rows[0];

    // Check scan status
    if (file.scan_status === "infected") {
      return res.status(403).json({ error: "File flagged as malicious" });
    }

    // Generate signed URL (valid for 5 minutes)
    const signedUrl = cloudfront.getSignedUrl({
      url: file.file_url,
      expires: Math.floor(Date.now() / 1000) + 300,
    });

    res.status(200).json({
      success: true,
      data: {
        download_url: signedUrl,
        expires_in: 300,
        file_name: file.file_name,
        file_size: file.file_size,
      },
    });
  } catch (error) {
    console.error("Download URL generation error:", error);
    res.status(500).json({ error: "Failed to generate download URL" });
  }
});
```

### Background Jobs

#### Job: Virus Scanning (ClamAV or AWS S3 antivirus)

```javascript
async function scanAttachment(job) {
  const { attachment_id, file_key } = job.data;

  try {
    // Update scan status
    await db.query(
      `
      UPDATE attachments
      SET scan_status = 'scanning'
      WHERE id = $1
    `,
      [attachment_id]
    );

    // Download file from S3 (stream)
    const s3Object = await s3
      .getObject({
        Bucket: S3_BUCKET,
        Key: file_key,
      })
      .promise();

    // Scan with ClamAV (example using node-clamav)
    const clamav = require("clamav.js");
    const scanResult = await clamav.scanBuffer(s3Object.Body);

    if (scanResult.isInfected) {
      // Mark as infected and delete from S3
      await db.query(
        `
        UPDATE attachments
        SET scan_status = 'infected', scan_result = $1
        WHERE id = $2
      `,
        [JSON.stringify(scanResult), attachment_id]
      );

      await s3
        .deleteObject({
          Bucket: S3_BUCKET,
          Key: file_key,
        })
        .promise();

      // Alert
      await alerting.send({
        level: "warning",
        message: "Infected file detected and removed",
        details: { attachment_id, file_key, virus: scanResult.viruses },
      });
    } else {
      // Mark as clean
      await db.query(
        `
        UPDATE attachments
        SET scan_status = 'clean', scan_result = $1
        WHERE id = $2
      `,
        [JSON.stringify(scanResult), attachment_id]
      );
    }
  } catch (error) {
    console.error("Virus scan failed:", error);

    await db.query(
      `
      UPDATE attachments
      SET scan_status = 'failed', scan_result = $1
      WHERE id = $2
    `,
      [JSON.stringify({ error: error.message }), attachment_id]
    );
  }
}
```

#### Job: Orphaned File Cleanup

```javascript
// Cron: Daily at 2 AM
async function cleanupOrphanedFiles() {
  // Find files uploaded but never linked to a message (> 24 hours old)
  const orphanedKeys = await redis.keys("upload:pending:*");

  for (const key of orphanedKeys) {
    const ttl = await redis.ttl(key);
    if (ttl <= 0) {
      const fileKey = key.replace("upload:pending:", "");

      try {
        // Delete from S3
        await s3
          .deleteObject({
            Bucket: S3_BUCKET,
            Key: fileKey,
          })
          .promise();

        // Remove from Redis
        await redis.del(key);

        console.log(`Cleaned up orphaned file: ${fileKey}`);
      } catch (error) {
        console.error(`Failed to cleanup ${fileKey}:`, error);
      }
    }
  }

  // Find attachments marked for deletion
  const deletedAttachments = await db.query(`
    SELECT file_key
    FROM attachments
    WHERE is_deleted = TRUE
      AND uploaded_at < NOW() - INTERVAL '7 days'
  `);

  for (const attachment of deletedAttachments.rows) {
    try {
      await s3
        .deleteObject({
          Bucket: S3_BUCKET,
          Key: attachment.file_key,
        })
        .promise();

      await db.query(
        `
        DELETE FROM attachments WHERE file_key = $1
      `,
        [attachment.file_key]
      );

      console.log(`Permanently deleted: ${attachment.file_key}`);
    } catch (error) {
      console.error(`Failed to delete ${attachment.file_key}:`, error);
    }
  }
}
```

### Verification Checklist

- [ ] Presigned URLs generated with correct expiry (5 min)
- [ ] File type and size validation enforced
- [ ] Storage quota checked before upload
- [ ] Files upload directly to S3 (no server proxy)
- [ ] Attachment records linked to messages correctly
- [ ] Virus scanning completes within 30 seconds
- [ ] Infected files removed immediately
- [ ] Download URLs require authentication
- [ ] CloudFront signed URLs expire appropriately
- [ ] Orphaned file cleanup runs daily
- [ ] Storage quota updated accurately

---

## Feature 9: Chat Feedback

### Business Requirements

- Collect user satisfaction ratings per conversation
- Thumbs up/down for individual AI responses
- Optional text feedback and comments
- Aggregate metrics for dashboard analytics
- Identify low-performing FAQ answers

### Database Schema

```sql
CREATE TABLE chat_feedback (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  message_id UUID REFERENCES messages(id) ON DELETE CASCADE,  -- Optional: specific message
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  rating SMALLINT CHECK (rating BETWEEN 1 AND 5),            -- 1-5 star rating
  feedback_type TEXT,                                        -- 'thumbs_up', 'thumbs_down', 'star'
  comment TEXT,
  sentiment TEXT,                                            -- 'positive', 'neutral', 'negative'
  user_identifier TEXT,
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_chat_feedback_conversation ON chat_feedback(conversation_id);
CREATE INDEX idx_chat_feedback_message ON chat_feedback(message_id);
CREATE INDEX idx_chat_feedback_company ON chat_feedback(company_id);
CREATE INDEX idx_chat_feedback_rating ON chat_feedback(rating);
CREATE INDEX idx_chat_feedback_created_at ON chat_feedback(created_at);

-- FAQ effectiveness tracking
CREATE TABLE faq_feedback (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  faq_id UUID NOT NULL REFERENCES faqs(id) ON DELETE CASCADE,
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  was_helpful BOOLEAN NOT NULL,
  message_id UUID REFERENCES messages(id) ON DELETE CASCADE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_faq_feedback_faq ON faq_feedback(faq_id);
CREATE INDEX idx_faq_feedback_company ON faq_feedback(company_id);

-- Aggregate metrics view
CREATE MATERIALIZED VIEW feedback_metrics AS
SELECT
  company_id,
  DATE(created_at) as date,
  COUNT(*) as total_responses,
  AVG(rating) as avg_rating,
  COUNT(CASE WHEN rating >= 4 THEN 1 END) as positive_count,
  COUNT(CASE WHEN rating <= 2 THEN 1 END) as negative_count,
  COUNT(CASE WHEN feedback_type = 'thumbs_up' THEN 1 END) as thumbs_up_count,
  COUNT(CASE WHEN feedback_type = 'thumbs_down' THEN 1 END) as thumbs_down_count
FROM chat_feedback
GROUP BY company_id, DATE(created_at);

CREATE INDEX idx_feedback_metrics_company ON feedback_metrics(company_id);
CREATE INDEX idx_feedback_metrics_date ON feedback_metrics(date);

-- Refresh materialized view daily
-- REFRESH MATERIALIZED VIEW CONCURRENTLY feedback_metrics;
```

### API Endpoints

#### 1. Submit Feedback

```
POST /api/v1/feedback
Authorization: Bearer <jwt-token> or X-API-Key: <api-key>
Content-Type: application/json

Request Body:
{
  "conversation_id": "conv-uuid",
  "message_id": "msg-uuid",      // Optional
  "rating": 5,
  "feedback_type": "thumbs_up",
  "comment": "Very helpful response, thank you!"
}

Response (201 Created):
{
  "success": true,
  "data": {
    "feedback_id": "feedback-uuid",
    "created_at": "2025-01-20T10:00:00Z"
  },
  "message": "Thank you for your feedback!"
}
```

```javascript
app.post("/api/v1/feedback", authenticate, async (req, res) => {
  const { conversation_id, message_id, rating, feedback_type, comment } =
    req.body;
  const { company_id, user_identifier } = req.auth;

  try {
    // Validate inputs
    if (rating && (rating < 1 || rating > 5)) {
      return res.status(400).json({ error: "Rating must be between 1 and 5" });
    }

    const validFeedbackTypes = ["thumbs_up", "thumbs_down", "star"];
    if (feedback_type && !validFeedbackTypes.includes(feedback_type)) {
      return res.status(400).json({ error: "Invalid feedback type" });
    }

    // Determine sentiment from rating/feedback_type
    let sentiment = "neutral";
    if (rating) {
      sentiment =
        rating >= 4 ? "positive" : rating <= 2 ? "negative" : "neutral";
    } else if (feedback_type) {
      sentiment = feedback_type === "thumbs_up" ? "positive" : "negative";
    }

    // Store feedback
    const feedback = await db.query(
      `
      INSERT INTO chat_feedback (
        conversation_id, message_id, company_id,
        rating, feedback_type, comment, sentiment, user_identifier
      )
      VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
      RETURNING id, created_at
    `,
      [
        conversation_id,
        message_id || null,
        company_id,
        rating || null,
        feedback_type || null,
        comment || null,
        sentiment,
        user_identifier,
      ]
    );

    // If feedback is for a specific message with FAQ sources, track FAQ effectiveness
    if (message_id) {
      const message = await db.query(
        `
        SELECT metadata
        FROM messages
        WHERE id = $1
      `,
        [message_id]
      );

      if (message.rows.length > 0 && message.rows[0].metadata?.matched_faqs) {
        const matchedFaqs = message.rows[0].metadata.matched_faqs;
        const wasHelpful = sentiment === "positive";

        for (const faqId of matchedFaqs) {
          await db.query(
            `
            INSERT INTO faq_feedback (faq_id, company_id, was_helpful, message_id)
            VALUES ($1, $2, $3, $4)
          `,
            [faqId, company_id, wasHelpful, message_id]
          );
        }
      }
    }

    // Audit log
    await auditLog.create({
      company_id,
      action: "FEEDBACK_SUBMITTED",
      details: {
        feedback_id: feedback.rows[0].id,
        conversation_id,
        rating,
        sentiment,
      },
    });

    res.status(201).json({
      success: true,
      data: {
        feedback_id: feedback.rows[0].id,
        created_at: feedback.rows[0].created_at,
      },
      message: "Thank you for your feedback!",
    });
  } catch (error) {
    console.error("Feedback submission error:", error);
    res.status(500).json({ error: "Failed to submit feedback" });
  }
});
```

#### 2. Get Feedback Analytics (Admin)

```
GET /api/v1/companies/:id/feedback/analytics?start_date=2025-01-01&end_date=2025-01-31
Authorization: Bearer <admin-jwt-token>

Response (200 OK):
{
  "success": true,
  "data": {
    "period": {
      "start_date": "2025-01-01",
      "end_date": "2025-01-31"
    },
    "summary": {
      "total_responses": 1543,
      "avg_rating": 4.2,
      "satisfaction_rate": 0.83,
      "nps_score": 42
    },
    "breakdown": {
      "ratings": {
        "5": 876,
        "4": 412,
        "3": 145,
        "2": 67,
        "1": 43
      },
      "feedback_types": {
        "thumbs_up": 1201,
        "thumbs_down": 342
      }
    },
    "trends": [
      {
        "date": "2025-01-01",
        "avg_rating": 4.1,
        "total_responses": 52
      },
      ...
    ],
    "low_rated_conversations": [
      {
        "conversation_id": "conv-uuid",
        "rating": 1,
        "comment": "AI couldn't answer my question",
        "created_at": "2025-01-15T10:00:00Z"
      }
    ]
  }
}
```

````javascript
app.get('/api/v1/companies/:id/feedback/analytics', authenticateAdmin, async (req, res) => {
  const { id: company_id } = req.params;
  const { start_date, end_date } = req.query;

  try {
    // Summary statistics
    const summary = await db.query(`
      SELECT
        COUNT(*) as total_responses,
        AVG(rating) as avg_rating,
        COUNT(CASE WHEN rating >= 4 THEN 1 END)::FLOAT / COUNT(*) as satisfaction_rate,
        -- NPS: % promoters (5) - % detractors (1-2)
        (COUNT(CASE WHEN rating = 5 THEN 1 END)::FLOAT / COUNT(*) * 100) -
        (COUNT(CASE WHEN rating <= 2 THEN 1 END)::FLOAT / COUNT(*) * 100) as nps_score
      FROM chat_feedback
      WHERE company_id = $1
        AND created_at BETWEEN $2 AND $3
    `, [company_id, start_date, end_date]);

    // Rating breakdown
    const breakdown = await db.query(`
      SELECT
        rating,
        COUNT(*) as count
      FROM chat_feedback
      WHERE company_id = $1
        AND created_at BETWEEN $2 AND $3
        AND rating IS NOT NULL
      GROUP BY rating
      ORDER BY rating DESC
    `, [company_id, start_date, end_date]);

    // Daily trends
    const trends = await db.query(`
      SELECT
        DATE(created_at) as date,
        AVG(rating) as avg_rating,
        COUNT(*) as total_responses
      FROM chat_feedback
      WHERE company_id = $1
        AND created_at BETWEEN $2 AND $3
      GROUP BY DATE(created_at)
      ORDER BY date ASC
    `, [company_id, start_date, end_date]);

    // Low-rated conversations for review
    const lowRated = await db.query(`
      SELECT
        cf.conversation_id,
        cf.rating,
        cf.comment,
        cf.created_at,
        c.user_identifier
      FROM chat_feedback cf
      JOIN conversations c ON c.id = cf.conversation_id
      WHERE cf.company_id = $1
        AND cf.rating <= 2
        AND cf.created_at BETWEEN $2 AND $3
      ORDER BY cf.created_at DESC
      LIMIT 10
    `, [company_id, start_date, end_date]);

    res.status(200).json({
      success: true,
      data: {
        period: { start_date, end_date },
        summary: summary.rows[0],
        breakdown: {
          ratings: Object.fromEntries(
            breakdown.rows.map(r => [r.rating,# Enterprise AI Support Desk Chatbot - Implementation Specification

## Document Overview

**Purpose**: Complete technical specification for building an enterprise-grade AI-powered support desk chatbot SaaS platform.

**Audience**: Engineering teams, AI assistants, and technical stakeholders

**Tech Stack**:
- Database: PostgreSQL 14+ with pgvector extension
- Queue System: Redis + BullMQ
- Storage: AWS S3 / CloudFront
- Auth: JWT + bcrypt/Argon2
- Real-time: Socket.io / WebSocket

---

## Core Conventions & Standards

### Data Standards
- **IDs**: UUID v4 (`gen_random_uuid()`)
- **Timestamps**: `TIMESTAMP WITH TIME ZONE` in UTC
- **Passwords**: bcrypt (cost 12) or Argon2id
- **API Keys**: Show once, store hashed (SHA-256 + salt)
- **Vector Dimensions**: 1536 (OpenAI ada-002 standard)

### Naming Conventions
- Tables: `snake_case` plural (e.g., `users`, `conversations`)
- Columns: `snake_case` (e.g., `created_at`, `user_id`)
- Foreign Keys: `{table}_id` (e.g., `company_id`)
- Indexes: `idx_{table}_{column(s)}` (e.g., `idx_users_email`)

### Security Requirements
- All endpoints require authentication (JWT or API key)
- Rate limiting: 100 req/min per company
- Input sanitization for prompt injection prevention
- Row-Level Security (RLS) for multi-tenancy
- HTTPS only, no exceptions
- CORS policy: whitelist company domains

---

## Implementation Phases

### Phase 1: Foundation (Week 1-2)
Core infrastructure that all features depend on.

**Tables**: `users`, `companies`, `plan_limits`, `audit_logs`

**Critical Path**: Auth → Company Setup → Quota System

---

## Feature 1: Users & Authentication

### Business Requirements
- Secure user registration with email verification
- JWT-based session management
- Password reset via email
- OTP-based account verification
- Audit trail for all auth events

### Database Schema

```sql
-- Users table
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id TEXT UNIQUE NOT NULL,           -- Human-readable: usr_abc123xyz
  first_name TEXT NOT NULL,
  last_name TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,            -- bcrypt cost 12
  otp_hash TEXT,                          -- Temporary, 6-digit
  otp_expires_at TIMESTAMP WITH TIME ZONE,
  is_verified BOOLEAN DEFAULT FALSE,
  is_active BOOLEAN DEFAULT TRUE,
  last_login_at TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_user_id ON users(user_id);
CREATE INDEX idx_users_is_verified ON users(is_verified) WHERE is_verified = FALSE;

-- Trigger for updated_at
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
````

### API Endpoints

#### 1. Register User

```
POST /api/v1/auth/register
Content-Type: application/json

Request Body:
{
  "first_name": "John",
  "last_name": "Doe",
  "email": "john.doe@company.com",
  "password": "SecurePass123!",
  "company_name": "Acme Corp"
}

Response (201 Created):
{
  "success": true,
  "data": {
    "user_id": "usr_abc123xyz",
    "email": "john.doe@company.com",
    "company": {
      "id": "uuid-here",
      "name": "Acme Corp",
      "public_key": "org_xyz789abc"
    },
    "api_key": "sk_live_xxx...xxx"  // SHOWN ONLY ONCE
  },
  "message": "Verification email sent to john.doe@company.com"
}

Error Responses:
- 400: Invalid email format, weak password, missing fields
- 409: Email already registered
- 429: Too many registration attempts
```

#### 2. Login

```
POST /api/v1/auth/login
Content-Type: application/json

Request Body:
{
  "email": "john.doe@company.com",
  "password": "SecurePass123!"
}

Response (200 OK):
{
  "success": true,
  "data": {
    "access_token": "eyJhbGc...",
    "refresh_token": "eyJhbGc...",
    "expires_in": 3600,
    "user": {
      "user_id": "usr_abc123xyz",
      "email": "john.doe@company.com",
      "is_verified": true,
      "company_id": "uuid-here"
    }
  }
}

Error Responses:
- 401: Invalid credentials
- 403: Account not verified
- 429: Too many login attempts (rate limit)
```

#### 3. Verify OTP

```
POST /api/v1/auth/verify-otp
Content-Type: application/json

Request Body:
{
  "email": "john.doe@company.com",
  "otp": "123456"
}

Response (200 OK):
{
  "success": true,
  "message": "Account verified successfully"
}

Error Responses:
- 400: Invalid OTP format
- 401: OTP expired or incorrect
- 404: User not found
```

#### 4. Forgot Password

```
POST /api/v1/auth/forgot-password
Content-Type: application/json

Request Body:
{
  "email": "john.doe@company.com"
}

Response (200 OK):
{
  "success": true,
  "message": "Password reset link sent to your email"
}
```

#### 5. Reset Password

```
POST /api/v1/auth/reset-password
Content-Type: application/json

Request Body:
{
  "token": "reset-token-from-email",
  "new_password": "NewSecurePass123!"
}

Response (200 OK):
{
  "success": true,
  "message": "Password reset successful"
}
```

### Background Actions:

- Check quota: current_faqs < max_faqs
- Insert into faqs table
- Enqueue embedding job: { faq_id, company_id, action: 'create' }
- Audit log: FAQ_CREATED

```

#### 2. Bulk CSV Upload
```

POST /api/v1/faqs/upload
Authorization: Bearer <jwt-token>
Content-Type: multipart/form-data

Form Data:

- file: faqs.csv
- category: "general" (optional, applied to all)
- source: "csv_upload"

CSV Format:
question,answer,category,tags
"How do I reset password?","Click Forgot Password...","account","password,login"
"What are your hours?","We're open 9-5 EST","general","hours,support"

Response (202 Accepted):
{
"success": true,
"data": {
"job_id": "upload-job-uuid",
"rows_processed": 150,
"rows_failed": 3,
"errors": [
{
"row": 45,
"error": "Answer exceeds 10000 characters"
},
{
"row": 78,
"error": "Duplicate question detected"
}
]
},
"message": "CSV upload processing. Embeddings will be generated in background."
}

Implementation:

1. Parse CSV (use papaparse or similar)
2. Validate each row:
   - Required: question, answer
   - Max length: question 500 chars, answer 10000 chars
   - Check for duplicates within file and existing FAQs
3. Batch insert valid rows (transaction)
4. Enqueue bulk embedding job: { faq_ids: [...] }
5. Return summary with errors

```

#### 3. Update FAQ
```

PUT /api/v1/faqs/:id
Authorization: Bearer <jwt-token>
Content-Type: application/json

Request Body:
{
"question": "How do I reset my password? (Updated)",
"answer": "New detailed instructions...",
"category": "account",
"tags": ["password", "login", "security", "help"]
}

Response (200 OK):
{
"success": true,
"data": {
"id": "faq-uuid",
"version": 2,
"updated_at": "2025-01-20T11:30:00Z"
},
"message": "FAQ updated. Re-embedding queued."
}

Background Actions:

- Increment version
- Delete old embedding from faq_embeddings
- Enqueue new embedding job
- Audit log: FAQ_UPDATED with diff

```

#### 4. Delete FAQ
```

DELETE /api/v1/faqs/:id
Authorization: Bearer <jwt-token>

Response (200 OK):
{
"success": true,
"message": "FAQ deleted successfully"
}

Options:

- Soft delete: SET is_active = FALSE
- Hard delete: DELETE FROM faqs (also cascades faq_embeddings)

Background Actions:

- Delete/deactivate FAQ
- Delete associated embeddings
- Decrement current_faqs in plan_limits
- Audit log: FAQ_DELETED

```

#### 5. List FAQs
```

GET /api/v1/faqs?company_id=:id&category=account&search=password&page=1&limit=50
Authorization: Bearer <jwt-token>

Response (200 OK):
{
"success": true,
"data": {
"faqs": [
{
"id": "faq-uuid",
"question": "How do I reset my password?",
"answer": "Click 'Forgot Password'...",
"category": "account",
"tags": ["password", "login"],
"version": 2,
"created_at": "2025-01-20T10:00:00Z",
"updated_at": "2025-01-20T11:30:00Z"
}
],
"pagination": {
"total": 245,
"page": 1,
"limit": 50,
"pages": 5
}
}
}

Query Parameters:

- category: Filter by category
- tags: Filter by tags (comma-separated)
- search: Full-text search on question/answer
- is_active: true/false
- page, limit: Pagination

````

### CSV Parser Implementation

```javascript
const Papa = require('papaparse');

async function parseFAQsCSV(fileBuffer, companyId) {
  return new Promise((resolve, reject) => {
    Papa.parse(fileBuffer.toString(), {
      header: true,
      skipEmptyLines: true,
      complete: async (results) => {
        const validRows = [];
        const errors = [];

        for (let i = 0; i < results.data.length; i++) {
          const row = results.data[i];
          const validation = validateFAQRow(row, i + 2); // +2 for header and 0-index

          if (validation.valid) {
            validRows.push({
              company_id: companyId,
              question: row.question.trim(),
              answer: row.answer.trim(),
              category: row.category?.trim() || 'general',
              tags: row.tags ? row.tags.split(',').map(t => t.trim()) : [],
              source: 'csv_upload',
              version: 1
            });
          } else {
            errors.push({
              row: i + 2,
              error: validation.error
            });
          }
        }

        resolve({ validRows, errors });
      },
      error: (error) => reject(error)
    });
  });
}

function validateFAQRow(row, rowNumber) {
  if (!row.question || row.question.trim().length === 0) {
    return { valid: false, error: 'Question is required' };
  }

  if (!row.answer || row.answer.trim().length === 0) {
    return { valid: false, error: 'Answer is required' };
  }

  if (row.question.length > 500) {
    return { valid: false, error: 'Question exceeds 500 characters' };
  }

  if (row.answer.length > 10000) {
    return { valid: false, error: 'Answer exceeds 10000 characters' };
  }

  return { valid: true };
}

// Bulk insert with transaction
async function bulkInsertFAQs(validRows) {
  const client = await db.getClient();

  try {
    await client.query('BEGIN');

    const insertedIds = [];

    for (const row of validRows) {
      const result = await client.query(`
        INSERT INTO faqs (company_id, question, answer, category, tags, source, version)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id
      `, [row.company_id, row.question, row.answer, row.category, row.tags, row.source, row.version]);

      insertedIds.push(result.rows[0].id);
    }

    // Update quota
    await client.query(`
      UPDATE plan_limits
      SET current_faqs = current_faqs + $1
      WHERE company_id = $2
    `, [insertedIds.length, validRows[0].company_id]);

    await client.query('COMMIT');

    // Enqueue bulk embedding job
    await queue.add('embeddings.bulk_create', {
      faq_ids: insertedIds,
      company_id: validRows[0].company_id
    });

    return insertedIds;

  } catch (error) {
    await client.query('ROLLBACK');
    throw error;
  } finally {
    client.release();
  }
}
````

### Verification Checklist

- [ ] CSV upload accepts standard formats (comma, semicolon delimiters)
- [ ] Invalid rows logged with specific error messages
- [ ] Duplicate detection works (case-insensitive question matching)
- [ ] FAQ CRUD operations trigger embedding jobs correctly
- [ ] Version increment on updates preserves history
- [ ] Soft delete preferred over hard delete for audit trail
- [ ] Full-text search returns relevant results
- [ ] Bulk operations are transactional (all-or-nothing)
- [ ] Quota checks enforce max_faqs limit
- [ ] Tags and categories support filtering

---

## Feature 5: Embeddings Pipeline & Vector Storage

### Business Requirements

- Generate vector embeddings for semantic search
- Support multiple embedding models
- Batch processing for bulk operations
- Retry logic for API failures
- Performance monitoring and optimization

### Database Schema

```sql
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE faq_embeddings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  faq_id UUID UNIQUE NOT NULL REFERENCES faqs(id) ON DELETE CASCADE,
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  embedding vector(1536),                -- 1536 for OpenAI ada-002, adjust per model
  model TEXT NOT NULL,                   -- 'text-embedding-ada-002', 'cohere-embed-v3', etc.
  model_version TEXT,                    -- Track model updates
  token_count INT,                       -- Tokens used for billing
  processing_time_ms INT,                -- Performance monitoring
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for vector similarity search
CREATE INDEX idx_faq_embeddings_company ON faq_embeddings(company_id);
CREATE INDEX idx_faq_embeddings_faq ON faq_embeddings(faq_id);

-- HNSW index for fast approximate nearest neighbor search
CREATE INDEX idx_faq_embeddings_vector ON faq_embeddings
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Alternative: IVFFlat index for larger datasets
-- CREATE INDEX idx_faq_embeddings_vector ON faq_embeddings
-- USING ivfflat (embedding vector_cosine_ops)
-- WITH (lists = 100);

-- Embedding generation queue tracking
CREATE TABLE embedding_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  faq_id UUID NOT NULL REFERENCES faqs(id) ON DELETE CASCADE,
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'pending',  -- pending, processing, completed, failed
  attempts INT DEFAULT 0,
  max_attempts INT DEFAULT 3,
  error TEXT,
  started_at TIMESTAMP WITH TIME ZONE,
  completed_at TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_embedding_jobs_status ON embedding_jobs(status);
CREATE INDEX idx_embedding_jobs_faq ON embedding_jobs(faq_id);
```

### Embedding Generation Worker

```javascript
const { OpenAI } = require("openai");
const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });

const EMBEDDING_MODEL = "text-embedding-ada-002";
const BATCH_SIZE = 100; // OpenAI allows batch embedding
const MAX_RETRIES = 3;
const RETRY_DELAYS = [1000, 5000, 15000]; // Exponential backoff

// Single FAQ embedding
async function generateEmbedding(faqId) {
  const startTime = Date.now();

  try {
    // Update job status
    await db.query(
      `
      UPDATE embedding_jobs
      SET status = 'processing', started_at = NOW(), attempts = attempts + 1
      WHERE faq_id = $1
    `,
      [faqId]
    );

    // Fetch FAQ content
    const faq = await db.query(
      `
      SELECT id, company_id, question, answer
      FROM faqs
      WHERE id = $1
    `,
      [faqId]
    );

    if (faq.rows.length === 0) {
      throw new Error("FAQ not found");
    }

    const { id, company_id, question, answer } = faq.rows[0];

    // Combine question and answer for embedding
    const text = `${question}\n\n${answer}`;

    // Call OpenAI Embeddings API
    const response = await openai.embeddings.create({
      model: EMBEDDING_MODEL,
      input: text,
    });

    const embedding = response.data[0].embedding;
    const processingTime = Date.now() - startTime;

    // Store embedding
    await db.query(
      `
      INSERT INTO faq_embeddings (
        faq_id, company_id, embedding, model, model_version, 
        token_count, processing_time_ms
      )
      VALUES ($1, $2, $3, $4, $5, $6, $7)
      ON CONFLICT (faq_id) DO UPDATE SET
        embedding = EXCLUDED.embedding,
        model = EXCLUDED.model,
        updated_at = NOW()
    `,
      [
        id,
        company_id,
        `[${embedding.join(",")}]`, // pgvector format
        EMBEDDING_MODEL,
        response.model,
        response.usage.total_tokens,
        processingTime,
      ]
    );

    // Mark job as completed
    await db.query(
      `
      UPDATE embedding_jobs
      SET status = 'completed', completed_at = NOW()
      WHERE faq_id = $1
    `,
      [faqId]
    );

    // Audit log
    await auditLog.create({
      company_id,
      action: "EMBEDDING_GENERATED",
      details: {
        faq_id: id,
        model: EMBEDDING_MODEL,
        tokens: response.usage.total_tokens,
        processing_time_ms: processingTime,
      },
    });

    return { success: true, embedding, processingTime };
  } catch (error) {
    console.error(`Embedding generation failed for FAQ ${faqId}:`, error);

    // Check retry attempts
    const job = await db.query(
      `
      SELECT attempts, max_attempts
      FROM embedding_jobs
      WHERE faq_id = $1
    `,
      [faqId]
    );

    if (job.rows[0].attempts >= job.rows[0].max_attempts) {
      // Max retries reached
      await db.query(
        `
        UPDATE embedding_jobs
        SET status = 'failed', error = $1
        WHERE faq_id = $2
      `,
        [error.message, faqId]
      );

      // Alert ops team
      await alerting.send({
        level: "error",
        message: `Embedding generation failed after ${MAX_RETRIES} attempts`,
        details: { faq_id: faqId, error: error.message },
      });
    } else {
      // Retry with exponential backoff
      const delay = RETRY_DELAYS[job.rows[0].attempts - 1] || 15000;
      await queue.add(
        "embeddings.create",
        { faq_id: faqId },
        {
          delay,
          jobId: `embed-${faqId}-attempt-${job.rows[0].attempts + 1}`,
        }
      );
    }

    throw error;
  }
}

// Bulk embedding generation (optimized)
async function generateBulkEmbeddings(faqIds) {
  const batches = [];

  // Split into batches
  for (let i = 0; i < faqIds.length; i += BATCH_SIZE) {
    batches.push(faqIds.slice(i, i + BATCH_SIZE));
  }

  for (const batch of batches) {
    try {
      // Fetch all FAQs in batch
      const faqs = await db.query(
        `
        SELECT id, company_id, question, answer
        FROM faqs
        WHERE id = ANY($1)
      `,
        [batch]
      );

      // Prepare texts
      const texts = faqs.rows.map((faq) => `${faq.question}\n\n${faq.answer}`);

      // Batch API call
      const response = await openai.embeddings.create({
        model: EMBEDDING_MODEL,
        input: texts,
      });

      // Store all embeddings in transaction
      const client = await db.getClient();

      try {
        await client.query("BEGIN");

        for (let i = 0; i < response.data.length; i++) {
          const embedding = response.data[i].embedding;
          const faq = faqs.rows[i];

          await client.query(
            `
            INSERT INTO faq_embeddings (
              faq_id, company_id, embedding, model, token_count
            )
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (faq_id) DO UPDATE SET
              embedding = EXCLUDED.embedding,
              updated_at = NOW()
          `,
            [
              faq.id,
              faq.company_id,
              `[${embedding.join(",")}]`,
              EMBEDDING_MODEL,
              Math.floor(response.usage.total_tokens / texts.length), // Approximate per FAQ
            ]
          );
        }

        await client.query("COMMIT");
      } catch (error) {
        await client.query("ROLLBACK");
        throw error;
      } finally {
        client.release();
      }

      console.log(`Batch embedded: ${batch.length} FAQs`);
    } catch (error) {
      console.error("Bulk embedding batch failed:", error);
      // Fall back to individual processing
      for (const faqId of batch) {
        await queue.add("embeddings.create", { faq_id: faqId });
      }
    }
  }
}
```

### Semantic Search Implementation

```javascript
async function semanticSearch(query, companyId, options = {}) {
  const {
    limit = 5,
    threshold = 0.75, // Minimum similarity score (0-1)
    categoryFilter = null,
  } = options;

  try {
    // Generate embedding for user query
    const queryEmbedding = await openai.embeddings.create({
      model: EMBEDDING_MODEL,
      input: query,
    });

    const embedding = queryEmbedding.data[0].embedding;

    // Similarity search using cosine distance
    // Note: pgvector cosine distance returns 0-2, where 0 = identical
    // We convert to similarity score: similarity = 1 - (distance / 2)
    const results = await db.query(
      `
      SELECT 
        f.id,
        f.question,
        f.answer,
        f.category,
        f.tags,
        f.metadata,
        1 - (e.embedding <=> $1::vector) AS similarity_score
      FROM faq_embeddings e
      JOIN faqs f ON f.id = e.faq_id
      WHERE 
        e.company_id = $2
        AND f.is_active = TRUE
        ${categoryFilter ? "AND f.category = $4" : ""}
        AND 1 - (e.embedding <=> $1::vector) >= $3
      ORDER BY e.embedding <=> $1::vector
      LIMIT ${limit}
    `,
      categoryFilter
        ? [embedding, companyId, threshold, categoryFilter]
        : [embedding, companyId, threshold]
    );

    return results.rows.map((row) => ({
      faq_id: row.id,
      question: row.question,
      answer: row.answer,
      category: row.category,
      tags: row.tags,
      metadata: row.metadata,
      similarity_score: parseFloat(row.similarity_score.toFixed(4)),
      confidence: calculateConfidence(row.similarity_score),
    }));
  } catch (error) {
    console.error("Semantic search failed:", error);
    throw error;
  }
}

// Convert similarity to confidence level
function calculateConfidence(similarityScore) {
  if (similarityScore >= 0.9) return "very_high";
  if (similarityScore >= 0.8) return "high";
  if (similarityScore >= 0.7) return "medium";
  if (similarityScore >= 0.6) return "low";
  return "very_low";
}

// Hybrid search: Combine semantic + keyword search
async function hybridSearch(query, companyId, options = {}) {
  const semanticResults = await semanticSearch(query, companyId, options);

  // Keyword search using PostgreSQL full-text search
  const keywordResults = await db.query(
    `
    SELECT 
      id,
      question,
      answer,
      category,
      ts_rank(to_tsvector('english', question || ' ' || answer), query) as rank
    FROM faqs, plainto_tsquery('english', $1) query
    WHERE 
      company_id = $2
      AND is_active = TRUE
      AND to_tsvector('english', question || ' ' || answer) @@ query
    ORDER BY rank DESC
    LIMIT 5
  `,
    [query, companyId]
  );

  // Merge and deduplicate results
  const mergedResults = [...semanticResults];
  const seenIds = new Set(semanticResults.map((r) => r.faq_id));

  for (const kw of keywordResults.rows) {
    if (!seenIds.has(kw.id)) {
      mergedResults.push({
        faq_id: kw.id,
        question: kw.question,
        answer: kw.answer,
        category: kw.category,
        similarity_score: kw.rank * 0.5, // Scale keyword rank
        confidence: "medium",
        source: "keyword",
      });
    }
  }

  return mergedResults.slice(0, options.limit || 5);
}
```

### Performance Optimization

```sql
-- Regular maintenance for pgvector indexes
-- Run weekly via cron job

-- Vacuum and analyze for better query planning
VACUUM ANALYZE faq_embeddings;

-- Reindex if significant data changes
REINDEX INDEX idx_faq_embeddings_vector;

-- Monitor index usage
SELECT
  schemaname,
  tablename,
  indexname,
  idx_scan,
  idx_tup_read,
  idx_tup_fetch
FROM pg_stat_user_indexes
WHERE tablename = 'faq_embeddings';
```

### API Endpoints

#### 1. Search FAQs (Semantic)

```
POST /api/v1/faqs/search
Authorization: Bearer <jwt-token>
Content-Type: application/json

Request Body:
{
  "query": "How do I change my billing information?",
  "limit": 5,
  "threshold": 0.75,
  "category": "billing"
}

Response (200 OK):
{
  "success": true,
  "data": {
    "query": "How do I change my billing information?",
    "results": [
      {
        "faq_id": "uuid-1",
        "question": "How can I update my payment method?",
        "answer": "Go to Settings > Billing...",
        "category": "billing",
        "similarity_score": 0.9234,
        "confidence": "very_high"
      },
      {
        "faq_id": "uuid-2",
        "question": "Where do I manage my subscription?",
        "answer": "Navigate to Account Settings...",
        "category": "billing",
        "similarity_score": 0.8567,
        "confidence": "high"
      }
    ],
    "processing_time_ms": 145
  }
}
```

#### 2. Regenerate Embeddings (Admin)

```
POST /api/v1/admin/faqs/:id/reembed
Authorization: Bearer <admin-jwt-token>

Response (202 Accepted):
{
  "success": true,
  "message": "Embedding regeneration queued",
  "job_id": "embed-job-uuid"
}
```

### Verification Checklist

- [ ] pgvector extension installed and configured
- [ ] Embedding generation triggered on FAQ create/update
- [ ] Embeddings stored with model metadata and timestamps
- [ ] Retry logic handles transient API failures (3 attempts)
- [ ] Bulk embedding batches requests (100 per call)
- [ ] Semantic search returns relevant results (similarity > 0.75)
- [ ] HNSW index created for fast approximate search
- [ ] Performance monitoring tracks latency and token usage
- [ ] Failed embeddings alert operations team
- [ ] Hybrid search combines semantic + keyword results

---

## Feature 6: Chat System (Conversations & Messages)

### Business Requirements

- Real-time bidirectional communication
- Conversation history persistence
- AI response generation with confidence scoring
- Automatic escalation on low confidence
- Support for multiple concurrent conversations

### Database Schema

```sql
CREATE TABLE conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  user_identifier TEXT NOT NULL,         -- Email, user_id, or anonymous session
  session_id TEXT,                       -- Browser session for anonymous users
  handled_by TEXT DEFAULT 'ai',          -- 'ai' or 'human'
  status TEXT DEFAULT 'open',            -- 'open', 'escalated', 'resolved', 'closed'
  escalation_reason TEXT,                -- Why it was escalated
  metadata JSONB DEFAULT '{}'::jsonb,    -- User agent, IP, location, etc.
  started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  ended_at TIMESTAMP WITH TIME ZONE,
  last_message_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_conversations_company ON conversations(company_id);
CREATE INDEX idx_conversations_status ON conversations(status);
CREATE INDEX idx_conversations_user ON conversations(user_identifier);
CREATE INDEX idx_conversations_company_status ON conversations(company_id, status);

CREATE TABLE messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  sender TEXT NOT NULL,                  -- 'user', 'ai', 'agent'
  sender_id TEXT,                        -- Agent UUID if sender='agent'
  content TEXT NOT NULL,
  content_type TEXT DEFAULT 'text',      -- 'text', 'image', 'file'
  metadata JSONB DEFAULT '{}'::jsonb,    -- Model info, tokens, confidence, etc.
  is_internal BOOLEAN DEFAULT FALSE,     -- Internal notes not shown to user
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_messages_conversation ON messages(conversation_id);
CREATE INDEX idx_messages_created_at ON messages(created_at);
CREATE INDEX idx_messages_sender ON messages(sender);

-- Message metadata structure example:
-- {
--   "model": "gpt-4-turbo",
--   "tokens": { "prompt": 450, "completion": 120 },
--   "confidence_score": 0.89,
--   "matched_faqs": ["faq-uuid-1", "faq-uuid-2"],
--   "processing_time_ms": 1240
-- }
```

### WebSocket Server Implementation

```javascript
const io = require("socket.io")(server, {
  cors: {
    origin: process.env.ALLOWED_ORIGINS.split(","),
    credentials: true,
  },
});

// Authentication middleware
io.use(async (socket, next) => {
  const { public_key, user_identifier } = socket.handshake.auth;

  if (!public_key) {
    return next(new Error("Authentication error: public_key required"));
  }

  // Verify company exists and is active
  const company = await db.query(
    `
    SELECT id, company_name, is_active, plan
    FROM companies
    WHERE public_key = $1
  `,
    [public_key]
  );

  if (company.rows.length === 0 || !company.rows[0].is_active) {
    return next(new Error("Invalid or inactive company"));
  }

  // Check concurrent connection limit
  const activeConnections = await redis.get(
    `connections:${company.rows[0].id}`
  );
  const limits = await getPlanLimits(company.rows[0].id);

  if (activeConnections >= limits.max_concurrent_chats) {
    return next(new Error("Concurrent chat limit reached"));
  }

  socket.company_id = company.rows[0].id;
  socket.user_identifier = user_identifier || `anon_${socket.id}`;

  next();
});

// Connection handler
io.on("connection", async (socket) => {
  console.log(`Client connected: ${socket.id}`);

  // Increment connection count
  await redis.incr(`connections:${socket.company_id}`);

  // Create or resume conversation
  let conversationId = socket.handshake.query.conversation_id;

  if (!conversationId) {
    // New conversation
    const result = await db.query(
      `
      INSERT INTO conversations (company_id, user_identifier, session_id, metadata)
      VALUES ($1, $2, $3, $4)
      RETURNING id
    `,
      [
        socket.company_id,
        socket.user_identifier,
        socket.id,
        { user_agent: socket.handshake.headers["user-agent"] },
      ]
    );

    conversationId = result.rows[0].id;
    socket.emit("conversation_started", { conversation_id: conversationId });
  } else {
    // Resume existing conversation
    const history = await getConversationHistory(conversationId, 20);
    socket.emit("conversation_resumed", {
      conversation_id: conversationId,
      history,
    });
  }

  socket.conversation_id = conversationId;
  socket.join(`conversation:${conversationId}`);

  // Handle incoming messages
  socket.on("user_message", async (data) => {
    await handleUserMessage(socket, data);
  });

  // Handle typing indicator
  socket.on("typing", () => {
    socket.to(`conversation:${conversationId}`).emit("user_typing");
  });

  // Handle disconnection
  socket.on("disconnect", async () => {
    console.log(`Client disconnected: ${socket.id}`);
    await redis.decr(`connections:${socket.company_id}`);
  });
});

// User message handler
async function handleUserMessage(socket, data) {
  const { text, attachments = [] } = data;
  const startTime = Date.now();

  try {
    // Check message quota
    const limits = await getPlanLimits(socket.company_id);
    if (limits.current_messages >= limits.max_messages_per_month) {
      socket.emit("error", {
        code: "QUOTA_EXCEEDED",
        message: "Monthly message limit reached. Please upgrade your plan.",
      });
      return;
    }

    // Store user message
    const userMessage = await db.query(
      `
      INSERT INTO messages (conversation_id, sender, content, metadata)
      VALUES ($1, $2, $3, $4)
      RETURNING id, created_at
    `,
      [socket.conversation_id, "user", text, { attachments }]
    );

    // Update conversation last_message_at
    await db.query(
      `
      UPDATE conversations
      SET last_message_at = NOW()
      WHERE id = $1
    `,
      [socket.conversation_id]
    );

    // Emit user message to other participants (agents)
    socket.to(`conversation:${socket.conversation_id}`).emit("new_message", {
      id: userMessage.rows[0].id,
      sender: "user",
      content: text,
      created_at: userMessage.rows[0].created_at,
    });

    // Generate AI response
    socket.emit("ai_thinking", { status: "processing" });

    const aiResponse = await generateAIResponse(
      socket.company_id,
      socket.conversation_id,
      text
    );

    // Store AI message
    const aiMessage = await db.query(
      `
      INSERT INTO messages (conversation_id, sender, content, metadata)
      VALUES ($1, $2, $3, $4)
      RETURNING id, created_at
    `,
      [
        socket.conversation_id,
        "ai",
        aiResponse.content,
        {
          model: aiResponse.model,
          confidence_score: aiResponse.confidence_score,
          matched_faqs: aiResponse.matched_faqs,
          tokens: aiResponse.tokens,
          processing_time_ms: Date.now() - startTime,
        },
      ]
    );

    // Check if escalation is needed
    if (aiResponse.confidence_score < 0.7) {
      await escalateConversation(
        socket.conversation_id,
        socket.company_id,
        "Low confidence response"
      );

      socket.emit("ai_message", {
        id: aiMessage.rows[0].id,
        content: aiResponse.content,
        confidence: "low",
        escalated: true,
        message:
          "I'm not entirely sure about this answer. A human agent will assist you shortly.",
        created_at: aiMessage.rows[0].created_at,
      });
    } else {
      socket.emit("ai_message", {
        id: aiMessage.rows[0].id,
        content: aiResponse.content,
        confidence: aiResponse.confidence,
        sources: aiResponse.matched_faqs,
        created_at: aiMessage.rows[0].created_at,
      });
    }

    // Increment message quota
    await incrementQuota(socket.company_id, "messages", 1);

    // Audit log
    await auditLog.create({
      company_id: socket.company_id,
      action: "MESSAGE_EXCHANGED",
      details: {
        conversation_id: socket.conversation_id,
        confidence_score: aiResponse.confidence_score,
        escalated: aiResponse.confidence_score < 0.7,
      },
    });
  } catch (error) {
    console.error("Message handling error:", error);
    socket.emit("error", {
      code: "MESSAGE_PROCESSING_FAILED",
      message: "Failed to process your message. Please try again.",
    });
  }
}

// AI Response Generation
async function generateAIResponse(companyId, conversationId, userMessage) {
  const startTime = Date.now();

  try {
    // Step 1: Get conversation context (last 10 messages)
    const context = await db.query(
      `
      SELECT sender, content, created_at
      FROM messages
      WHERE conversation_id = $1
      ORDER BY created_at DESC
      LIMIT 10
    `,
      [conversationId]
    );

    const conversationHistory = context.rows.reverse().map((msg) => ({
      role: msg.sender === "user" ? "user" : "assistant",
      content: msg.content,
    }));

    // Step 2: Semantic search for relevant FAQs
    const relevantFAQs = await semanticSearch(userMessage, companyId, {
      limit: 3,
      threshold: 0.65,
    });

    if (relevantFAQs.length === 0) {
      return {
        content:
          "I couldn't find information about that in our knowledge base. Let me connect you with a human agent who can help.",
        confidence_score: 0.4,
        confidence: "very_low",
        matched_faqs: [],
        model: "none",
        tokens: { prompt: 0, completion: 0 },
      };
    }

    // Step 3: Build prompt with FAQ context
    const faqContext = relevantFAQs
      .map(
        (faq, idx) =>
          `[FAQ ${idx + 1}]\nQ: ${faq.question}\nA: ${faq.answer}\nRelevance: ${
            faq.similarity_score
          }`
      )
      .join("\n\n");

    const systemPrompt = `You are a helpful customer support assistant. Answer the user's question based on the provided FAQ context. If the FAQs don't contain relevant information, politely say so and suggest they speak with a human agent.

FAQ Context:
${faqContext}

Guidelines:
- Be concise and helpful
- Cite the FAQ source when applicable (e.g., "According to our FAQ...")
- If unsure, be honest and offer to escalate
- Maintain a friendly, professional tone`;

    // Step 4: Call LLM
    const completion = await openai.chat.completions.create({
      model: "gpt-4-turbo-preview",
      messages: [
        { role: "system", content: systemPrompt },
        ...conversationHistory,
        { role: "user", content: userMessage },
      ],
      temperature: 0.7,
      max_tokens: 500,
    });

    const aiContent = completion.choices[0].message.content;

    // Step 5: Calculate confidence score
    // Combine semantic similarity and completion finish reason
    const avgSimilarity =
      relevantFAQs.reduce((sum, faq) => sum + faq.similarity_score, 0) /
      relevantFAQs.length;
    const finishReasonPenalty =
      completion.choices[0].finish_reason === "length" ? 0.1 : 0;
    const confidenceScore = Math.max(0, avgSimilarity - finishReasonPenalty);

    return {
      content: aiContent,
      confidence_score: confidenceScore,
      confidence: calculateConfidence(confidenceScore),
      matched_faqs: relevantFAQs.map((f) => f.faq_id),
      model: completion.model,
      tokens: {
        prompt: completion.usage.prompt_tokens,
        completion: completion.usage.completion_tokens,
      },
      processing_time_ms: Date.now() - startTime,
    };
  } catch (error) {
    console.error("AI response generation failed:", error);
    throw error;
  }
}

// Conversation history retrieval
async function getConversationHistory(conversationId, limit = 50) {
  const result = await db.query(
    `
    SELECT 
      m.id,
      m.sender,
      m.sender_id,
      m.content,
      m.content_type,
      m.metadata,
      m.created_at,
      CASE 
        WHEN m.sender = 'agent' THEN sa.agent_name
        ELSE NULL
      END as agent_name
    FROM messages m
    LEFT JOIN support_agents sa ON m.sender_id::uuid = sa.id
    WHERE m.conversation_id = $1
      AND m.is_internal = FALSE
    ORDER BY m.created_at ASC
    LIMIT $2
  `,
    [conversationId, limit]
  );

  return result.rows;
}

// Escalation handler
async function escalateConversation(conversationId, companyId, reason) {
  await db.query(
    `
    UPDATE conversations
    SET 
      handled_by = 'human',
      status = 'escalated',
      escalation_reason = $1
    WHERE id = $2
  `,
    [reason, conversationId]
  );

  // Notify available agents via WebSocket
  io.to(`company:${companyId}:agents`).emit("conversation_escalated", {
    conversation_id: conversationId,
    reason,
    timestamp: new Date().toISOString(),
  });

  // Send webhook notification
  await sendWebhook(companyId, "conversation.escalated", {
    conversation_id: conversationId,
    reason,
  });

  // Audit log
  await auditLog.create({
    company_id: companyId,
    action: "CONVERSATION_ESCALATED",
    details: { conversation_id: conversationId, reason },
  });
}
```

### REST API Endpoints (Alternative to WebSocket)

```javascript
// Start conversation
app.post("/api/v1/chat/start", authenticateAPIKey, async (req, res) => {
  const { user_identifier, metadata } = req.body;

  try {
    const result = await db.query(
      `
      INSERT INTO conversations (company_id, user_identifier, metadata)
      VALUES ($1, $2, $3)
      RETURNING id, started_at
    `,
      [req.company_id, user_identifier, metadata || {}]
    );

    res.status(201).json({
      success: true,
      data: {
        conversation_id: result.rows[0].id,
        started_at: result.rows[0].started_at,
      },
    });
  } catch (error) {
    res.status(500).json({ error: "Failed to start conversation" });
  }
});

// Send message
app.post(
  "/api/v1/chat/:conversation_id/message",
  authenticateAPIKey,
  async (req, res) => {
    const { conversation_id } = req.params;
    const { sender, content } = req.body;

    if (sender !== "user") {
      return res.status(400).json({ error: "Invalid sender" });
    }

    try {
      // Store message
      const userMessage = await db.query(
        `
      INSERT INTO messages (conversation_id, sender, content)
      VALUES ($1, $2, $3)
      RETURNING id, created_at
    `,
        [conversation_id, sender, content]
      );

      // Generate AI response
      const aiResponse = await generateAIResponse(
        req.company_id,
        conversation_id,
        content
      );

      // Store AI response
      const aiMessage = await db.query(
        `
      INSERT INTO messages (conversation_id, sender, content, metadata)
      VALUES ($1, $2, $3, $4)
      RETURNING id, created_at
    `,
        [
          conversation_id,
          "ai",
          aiResponse.content,
          {
            confidence_score: aiResponse.confidence_score,
            matched_faqs: aiResponse.matched_faqs,
            tokens: aiResponse.tokens,
          },
        ]
      );

      res.status(200).json({
        success: true,
        data: {
          user_message: {
            id: userMessage.rows[0].id,
            content,
            created_at: userMessage.rows[0].created_at,
          },
          ai_response: {
            id: aiMessage.rows[0].id,
            content: aiResponse.content,
            confidence: aiResponse.confidence,
            sources: aiResponse.matched_faqs,
            created_at: aiMessage.rows[0].created_at,
          },
        },
      });
    } catch (error) {
      res.status(500).json({ error: "Failed to process message" });
    }
  }
);

// Get conversation history
app.get(
  "/api/v1/chat/:conversation_id/history",
  authenticateAPIKey,
  async (req, res) => {
    const { conversation_id } = req.params;
    const { limit = 50, offset = 0 } = req.query;

    try {
      const history = await getConversationHistory(
        conversation_id,
        limit,
        offset
      );

      res.status(200).json({
        success: true,
        data: {
          conversation_id,
          messages: history,
          total: history.length,
        },
      });
    } catch (error) {
      res.status(500).json({ error: "Failed to retrieve history" });
    }
  }
);

// Close conversation
app.post(
  "/api/v1/chat/:conversation_id/close",
  authenticateAPIKey,
  async (req, res) => {
    const { conversation_id } = req.params;

    try {
      await db.query(
        `
      UPDATE conversations
      SET status = 'closed', ended_at = NOW()
      WHERE id = $1 AND company_id = $2
    `,
        [conversation_id, req.company_id]
      );

      res.status(200).json({
        success: true,
        message: "Conversation closed",
      });
    } catch (error) {
      res.status(500).json({ error: "Failed to close conversation" });
    }
  }
);
```

### Verification Checklist

- [ ] Conversations created and messages persist correctly
- [ ] WebSocket bidirectional communication works
- [ ] JWT/API key authentication enforced on all endpoints
- [ ] AI response pipeline returns relevant answers
- [ ] Confidence scoring triggers escalation at < 0.70 threshold
- [ ] Conversation history retrieval paginated and optimized
- [ ] Concurrent chat limit enforced per company plan
- [ ] Typing indicators and real-time events functional
- [ ] Message quota incremented on each exchange
- [ ] Error handling graceful with user-friendly messages

---

## Feature 7: Escalation & Support Agents

### Business Requirements

- Human agent dashboard for escalated conversations
- Agent assignment and workload distribution
- Internal notes and collaboration
- SLA tracking and metrics
- Agent performance analytics

### Database Schema

```sql
CREATE TABLE support_agents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  agent_name TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT DEFAULT 'agent',              -- 'agent', 'supervisor', 'admin'
  status TEXT DEFAULT 'offline',          -- 'online', 'offline', 'away', 'busy'
  avatar_url TEXT,
  max_concurrent_chats INT DEFAULT 5,
  current_active_chats INT DEFAULT 0,
  is_active BOOLEAN DEFAULT TRUE,
  last_seen_at TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_support_agents_company ON support_agents(company_id);
CREATE INDEX idx_support_agents_email ON support_agents(email);
CREATE INDEX idx_support_agents_status ON support_agents(status) WHERE is_active = TRUE;

CREATE TABLE agent_assignments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  agent_id UUID REFERENCES support_agents(id) ON DELETE SET NULL,
  assigned_by UUID REFERENCES support_agents(id),  -- Who assigned (auto or manual)
  assignment_type TEXT DEFAULT 'manual',   -- 'auto', 'manual', 'claimed'
  assigned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  completed_at TIMESTAMP WITH TIME ZONE,
  status TEXT DEFAULT 'active',            -- 'active', 'transferred', 'completed'
  notes TEXT
);

CREATE INDEX idx_agent_assignments_conversation ON agent_assignments(conversation_id);
CREATE INDEX idx_agent_assignments_agent ON agent_assignments(agent_id);
CREATE INDEX idx_agent_assignments_status ON agent_assignments(status);

-- Agent performance metrics
CREATE TABLE agent_metrics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id UUID NOT NULL REFERENCES support_agents(id) ON DELETE CASCADE,
  date DATE NOT NULL,
  conversations_handled INT DEFAULT 0,
  avg_response_time_seconds INT,
  avg_resolution_time_seconds INT,
  satisfaction_score NUMERIC(3,2),         -- Average from feedback
  messages_sent INT DEFAULT 0,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(agent_id, date)
);

CREATE INDEX idx_agent_metrics_agent ON agent_metrics(agent_id);
CREATE INDEX idx_agent_metrics_date ON agent_metrics(date);
```

### Agent Dashboard API

```javascript
// Agent login
app.post("/api/v1/agents/login", async (req, res) => {
  const { email, password } = req.body;

  try {
    const agent = await db.query(
      `
      SELECT id, agent_name, email, password_hash, company_id, role, is_active
      FROM support_agents
      WHERE email = $1
    `,
      [email]
    );

    if (agent.rows.length === 0) {
      return res.status(401).json({ error: "Invalid credentials" });
    }

    const agentData = agent.rows[0];

    if (!agentData.is_active) {
      return res.status(403).json({ error: "Account deactivated" });
    }

    const validPassword = await bcrypt.compare(
      password,
      agentData.password_hash
    );

    if (!validPassword) {
      return res.status(401).json({ error: "Invalid credentials" });
    }

    // Generate JWT
    const token = jwt.sign(
      {
        agent_id: agentData.id,
        company_id: agentData.company_id,
        role: agentData.role,
        type: "agent",
      },
      process.env.JWT_SECRET,
      { expiresIn: "8h" }
    );

    // Update status to online
    await db.query(
      `
      UPDATE support_agents
      SET status = 'online', last_seen_at = NOW()
      WHERE id = $1
    `,
      [agentData.id]
    );

    res.status(200).json({
      success: true,
      data: {
        token,
        agent: {
          id: agentData.id,
          name: agentData.agent_name,
          email: agentData.email,
          role: agentData.role,
          company_id: agentData.company_id,
        },
      },
    });
  } catch (error) {
    res.status(500).json({ error: "Login failed" });
  }
});

// Get escalated conversations
app.get("/api/v1/agents/conversations", authenticateAgent, async (req, res) => {
  const { status = "escalated", assigned_to_me = false } = req.query;
  const { agent_id, company_id } = req.auth;

  try {
    let query = `
      SELECT 
        c.id,
        c.user_identifier,
        c.status,
        c.escalation_reason,
        c.started_at,
        c.last_message_at,
        aa.agent_id,
        aa.assigned_at,
        sa.agent_name as assigned_agent_name,
        (SELECT content FROM messages WHERE conversation_id = c.id ORDER BY created_at DESC LIMIT 1) as last_message,
        (SELECT COUNT(*) FROM messages WHERE conversation_id = c.id) as message_count
      FROM conversations c
      LEFT JOIN agent_assignments aa ON c.id = aa.conversation_id AND aa.status = 'active'
      LEFT JOIN support_agents sa ON aa.agent_id = sa.id
      WHERE c.company_id = $1
        AND c.status = $2
    `;

    const params = [company_id, status];

    if (assigned_to_me === "true") {
      query += ` AND aa.agent_id = $3`;
      params.push(agent_id);
    }

    query += ` ORDER BY c.last_message_at DESC LIMIT 50`;

    const result = await db.query(query, params);

    res.status(200).json({
      success: true,
      data: {
        conversations: result.rows,
        total: result.rows.length,
      },
    });
  } catch (error) {
    res.status(500).json({ error: "Failed to retrieve conversations" });
  }
});

// Assign/claim conversation
app.post(
  "/api/v1/agents/conversations/:id/assign",
  authenticateAgent,
  async (req, res) => {
    const { id: conversation_id } = req.params;
    const { agent_id: target_agent_id } = req.body; // Optional, defaults to self
    const { agent_id, company_id } = req.auth;

    const assignee = target_agent_id || agent_id;

    try {
      // Check if agent is available
      const agentCheck = await db.query(
        `
      SELECT current_active_chats, max_concurrent_chats, status
      FROM support_agents
      WHERE id = $1 AND company_id = $2
    `,
        [assignee, company_id]
      );

      if (agentCheck.rows.length === 0) {
        return res.status(404).json({ error: "Agent not found" });
      }

      const agent = agentCheck.rows[0];

      if (agent.current_active_chats >= agent.max_concurrent_chats) {
        return res.status(400).json({ error: "Agent at maximum capacity" });
      }

      if (agent.status === "offline") {
        return res.status(400).json({ error: "Agent is offline" });
      }

      // Assign conversation
      await db.query(
        `
      INSERT INTO agent_assignments (conversation_id, agent_id, assigned_by, assignment_type)
      VALUES ($1, $2, $3, $4)
    `,
        [
          conversation_id,
          assignee,
          agent_id,
          target_agent_id ? "manual" : "claimed",
        ]
      );

      // Update agent active chats
      await db.query(
        `
      UPDATE support_agents
      SET current_active_chats = current_active_chats + 1
      WHERE id = $1
    `,
        [assignee]
      );

      // Notify via WebSocket
      io.to(`agent:${assignee}`).emit("conversation_assigned", {
        conversation_id,
        assigned_at: new Date().toISOString(),
      });

      res.status(200).json({
        success: true,
        message: "Conversation assigned successfully",
      });
    } catch (error) {
      res.status(500).json({ error: "Assignment failed" });
    }
  }
);

// Send agent message
app.post(
  "/api/v1/agents/conversations/:id/message",
  authenticateAgent,
  async (req, res) => {
    const { id: conversation_id } = req.params;
    const { content, is_internal = false } = req.body;
    const { agent_id, company_id } = req.auth;

    try {
      // Verify agent is assigned
      const assignment = await db.query(
        `
      SELECT aa.id
      FROM agent_assignments aa
      JOIN conversations c ON c.id = aa.conversation_id
      WHERE aa.conversation_id = $1 
        AND aa.agent_id = $2
        AND aa.status = 'active'
        AND c.company_id = $3
    `,
        [conversation_id, agent_id, company_id]
      );

      if (assignment.rows.length === 0) {
        return res
          .status(403)
          .json({ error: "Not assigned to this conversation" });
      }

      // Store message
      const message = await db.query(
        `
      INSERT INTO messages (conversation_id, sender, sender_id, content, is_internal)
      VALUES ($1, $2, $3, $4, $5)
      RETURNING id, created_at
    `,
        [conversation_id, "agent", agent_id, content, is_internal]
      );

      // Update conversation timestamp
      await db.query(
        `
      UPDATE conversations
      SET last_message_at = NOW()
      WHERE id = $1
    `,
        [conversation_id]
      );

      // Emit to user via WebSocket (if not internal)
      if (!is_internal) {
        io.to(`conversation:${conversation_id}`).emit("agent_message", {
          id: message.rows[0].id,
          content,
          sender: "agent",
          created_at: message.rows[0].created_at,
        });
      }

      res.status(200).json({
        success: true,
        data: {
          message_id: message.rows[0].id,
          created_at: message.rows[0].created_at,
        },
      });
    } catch (error) {
      res.status(500).json({ error: "Failed to send message" });
    }
  }
);

// Close/resolve conversation
app.post(
  "/api/v1/agents/conversations/:id/close",
  authenticateAgent,
  async (req, res) => {
    const { id: conversation_id } = req.params;
    const { resolution_notes } = req.body;
    const { agent_id, company_id } = req.auth;

    try {
      // Update conversation status
      await db.query(
        `
      UPDATE conversations
      SET status = 'resolved', ended_at = NOW()
      WHERE id = $1 AND company_id = $2
    `,
        [conversation_id, company_id]
      );

      // Complete assignment
      await db.query(
        `
      UPDATE agent_assignments
      SET status = 'completed', completed_at = NOW(), notes = $1
      WHERE conversation_id = $2 AND agent_id = $3 AND status = 'active'
    `,
        [resolution_notes, conversation_id, agent_id]
      );

      // Decrement agent active chats
      await db.query(
        `
      UPDATE support_agents
      SET current_active_chats = GREATEST(current_active_chats - 1, 0)
      WHERE id = $1
    `,
        [agent_id]
      );

      // Calculate metrics (response time, resolution time)
      const metrics = await db.query(
        `
      SELECT 
        EXTRACT(EPOCH FROM (NOW() - c.started_at))::INT as resolution_time,
        EXTRACT(EPOCH FROM (MIN(m.created_at) - c.started_at))::INT as first_response_time
      FROM conversations c
      JOIN messages m ON m.conversation_id = c.id AND m.sender = 'agent'
      WHERE c.id = $1
      GROUP BY c.started_at
    `,
        [conversation_id]
      );

      // Update agent metrics
      if (metrics.rows.length > 0) {
        await db.query(
          `
        INSERT INTO agent_metrics (agent_id, date, conversations_handled, avg_response_time_seconds, avg_resolution_time_seconds)
        VALUES ($1, CURRENT_DATE, 1, $2, $3)
        ON CONFLICT (agent_id, date) DO UPDATE SET
          conversations_handled = agent_metrics.conversations_handled + 1,
          avg_response_time_seconds = (agent_metrics.avg_response_time_seconds * agent_metrics.conversations_handled + $2) / (agent_metrics.conversations_handled + 1),
          avg_resolution_time_seconds = (agent_metrics.avg_resolution_time_seconds * agent_metrics.conversations_handled + $3) / (agent_metrics.conversations_handled + 1)
      `,
          [
            agent_id,
            metrics.rows[0].first_response_time,
            metrics.rows[0].resolution_time,
          ]
        );
      }

      res.status(200).json({
        success: true,
        message: "Conversation closed and resolved",
      });
    } catch (error) {
      res.status(500).json({ error: "Failed to close conversation" });
    }
  }
);
```

### Auto-Assignment Algorithm

```javascript
async function autoAssignConversation(conversationId, companyId) {
  try {
    // Find available agent with lowest current workload
    const availableAgent = await db.query(
      `
      SELECT id, agent_name, current_active_chats, max_concurrent_chats
      FROM support_agents
      WHERE company_id = $1
        AND is_active = TRUE
        AND status IN ('online', 'away')
        AND current_active_chats < max_concurrent_chats
      ORDER BY 
        CASE WHEN status = 'online' THEN 0 ELSE 1 END,
        current_active_chats ASC,
        last_seen_at DESC
      LIMIT 1
    `,
      [companyId]
    );

    if (availableAgent.rows.length === 0) {
      // No agents available, keep in queue
      await sendWebhook(companyId, "conversation.no_agent_available", {
        conversation_id: conversationId,
      });
      return null;
    }

    const agent = availableAgent.rows[0];

    // Assign to agent
    await db.query(
      `
      INSERT INTO agent_assignments (conversation_id, agent_id, assignment_type)
      VALUES ($1, $2, 'auto')
    `,
      [conversationId, agent.id]
    );

    await db.query(
      `
      UPDATE support_agents
      SET current_active_chats = current_active_chats + 1
      WHERE id = $1
    `,
      [agent.id]
    );

    // Notify agent
    io.to(`agent:${agent.id}`).emit("conversation_assigned", {
      conversation_id: conversationId,
      assignment_type: "auto",
    });

    return agent;
  } catch (error) {
    console.error("Auto-assignment failed:", error);
    return null;
  }
}
```

### Verification Checklist

- [ ] Agents can authenticate and access dashboard
- [ ] Escalated conversations appear in agent queue
- [ ] Assignment workflow (auto and manual) functions correctly
- [ ] Agent capacity limits enforced (max_concurrent_chats)
- [ ] Agent messages delivered to end users via WebSocket
- [ ] Internal notes visible only to agents, not users
- [ ] Conversation closure updates agent metrics
- [ ] Response time and resolution time calculated accurately
- [ ] Agent status updates (online, offline, away, busy) work
- [ ] Performance dashboard shows aggregated metrics

---

## Implementation Roadmap

### Sprint 1 (Weeks 1-2): Foundation

**Goal**: Core infrastructure and authentication

**Deliverables**:

- Database setup (PostgreSQL + pgvector)
- Tables: `users`, `companies`, `plan_limits`, `audit_logs`
- Auth endpoints (register, login, OTP verification)
- API key generation and verification
- JWT middleware

**Success Criteria**:

- Users can register and verify accounts
- Company created with public_key and api_key
- Authentication working end-to-end

### Sprint 2 (Weeks 3-4): Knowledge Base

**Goal**: FAQ management and embeddings

**Deliverables**:

- Tables: `faqs`, `faq_embeddings`, `faq_categories`
- FAQ CRUD endpoints
- CSV upload with validation
- Embedding generation worker (OpenAI integration)
- Semantic search implementation

**Success Criteria**:

- CSV upload processes 1000+ FAQs successfully
- Embeddings generated within 5 seconds per FAQ
- Semantic search returns relevant results

### Sprint 3 (Weeks 5-6): Chat System

**Goal**: Real-time conversations with AI responses

**Deliverables**:

- Tables: `conversations`, `messages`
- WebSocket server setup
- REST API for chat (fallback)
- AI response pipeline with confidence scoring
- Quota enforcement middleware

**Success Criteria**:

- Users can start conversations and receive AI responses
- Confidence-based escalation triggers correctly
- Concurrent chat limits enforced

### Sprint 4 (Weeks 7-8): Human Support

**Goal**: Agent dashboard and escalation workflow

**Deliverables**:

- Tables: `support_agents`, `agent_assignments`, `agent_metrics`
- Agent authentication and dashboard API
- Assignment workflow (auto + manual)
- Agent messaging interface Jobs

#### Job: Send Verification Email

```javascript
// Queue: email.verification
{
  jobId: 'unique-id',
  data: {
    email: 'john.doe@company.com',
    otp: '123456',
    user_name: 'John Doe'
  },
  attempts: 3,
  backoff: { type: 'exponential', delay: 2000 }
}

// Implementation
async function sendVerificationEmail(job) {
  const { email, otp, user_name } = job.data;

  await emailService.send({
    to: email,
    template: 'verification',
    data: {
      name: user_name,
      otp: otp,
      expires_in: '10 minutes'
    }
  });

  await auditLog.create({
    action: 'EMAIL_SENT',
    details: { type: 'verification', recipient: email }
  });
}
```

### Security Implementation

#### Password Hashing

```javascript
const bcrypt = require("bcrypt");
const SALT_ROUNDS = 12;

async function hashPassword(plainPassword) {
  return await bcrypt.hash(plainPassword, SALT_ROUNDS);
}

async function verifyPassword(plainPassword, hash) {
  return await bcrypt.compare(plainPassword, hash);
}
```

#### JWT Token Generation

```javascript
const jwt = require("jsonwebtoken");

function generateTokens(userId, companyId) {
  const accessToken = jwt.sign(
    {
      user_id: userId,
      company_id: companyId,
      type: "access",
    },
    process.env.JWT_SECRET,
    { expiresIn: "1h" }
  );

  const refreshToken = jwt.sign(
    {
      user_id: userId,
      type: "refresh",
    },
    process.env.JWT_REFRESH_SECRET,
    { expiresIn: "7d" }
  );

  return { accessToken, refreshToken };
}
```

#### OTP Generation

```javascript
function generateOTP() {
  return Math.floor(100000 + Math.random() * 900000).toString();
}

async function hashOTP(otp) {
  return await bcrypt.hash(otp, 10);
}
```

### Validation Rules

```javascript
const PASSWORD_REQUIREMENTS = {
  minLength: 8,
  requireUppercase: true,
  requireLowercase: true,
  requireNumber: true,
  requireSpecial: true,
};

function validatePassword(password) {
  if (password.length < PASSWORD_REQUIREMENTS.minLength) {
    throw new Error("Password must be at least 8 characters");
  }
  if (!/[A-Z]/.test(password)) {
    throw new Error("Password must contain uppercase letter");
  }
  if (!/[a-z]/.test(password)) {
    throw new Error("Password must contain lowercase letter");
  }
  if (!/[0-9]/.test(password)) {
    throw new Error("Password must contain number");
  }
  if (!/[!@#$%^&*]/.test(password)) {
    throw new Error("Password must contain special character");
  }
}
```

### Verification Checklist

- [ ] User registration creates both `users` and `companies` records atomically
- [ ] JWT tokens issued with correct expiry and claims
- [ ] Passwords hashed with bcrypt cost 12 minimum
- [ ] OTP emails sent within 5 seconds of registration
- [ ] OTP expiry enforced (10 minutes default)
- [ ] Account verification toggles `is_verified` flag
- [ ] Password reset tokens expire after 1 hour
- [ ] Rate limiting prevents brute force (5 attempts/15 min)
- [ ] All auth actions logged to `audit_logs`
- [ ] Unit tests cover all validation logic
- [ ] Integration tests verify email delivery

---

## Feature 2: Companies & API Keys

### Business Requirements

- Unique public key for frontend integration
- Secure API key for backend operations
- Key rotation without service interruption
- Company metadata management
- Webhook configuration support

### Database Schema

```sql
CREATE TABLE companies (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  company_name TEXT NOT NULL,
  public_key TEXT UNIQUE NOT NULL,        -- org_xyz123abc (safe for frontend)
  api_key_hash TEXT UNIQUE NOT NULL,      -- SHA-256 hashed sk_live_xxx
  support_email TEXT,
  support_phone TEXT,
  plan TEXT DEFAULT 'free',               -- free, starter, professional, enterprise
  webhook_url TEXT,
  webhook_secret TEXT,                    -- For HMAC verification
  is_active BOOLEAN DEFAULT TRUE,
  settings JSONB DEFAULT '{}'::jsonb,     -- Company preferences
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_companies_user_id ON companies(user_id);
CREATE INDEX idx_companies_public_key ON companies(public_key);
CREATE INDEX idx_companies_plan ON companies(plan);
CREATE INDEX idx_companies_is_active ON companies(is_active) WHERE is_active = TRUE;

-- Settings JSONB structure example:
-- {
--   "branding": {
--     "primary_color": "#007bff",
--     "logo_url": "https://cdn.example.com/logo.png"
--   },
--   "chatbot": {
--     "greeting_message": "Hello! How can I help?",
--     "confidence_threshold": 0.75
--   }
-- }
```

### API Key Generation

```javascript
const crypto = require("crypto");

// Generate public key: org_<16-char-hash>
function generatePublicKey() {
  const randomBytes = crypto.randomBytes(12);
  const hash = randomBytes.toString("base64url").substring(0, 16);
  return `org_${hash}`;
}

// Generate API key: sk_live_<48-char-random>
function generateAPIKey() {
  const randomBytes = crypto.randomBytes(36);
  const key = randomBytes.toString("base64url").substring(0, 48);
  return `sk_live_${key}`;
}

// Hash API key for storage
function hashAPIKey(apiKey) {
  return crypto
    .createHash("sha256")
    .update(apiKey + process.env.API_KEY_SALT)
    .digest("hex");
}

// Constant-time comparison to prevent timing attacks
function verifyAPIKey(providedKey, storedHash) {
  const providedHash = hashAPIKey(providedKey);
  return crypto.timingSafeEqual(
    Buffer.from(storedHash, "hex"),
    Buffer.from(providedHash, "hex")
  );
}
```

### API Endpoints

#### 1. Get Company Info (Public)

```
GET /api/v1/companies/:public_key
No authentication required (public endpoint)

Response (200 OK):
{
  "success": true,
  "data": {
    "id": "uuid-here",
    "company_name": "Acme Corp",
    "public_key": "org_xyz123abc",
    "support_email": "support@acmecorp.com",
    "branding": {
      "primary_color": "#007bff",
      "logo_url": "https://cdn.acmecorp.com/logo.png"
    }
  }
}

Note: Never exposes api_key_hash, webhook_secret, or internal settings
```

#### 2. Get Company Details (Admin)

```
GET /api/v1/companies/:id
Authorization: Bearer <jwt-token>

Response (200 OK):
{
  "success": true,
  "data": {
    "id": "uuid-here",
    "user_id": "usr_abc123",
    "company_name": "Acme Corp",
    "public_key": "org_xyz123abc",
    "support_email": "support@acmecorp.com",
    "plan": "professional",
    "webhook_url": "https://acmecorp.com/webhooks/support",
    "is_active": true,
    "settings": { ... },
    "created_at": "2025-01-01T00:00:00Z",
    "updated_at": "2025-01-15T10:30:00Z"
  }
}
```

#### 3. Rotate API Key

```
POST /api/v1/companies/:id/rotate-api-key
Authorization: Bearer <jwt-token>
Content-Type: application/json

Request Body:
{
  "reason": "Suspected compromise"  // Optional, for audit log
}

Response (200 OK):
{
  "success": true,
  "data": {
    "api_key": "sk_live_new_key_here"  // SHOWN ONLY ONCE
  },
  "message": "API key rotated successfully. Old key invalidated immediately."
}

Implementation Notes:
- Old API key invalidated instantly (update api_key_hash)
- Audit log records: OLD_KEY_ROTATED with timestamp
- Email notification sent to company admin
- Grace period NOT recommended for security
```

#### 4. Update Company Settings

```
PATCH /api/v1/companies/:id
Authorization: Bearer <jwt-token>
Content-Type: application/json

Request Body:
{
  "company_name": "Acme Corporation",
  "support_email": "help@acmecorp.com",
  "webhook_url": "https://acmecorp.com/new-webhook",
  "settings": {
    "branding": {
      "primary_color": "#ff6600"
    }
  }
}

Response (200 OK):
{
  "success": true,
  "data": { /* updated company object */ }
}
```

### Webhook Implementation

```javascript
// Webhook payload structure
const webhookPayload = {
  event: "conversation.escalated",
  timestamp: new Date().toISOString(),
  company_id: "uuid-here",
  data: {
    conversation_id: "conv-uuid",
    reason: "Low confidence response",
    user_identifier: "user@example.com",
  },
};

// Sign webhook for verification
function signWebhook(payload, secret) {
  const hmac = crypto.createHmac("sha256", secret);
  hmac.update(JSON.stringify(payload));
  return hmac.digest("hex");
}

// Send webhook with retry
async function sendWebhook(companyId, event, data) {
  const company = await getCompany(companyId);

  if (!company.webhook_url) return;

  const payload = {
    event,
    timestamp: new Date().toISOString(),
    company_id: companyId,
    data,
  };

  const signature = signWebhook(payload, company.webhook_secret);

  await queue.add(
    "webhooks.send",
    {
      url: company.webhook_url,
      payload,
      headers: {
        "X-Webhook-Signature": signature,
        "X-Webhook-Event": event,
      },
    },
    {
      attempts: 3,
      backoff: { type: "exponential", delay: 5000 },
    }
  );
}
```

### Verification Checklist

- [ ] Public key is unpredictable and collision-resistant
- [ ] API key shown only once at creation/rotation
- [ ] API key stored as SHA-256 hash, never plaintext
- [ ] Constant-time comparison prevents timing attacks
- [ ] Admin can rotate keys; old keys invalidate immediately
- [ ] Public endpoint only returns non-sensitive company data
- [ ] Webhook signatures use HMAC-SHA256
- [ ] Webhook delivery has retry logic (3 attempts, exponential backoff)
- [ ] Key rotation triggers audit log and email notification
- [ ] Settings JSONB validated against schema

---

## Feature 3: Plan Limits & Quotas

### Business Requirements

- Enforce usage limits per plan tier
- Track consumption in real-time
- Monthly quota reset automation
- Graceful handling of limit exceeded
- Admin override capability

### Database Schema

```sql
CREATE TABLE plan_limits (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID UNIQUE NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  plan TEXT NOT NULL DEFAULT 'free',

  -- Limits (maximums)
  max_messages_per_month INT NOT NULL DEFAULT 1000,
  max_faqs INT NOT NULL DEFAULT 100,
  max_storage_mb INT NOT NULL DEFAULT 100,
  max_agents INT NOT NULL DEFAULT 1,
  max_concurrent_chats INT NOT NULL DEFAULT 10,

  -- Current usage
  current_messages INT NOT NULL DEFAULT 0,
  current_faqs INT NOT NULL DEFAULT 0,
  current_storage_mb NUMERIC(10,2) NOT NULL DEFAULT 0,
  current_agents INT NOT NULL DEFAULT 0,

  -- Billing cycle
  reset_date DATE NOT NULL,
  last_reset_at TIMESTAMP WITH TIME ZONE,

  -- Metadata
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

  CONSTRAINT chk_current_lte_max CHECK (
    current_messages <= max_messages_per_month AND
    current_faqs <= max_faqs AND
    current_storage_mb <= max_storage_mb AND
    current_agents <= max_agents
  )
);

-- Indexes
CREATE INDEX idx_plan_limits_company ON plan_limits(company_id);
CREATE INDEX idx_plan_limits_reset_date ON plan_limits(reset_date);
CREATE INDEX idx_plan_limits_plan ON plan_limits(plan);

-- Plan tiers configuration
CREATE TABLE plan_tiers (
  plan TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  price_monthly NUMERIC(10,2) NOT NULL,
  max_messages_per_month INT NOT NULL,
  max_faqs INT NOT NULL,
  max_storage_mb INT NOT NULL,
  max_agents INT NOT NULL,
  max_concurrent_chats INT NOT NULL,
  features JSONB NOT NULL DEFAULT '{}'::jsonb,
  is_active BOOLEAN DEFAULT TRUE
);

-- Insert default plans
INSERT INTO plan_tiers (plan, display_name, price_monthly, max_messages_per_month, max_faqs, max_storage_mb, max_agents, max_concurrent_chats, features) VALUES
('free', 'Free', 0, 1000, 100, 100, 1, 5, '{"priority_support": false, "custom_branding": false, "api_access": false}'::jsonb),
('starter', 'Starter', 29, 10000, 500, 1000, 3, 20, '{"priority_support": false, "custom_branding": true, "api_access": true}'::jsonb),
('professional', 'Professional', 99, 50000, 2000, 5000, 10, 50, '{"priority_support": true, "custom_branding": true, "api_access": true}'::jsonb),
('enterprise', 'Enterprise', 499, -1, -1, -1, -1, -1, '{"priority_support": true, "custom_branding": true, "api_access": true, "dedicated_support": true}'::jsonb);
-- -1 indicates unlimited
```

### Quota Enforcement Middleware

```javascript
// Middleware: Check quota before operation
async function checkQuota(req, res, next) {
  const { company_id } = req.auth;
  const quotaType = req.quotaType; // Set by route: 'messages', 'faqs', 'storage'

  try {
    const limits = await db.query(
      `
      SELECT 
        max_${quotaType}_per_month as max_limit,
        current_${quotaType} as current_usage
      FROM plan_limits
      WHERE company_id = $1
      FOR UPDATE  -- Lock row to prevent race conditions
    `,
      [company_id]
    );

    if (limits.rows.length === 0) {
      return res.status(500).json({
        error: "Plan limits not configured",
      });
    }

    const { max_limit, current_usage } = limits.rows[0];

    // -1 means unlimited (enterprise)
    if (max_limit !== -1 && current_usage >= max_limit) {
      return res.status(429).json({
        error: "Quota exceeded",
        details: {
          quota_type: quotaType,
          current_usage,
          max_limit,
          reset_date: limits.rows[0].reset_date,
        },
        upgrade_url: "/pricing",
      });
    }

    req.quota = { current_usage, max_limit };
    next();
  } catch (error) {
    console.error("Quota check failed:", error);
    res.status(500).json({ error: "Internal server error" });
  }
}

// Usage in routes
app.post(
  "/api/chat/message",
  authenticateJWT,
  setQuotaType("messages"),
  checkQuota,
  handleChatMessage
);
```

### Quota Increment Function

```javascript
async function incrementQuota(companyId, quotaType, delta = 1) {
  const column = `current_${quotaType}`;

  const result = await db.query(
    `
    UPDATE plan_limits
    SET 
      ${column} = ${column} + $1,
      updated_at = NOW()
    WHERE company_id = $2
    RETURNING ${column}, max_${quotaType}_per_month
  `,
    [delta, companyId]
  );

  if (result.rows.length === 0) {
    throw new Error("Company plan limits not found");
  }

  // Log to audit
  await auditLog.create({
    company_id: companyId,
    action: "QUOTA_INCREMENT",
    details: {
      quota_type: quotaType,
      delta,
      new_value: result.rows[0][column],
    },
  });

  return result.rows[0];
}
```

### API Endpoints

#### 1. Get Current Usage

```
GET /api/v1/companies/:id/usage
Authorization: Bearer <jwt-token>

Response (200 OK):
{
  "success": true,
  "data": {
    "plan": "professional",
    "billing_cycle": {
      "reset_date": "2025-02-01",
      "days_remaining": 12
    },
    "quotas": {
      "messages": {
        "used": 3450,
        "limit": 50000,
        "percentage": 6.9
      },
      "faqs": {
        "used": 250,
        "limit": 2000,
        "percentage": 12.5
      },
      "storage_mb": {
        "used": 1245.67,
        "limit": 5000,
        "percentage": 24.9
      },
      "agents": {
        "used": 5,
        "limit": 10,
        "percentage": 50
      }
    }
  }
}
```

#### 2. Admin: Adjust Plan

```
POST /api/v1/admin/companies/:id/plan
Authorization: Bearer <admin-jwt-token>
Content-Type: application/json

Request Body:
{
  "plan": "enterprise",
  "reason": "Upgrade request"
}

Response (200 OK):
{
  "success": true,
  "message": "Plan upgraded to enterprise",
  "data": {
    "old_plan": "professional",
    "new_plan": "enterprise",
    "effective_date": "2025-01-20T00:00:00Z"
  }
}
```

#### 3. Admin: Manual Quota Adjustment

```
POST /api/v1/admin/companies/:id/quota/adjust
Authorization: Bearer <admin-jwt-token>
Content-Type: application/json

Request Body:
{
  "quota_type": "messages",
  "adjustment": 5000,
  "reason": "Goodwill credit for downtime"
}

Response (200 OK):
{
  "success": true,
  "data": {
    "quota_type": "messages",
    "old_limit": 50000,
    "new_limit": 55000,
    "adjustment": 5000
  }
}
```

### Background Jobs

#### Job: Monthly Quota Reset

```javascript
// Cron: 0 0 1 * * (First day of month, midnight UTC)
async function resetMonthlyQuotas() {
  const today = new Date();

  const result = await db.query(
    `
    UPDATE plan_limits
    SET 
      current_messages = 0,
      current_storage_mb = 0,
      last_reset_at = NOW(),
      reset_date = $1,
      updated_at = NOW()
    WHERE reset_date <= $2
    RETURNING company_id, plan
  `,
    [
      new Date(today.getFullYear(), today.getMonth() + 1, 1), // Next reset
      today,
    ]
  );

  // Audit log
  for (const row of result.rows) {
    await auditLog.create({
      company_id: row.company_id,
      action: "QUOTA_RESET",
      details: {
        plan: row.plan,
        reset_date: today.toISOString(),
      },
    });
  }

  console.log(`Reset quotas for ${result.rowCount} companies`);
}
```

### Verification Checklist

- [ ] Plan limits created automatically on company registration
- [ ] Quota checks are atomic (use `FOR UPDATE` locks)
- [ ] 429 response includes actionable upgrade information
- [ ] Monthly reset job runs reliably (monitor cron execution)
- [ ] Enterprise plan (-1 limits) bypasses all checks
- [ ] Quota increment logs to audit trail
- [ ] Admin can manually adjust quotas with reason tracking
- [ ] Storage quota calculated accurately (sum of attachments)
- [ ] Concurrent chat limit enforced at websocket connection
- [ ] Grace period handled (e.g., 10% overage allowed)

---

## Feature 4: FAQ Management

### Business Requirements

- CRUD operations for company knowledge base
- Bulk CSV upload with validation
- Version control for FAQ edits
- Automatic embedding generation trigger
- FAQ categorization and tagging

### Database Schema

```sql
CREATE TABLE faqs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  question TEXT NOT NULL,
  answer TEXT NOT NULL,
  category TEXT,                          -- e.g., 'billing', 'technical', 'general'
  tags TEXT[] DEFAULT '{}',               -- Searchable tags
  source TEXT DEFAULT 'manual',           -- 'manual', 'csv_upload', 'api', 'import'
  version INT NOT NULL DEFAULT 1,
  is_active BOOLEAN DEFAULT TRUE,
  priority INT DEFAULT 0,                 -- Higher = shown first in ties
  metadata JSONB DEFAULT '{}'::jsonb,     -- Custom fields, links, etc.
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  created_by UUID REFERENCES users(id),
  updated_by UUID REFERENCES users(id)
);

-- Indexes
CREATE INDEX idx_faqs_company ON faqs(company_id);
CREATE INDEX idx_faqs_active ON faqs(is_active) WHERE is_active = TRUE;
CREATE INDEX idx_faqs_category ON faqs(category);
CREATE INDEX idx_faqs_tags ON faqs USING GIN(tags);
CREATE INDEX idx_faqs_company_active ON faqs(company_id, is_active) WHERE is_active = TRUE;

-- Full-text search index (optional, for keyword search)
CREATE INDEX idx_faqs_fulltext ON faqs USING GIN(
  to_tsvector('english', question || ' ' || answer)
);

-- FAQ categories lookup
CREATE TABLE faq_categories (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(company_id, name)
);
```

### API Endpoints

#### 1. Create FAQ

```
POST /api/v1/faqs
Authorization: Bearer <jwt-token>
Content-Type: application/json

Request Body:
{
  "question": "How do I reset my password?",
  "answer": "Click 'Forgot Password' on the login page and follow the email instructions.",
  "category": "account",
  "tags": ["password", "login", "security"],
  "priority": 5
}

Response (201 Created):
{
  "success": true,
  "data": {
    "id": "faq-uuid",
    "question": "How do I reset my password?",
    "answer": "Click 'Forgot Password'...",
    "category": "account",
    "tags": ["password", "login", "security"],
    "version": 1,
    "is_active": true,
    "created_at": "2025-01-20T10:00:00Z"
  },
  "message": "FAQ created. Embedding generation queued."
}

Backgroun
```
