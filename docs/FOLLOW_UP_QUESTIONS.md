# Follow-Up Questions & Session Management Documentation

This document explains the follow-up question feature and session-based conversation context management.

## Overview

The Nithub QA API supports intelligent conversation flow with automatic session management:

1. **Automatic session management** - Short session IDs for tracking conversations
2. **Generating follow-up questions** - Automatically generated after each answer
3. **Automatic context attachment** - Backend automatically handles related questions within a session
4. **Session timeout** - Sessions expire after 15 minutes of inactivity

## Features

### 1. Automatic Follow-Up Question Generation

After answering any question, the system automatically generates a relevant follow-up question based on:

- The answer provided
- The knowledge base context used
- Natural conversation flow

The follow-up question is included in the response and stored in the database.

### 2. Session-Based Context Management

The system uses short session IDs (8 characters) to track conversations:

- **Automatic session creation**: First request creates a new session
- **Session tracking**: Backend stores previous question/answer and follow-up in memory
- **Automatic context**: When a question is sent with a `session_id`, backend automatically checks if it's related to previous questions in that session
- **No frontend storage needed**: Frontend only needs to send the `session_id` received in the previous response

### 3. Context-Aware Answers

Related questions receive enhanced answers that:

- Reference previous conversation context
- Provide comprehensive responses that connect related topics
- Maintain conversation coherence

## API Usage

### Basic Request (First Question - No Session ID)

**Request:**

```json
POST /ask
{
  "question": "What is Nithub?"
}
```

**Response:**

```json
{
  "answer": "Nithub is an innovation hub dedicated to building Africa's future by supporting startups, creating digital products, and upskilling talent.",
  "follow_up_question": "Where is Nithub located?",
  "conversation_id": 1,
  "session_id": "aB3xY9z2"
}
```

**Note:** The `session_id` is automatically generated. Frontend should save this for subsequent requests.

### Follow-Up Request (With Session ID)

**Request:**

```json
POST /ask
{
  "question": "Where is Nithub located?",
  "session_id": "aB3xY9z2"
}
```

**Response:**

```json
{
  "answer": "We are located at 6 Commercial Road, University of Lagos, Lagos, Nigeria.",
  "follow_up_question": "How can I contact Nithub?",
  "conversation_id": 2,
  "session_id": "aB3xY9z2"
}
```

**How it works:**

- Backend automatically retrieves previous question/answer from session storage
- Checks if current question is related to previous
- If related, uses both contexts for comprehensive answer
- Updates session with new conversation data
- Session timeout resets to 15 minutes

### Related Question Detection

When `session_id` is provided, the backend automatically:

1. **Related Question Example:**

   - Session has previous: "What is Nithub?" → "Nithub is an innovation hub..."
   - Current question: "Where is it located?" (uses "it" referring to Nithub)
   - **Backend action:**
     - Retrieves previous Q&A from session
     - Checks if related (YES ✅)
     - Uses both previous context and current question for comprehensive answer
   - **Frontend action:** Only needs to send `session_id` - context handled automatically

2. **Unrelated Question Example:**

   - Session has previous: "What is Nithub?"
   - Current question: "What are your opening hours?" (completely different topic)
   - **Backend action:**
     - Checks relation (NO ❌)
     - Treats as new question, uses only current context
   - Session is still updated with new conversation data

## Conversation Flow Example

```
Request 1:
POST /ask
{
  "question": "What is Nithub?"
  // No session_id - creates new session
}

Response 1:
{
  "answer": "Nithub is an innovation hub...",
  "follow_up_question": "Where is Nithub located?",
  "conversation_id": 1,
  "session_id": "aB3xY9z2"  // ← Frontend saves this
}

Request 2:
POST /ask
{
  "question": "Where is Nithub located?",
  "session_id": "aB3xY9z2"  // ← Frontend sends saved session_id
}

Backend automatically:
- Retrieves previous Q&A from session "aB3xY9z2"
- Detects relation ✅
- Uses previous context + current question

Response 2:
{
  "answer": "We are located at 6 Commercial Road...",
  "follow_up_question": "How can I contact Nithub?",
  "conversation_id": 2,
  "session_id": "aB3xY9z2"  // ← Same session, updated
}

Request 3:
POST /ask
{
  "question": "How can I contact Nithub?",
  "session_id": "aB3xY9z2"
}

Backend automatically:
- Retrieves previous Q&A from session
- Detects relation ✅
- Uses context

Response 3:
{
  "answer": "You can contact us through our website...",
  "follow_up_question": "What are your opening hours?",
  "conversation_id": 3,
  "session_id": "aB3xY9z2"
}

After 15 minutes of inactivity:
- Session "aB3xY9z2" expires and is deleted
- Next request with that session_id will create a new session
```

## Request Model

### AskRequest

```typescript
{
  question: string           // Required: The question to ask
  session_id?: string        // Optional: Session ID from previous response
}
```

### Fields

- **question** (required): The user's question
- **session_id** (optional): The `session_id` from a previous response. If provided:
  - Backend automatically retrieves previous conversation from session storage
  - Checks if current question is related to previous
  - Uses previous context if related
  - Updates session with new conversation data
  - Resets 15-minute timeout timer

## Response Model

### AskResponse

```typescript
{
  answer: string              // The generated answer
  follow_up_question?: string  // Suggested next question (generated automatically)
  conversation_id: number     // Database ID for this conversation
  session_id: string          // Session ID (save this for next request)
}
```

### Fields

- **answer**: The AI-generated answer based on knowledge base
- **follow_up_question**: A relevant question automatically generated based on the answer. Display to user as a suggested next question
- **conversation_id**: Unique identifier stored in database (for reference/analytics)
- **session_id**: Session identifier (8 characters). **Frontend should save this and include it in subsequent requests** to maintain conversation context

## Database Schema

### Conversations Table

| Column                     | Type     | Description                                    |
| -------------------------- | -------- | ---------------------------------------------- |
| `id`                       | Integer  | Primary key                                    |
| `question`                 | Text     | User's question                                |
| `answer`                   | Text     | Generated answer                               |
| `follow_up_question`       | Text     | Generated follow-up question (nullable)        |
| `previous_conversation_id` | Integer  | ID of previous related conversation (nullable) |
| `created_at`               | DateTime | Timestamp                                      |

### Conversation Chains

Conversations can form chains:

- Conversation 1: First question (no `previous_conversation_id`)
- Conversation 2: Follow-up question (`previous_conversation_id = 1`)
- Conversation 3: Follow-up to Conversation 2 (`previous_conversation_id = 2`)

## Implementation Details

### Related Question Detection

The system uses Google Gemini to determine if questions are related:

1. **Input**: Previous question, previous answer, current question
2. **Processing**: LLM analyzes semantic similarity and conversational flow
3. **Output**: "YES" if related, "NO" if not
4. **Action**: Uses previous context only if "YES"

### Follow-Up Question Generation

The system generates follow-up questions by:

1. Analyzing the answer provided
2. Reviewing the knowledge base context used
3. Identifying natural next questions users might ask
4. Ensuring the question can be answered from the knowledge base

### Context Combination

When questions are related:

1. Retrieves relevant entries for current question
2. Includes previous question and answer in the prompt
3. Instructs LLM to use both contexts for comprehensive answer
4. Maintains conversation coherence

## Usage Patterns

### Pattern 1: Sequential Follow-Ups (Recommended)

Frontend displays `follow_up_question` as a button/suggestion. When user clicks it:

```javascript
let sessionId = null; // Store in component state

// Step 1 - First question
const response1 = await fetch("/ask", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ question: "What is Nithub?" }),
});
const data1 = await response1.json();
sessionId = data1.session_id; // Save session ID

// Display answer and follow_up_question to user

// Step 2 - User clicks follow-up question button
const response2 = await fetch("/ask", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    question: data1.follow_up_question, // Use generated follow-up
    session_id: sessionId, // Include session ID
  }),
});
const data2 = await response2.json();
sessionId = data2.session_id; // Update (usually same, but always save)

// Backend automatically handles context if related
```

### Pattern 2: User-Driven Follow-Ups

User asks their own question with session ID - backend checks relation automatically:

```javascript
let sessionId = null;

// Step 1
const response1 = await fetch("/ask", {
  method: "POST",
  body: JSON.stringify({ question: "What is Nithub?" }),
});
const data1 = await response1.json();
sessionId = data1.session_id;

// Step 2 - User types their own question
const userQuestion = "What programs do you offer?"; // User's own question
const response2 = await fetch("/ask", {
  method: "POST",
  body: JSON.stringify({
    question: userQuestion,
    session_id: sessionId, // Include session ID
  }),
});

// Backend automatically:
// - Retrieves previous Q&A from session
// - Checks if userQuestion is related to previous
// - Uses context if related, otherwise treats as new
```

### Pattern 3: New Conversation (No Session)

Start a new conversation by omitting `session_id`:

```javascript
const response = await fetch("/ask", {
  method: "POST",
  body: JSON.stringify({ question: "What are your opening hours?" }),
  // No session_id - creates new session
});
// No context from previous conversations in this session
```

## Session Management

### Session Lifecycle

1. **Creation**: First request without `session_id` creates a new 8-character session ID
2. **Usage**: Include `session_id` in subsequent requests to maintain context
3. **Activity Tracking**: Each request with a valid `session_id` resets the 15-minute timer
4. **Expiration**: Sessions expire after 15 minutes of inactivity
5. **Cleanup**: Expired sessions are automatically deleted (runs every minute)

### Session Storage

Sessions are stored **in-memory on the backend** and contain:

- `last_activity`: Timestamp of last request
- `previous_question`: Last question asked
- `previous_answer`: Last answer provided
- `previous_conv_id`: Database conversation ID
- `follow_up_question`: Generated follow-up from last response

**Important**: Sessions are stored in memory and will be lost on server restart. The conversation history in PostgreSQL persists independently.

### Session Info Endpoint

Check session status:

```bash
GET /session/{session_id}
```

**Response:**

```json
{
  "session_id": "aB3xY9z2",
  "last_activity": "2025-10-31T11:30:00Z",
  "time_remaining_seconds": 750,
  "has_previous_conversation": true,
  "follow_up_question": "Where is Nithub located?"
}
```

## Best Practices

1. **Always save `session_id`**: Store it in frontend state/localStorage to maintain conversation
2. **Include `session_id` in requests**: Backend handles context automatically
3. **Display `follow_up_question`**: Show it as a suggested next question
4. **Handle expired sessions**: If session expires (404 on session endpoint), start new conversation
5. **No frontend storage needed**: Don't store previous questions/answers - backend handles it
6. **Handle null follow-ups**: May occasionally be null if generation fails

## Error Handling

### Follow-Up Generation Fails

If follow-up question generation fails:

- `follow_up_question` will be `null`
- Answer is still provided normally
- Error is logged but doesn't block response

### Session Expired or Not Found

If `session_id` doesn't exist or expired:

- New session is automatically created
- Previous question/answer are not available
- Current question treated as standalone
- No error thrown - seamless experience

### Relation Check Fails

If relation checking fails:

- System defaults to not using previous context
- Current question processed normally
- Error logged but doesn't block response

## Examples

### Example 1: Location Follow-Up

```bash
# Request 1 - No session_id (creates new session)
curl -X POST "http://localhost:8080/ask" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is Nithub?"}'

# Response 1
{
  "answer": "Nithub is an innovation hub...",
  "follow_up_question": "Where is Nithub located?",
  "conversation_id": 1,
  "session_id": "aB3xY9z2"  // Save this!
}

# Request 2 - Include session_id from previous response
curl -X POST "http://localhost:8080/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Where is Nithub located?",
    "session_id": "aB3xY9z2"
  }'

# Response 2 - Backend automatically uses context from session
{
  "answer": "We are located at 6 Commercial Road, University of Lagos...",
  "follow_up_question": "How can I contact Nithub?",
  "conversation_id": 2,
  "session_id": "aB3xY9z2"  // Same session, keep using it
}
```

### Example 2: Program Details Follow-Up

```bash
# Request 1
curl -X POST "http://localhost:8080/ask" \
  -H "Content-Type: application/json" \
  -d '{"question": "What training programs do you offer?"}'

# Response 1
{
  "answer": "We offer NITDEV, NITDATA, HATCHDEV...",
  "follow_up_question": "Are your training programmes beginner-friendly?",
  "conversation_id": 5,
  "session_id": "xY8mN2pQ"
}

# Request 2 - Related question (uses "they" referring to programs)
curl -X POST "http://localhost:8080/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Are they suitable for beginners?",
    "session_id": "xY8mN2pQ"
  }'

# Backend automatically:
# - Retrieves previous Q&A from session
# - Detects "they" refers to programs (related ✅)
# - Uses context

# Response 2
{
  "answer": "Yes! We have entry-level programmes for absolute beginners...",
  "follow_up_question": "How long do your training programmes last?",
  "conversation_id": 6,
  "session_id": "xY8mN2pQ"
}
```

## Session vs Database Storage

### Session Storage (In-Memory)

- **Purpose**: Quick access to recent conversation context
- **Location**: Backend server memory
- **Lifetime**: 15 minutes of inactivity
- **Data**: Previous question, answer, follow-up question, conversation ID
- **Loss**: Data lost on server restart (but conversations still in PostgreSQL)

### Database Storage (PostgreSQL)

- **Purpose**: Permanent conversation history
- **Location**: PostgreSQL database
- **Lifetime**: Permanent (until manually deleted)
- **Data**: All questions, answers, follow-up questions, relationships
- **Persistent**: Survives server restarts

## Database Migration

If you have an existing database, you'll need to add the new columns:

```sql
-- Connect to your PostgreSQL database
ALTER TABLE conversations
ADD COLUMN IF NOT EXISTS follow_up_question TEXT,
ADD COLUMN IF NOT EXISTS previous_conversation_id INTEGER;

-- Add index for faster lookups
CREATE INDEX IF NOT EXISTS idx_conversations_previous_id
ON conversations(previous_conversation_id);
```

Or drop and recreate (loses data):

```sql
DROP TABLE conversations;
-- Restart the app - it will recreate with new schema
```

## Troubleshooting

### Follow-up questions are always null

- Check Gemini API quota/errors in logs
- Verify API key is valid
- Check if answer generation is working (if answers fail, follow-ups will too)

### Questions always treated as unrelated

- Check relation detection logic in logs
- Verify `session_id` is being sent correctly
- Ensure questions are semantically related (the system is strict)
- Check if session expired (use `/session/{session_id}` endpoint)

### Context not being used

- Verify `session_id` is being sent in request
- Check logs for "Questions are related. Using previous context from session." message
- Verify session hasn't expired (check `/session/{session_id}`)
- Ensure session has previous conversation data (check session info endpoint)

## Future Enhancements

Potential improvements:

- Multi-turn conversation context (chain of multiple previous questions)
- Session-based conversation grouping
- Custom follow-up question templates
- User preference-based follow-up suggestions
