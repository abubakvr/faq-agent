# Nithub QA API Documentation

Complete API reference for the Nithub Question & Answer service.

## Base URL

```
http://localhost:8080
```

## Standard Response Format

All API endpoints return responses in the following standardized format:

### Success Response

```json
{
  "status": true,
  "code": "00",
  "message": "Response retrieved successfully",
  "data": {
    // Endpoint-specific data
  }
}
```

### Error Response

```json
{
  "status": false,
  "code": "01",
  "message": "Error message describing what went wrong",
  "data": {}
}
```

### Response Fields

| Field     | Type    | Description                                                       |
| --------- | ------- | ----------------------------------------------------------------- |
| `status`  | boolean | `true` for success, `false` for failure                           |
| `code`    | string  | `"00"` for success, `"01"` for failure                            |
| `message` | string  | Human-readable message describing the result                      |
| `data`    | object  | Response data (endpoint-specific) or empty object `{}` for errors |

---

## Endpoints

### 1. Health Check

**GET** `/`

Check if the API is running.

#### Response

**Success (200 OK)**

```json
{
  "status": true,
  "code": "00",
  "message": "Nithub QA API is running!",
  "data": {
    "message": "Nithub QA API is running!"
  }
}
```

---

### 2. Ask a Question

**POST** `/ask`

Ask a question and receive an AI-generated answer with a follow-up question suggestion.

#### Request Body

```json
{
  "question": "What is Nithub?",
  "session_id": "optional_session_id" // Optional: for conversation continuity
}
```

#### Request Parameters

| Parameter    | Type   | Required | Description                                     |
| ------------ | ------ | -------- | ----------------------------------------------- |
| `question`   | string | Yes      | The question to ask                             |
| `session_id` | string | No       | Session ID for maintaining conversation context |

#### Response

**Success (200 OK)**

```json
{
  "status": true,
  "code": "00",
  "message": "Response retrieved successfully",
  "data": {
    "answer": "Nithub is an innovation hub dedicated to building Africa's future by supporting startups, creating digital products, and upskilling talent.",
    "follow_up_question": "Would you like to know more about how you can visit us in person?",
    "conversation_id": 73,
    "session_id": "HZ7PlNgb"
  }
}
```

**Error (200 OK)** - Invalid input

```json
{
  "status": false,
  "code": "01",
  "message": "Question cannot be empty",
  "data": {}
}
```

**Error (200 OK)** - LLM API error

```json
{
  "status": false,
  "code": "01",
  "message": "Gemini API error using model 'gemini-2.5-flash': ...",
  "data": {}
}
```

#### Response Data Fields

| Field                | Type           | Description                                                    |
| -------------------- | -------------- | -------------------------------------------------------------- |
| `answer`             | string         | AI-generated answer (max 300 words)                            |
| `follow_up_question` | string \| null | Suggested follow-up question in invitation format              |
| `conversation_id`    | integer        | Database ID of the saved conversation                          |
| `session_id`         | string         | Session ID for maintaining conversation context (8 characters) |

#### Usage Examples

**First Question (No Session)**

```bash
POST /ask
Content-Type: application/json

{
  "question": "What is Nithub?"
}
```

**Follow-up Question (With Session)**

```bash
POST /ask
Content-Type: application/json

{
  "question": "Where is Nithub located?",
  "session_id": "HZ7PlNgb"
}
```

**Answering Follow-up (Yes)**

```bash
POST /ask
Content-Type: application/json

{
  "question": "Yes",
  "session_id": "HZ7PlNgb"
}
```

_Note: When answering "Yes" to a follow-up question, the system automatically extracts the actual question from the follow-up._

---

### 3. Get All Conversations

**GET** `/conversations`

Retrieve a paginated list of all conversations stored in the database.

#### Query Parameters

| Parameter | Type    | Required | Default | Description                                       |
| --------- | ------- | -------- | ------- | ------------------------------------------------- |
| `limit`   | integer | No       | 50      | Maximum number of conversations to return (1-100) |
| `offset`  | integer | No       | 0       | Number of conversations to skip for pagination    |

#### Response

**Success (200 OK)**

```json
{
  "status": true,
  "code": "00",
  "message": "Response retrieved successfully",
  "data": {
    "total": 150,
    "conversations": [
      {
        "id": 73,
        "question": "What is Nithub?",
        "answer": "Nithub is an innovation hub...",
        "follow_up_question": "Would you like to know more about how you can visit us in person?",
        "previous_conversation_id": null,
        "created_at": "2025-10-31T15:12:02.889Z"
      },
      {
        "id": 72,
        "question": "Where is Nithub located?",
        "answer": "We are located at 6 Commercial Road...",
        "follow_up_question": "Would you like to know more about our programs?",
        "previous_conversation_id": 71,
        "created_at": "2025-10-31T15:11:45.234Z"
      }
    ]
  }
}
```

**Error (200 OK)**

```json
{
  "status": false,
  "code": "01",
  "message": "Error retrieving conversations: ...",
  "data": {}
}
```

#### Usage Examples

**Get First 50 Conversations**

```bash
GET /conversations
```

**Get Next 20 Conversations (Pagination)**

```bash
GET /conversations?limit=20&offset=50
```

---

### 4. Get Single Conversation

**GET** `/conversations/{conversation_id}`

Retrieve a specific conversation by its ID.

#### Path Parameters

| Parameter         | Type    | Required | Description                            |
| ----------------- | ------- | -------- | -------------------------------------- |
| `conversation_id` | integer | Yes      | The ID of the conversation to retrieve |

#### Response

**Success (200 OK)**

```json
{
  "status": true,
  "code": "00",
  "message": "Response retrieved successfully",
  "data": {
    "id": 73,
    "question": "What is Nithub?",
    "answer": "Nithub is an innovation hub dedicated to building Africa's future by supporting startups, creating digital products, and upskilling talent.",
    "follow_up_question": "Would you like to know more about how you can visit us in person?",
    "previous_conversation_id": null,
    "created_at": "2025-10-31T15:12:02.889Z"
  }
}
```

**Error (200 OK)** - Conversation not found

```json
{
  "status": false,
  "code": "01",
  "message": "Conversation not found",
  "data": {}
}
```

#### Usage Example

```bash
GET /conversations/73
```

---

### 5. Get Session Information

**GET** `/session/{session_id}`

Get information about a conversation session, including time remaining and follow-up question.

#### Path Parameters

| Parameter    | Type   | Required | Description                |
| ------------ | ------ | -------- | -------------------------- |
| `session_id` | string | Yes      | The 8-character session ID |

#### Response

**Success (200 OK)**

```json
{
  "status": true,
  "code": "00",
  "message": "Response retrieved successfully",
  "data": {
    "session_id": "HZ7PlNgb",
    "last_activity": "2025-10-31T15:12:02.889Z",
    "time_remaining_seconds": 720,
    "has_previous_conversation": true,
    "follow_up_question": "Would you like to know more about how you can visit us in person?"
  }
}
```

**Error (200 OK)** - Session not found or expired

```json
{
  "status": false,
  "code": "01",
  "message": "Session not found or expired",
  "data": {}
}
```

#### Response Data Fields

| Field                       | Type           | Description                                             |
| --------------------------- | -------------- | ------------------------------------------------------- |
| `session_id`                | string         | The session ID                                          |
| `last_activity`             | datetime       | Timestamp of last activity in the session               |
| `time_remaining_seconds`    | integer        | Seconds until session expires (0 if expired)            |
| `has_previous_conversation` | boolean        | Whether there's a previous conversation in this session |
| `follow_up_question`        | string \| null | The current follow-up question suggestion               |

#### Usage Example

```bash
GET /session/HZ7PlNgb
```

#### Session Expiration

- Sessions expire after **15 minutes** of inactivity
- Expired sessions are automatically cleaned up
- Using an expired `session_id` creates a new session

---

## Error Handling

All endpoints return errors in the standardized format:

```json
{
  "status": false,
  "code": "01",
  "message": "Error description",
  "data": {}
}
```

### Common Error Messages

- **Invalid input**: "Question cannot be empty"
- **Database error**: "Error retrieving conversations: ..."
- **LLM API error**: "Gemini API error using model 'gemini-2.5-flash': ..."
- **Session expired**: "Session not found or expired"
- **Not found**: "Conversation not found"
- **Internal server error**: "Internal server error: ..."

---

## Response Times

| Endpoint                  | Typical Response Time    |
| ------------------------- | ------------------------ |
| `GET /`                   | < 1ms                    |
| `POST /ask`               | 10-20 seconds (LLM call) |
| `GET /conversations`      | < 100ms                  |
| `GET /conversations/{id}` | < 50ms                   |
| `GET /session/{id}`       | < 10ms                   |

---

## Authentication

Currently, no authentication is required. All endpoints are publicly accessible.

---

## Rate Limiting

No rate limiting is currently implemented. Please use the API responsibly.

---

## Examples

### Complete Conversation Flow

**Step 1: Ask First Question**

```bash
POST /ask
{
  "question": "What is Nithub?"
}
```

**Response:**

```json
{
  "status": true,
  "code": "00",
  "message": "Response retrieved successfully",
  "data": {
    "answer": "Nithub is an innovation hub...",
    "follow_up_question": "Would you like to know more about how you can visit us in person?",
    "conversation_id": 1,
    "session_id": "abc12345"
  }
}
```

**Step 2: Answer Follow-up (Yes)**

```bash
POST /ask
{
  "question": "Yes",
  "session_id": "abc12345"
}
```

**Response:**

```json
{
  "status": true,
  "code": "00",
  "message": "Response retrieved successfully",
  "data": {
    "answer": "We are located at 6 Commercial Road...",
    "follow_up_question": "Would you like to know more about our programs?",
    "conversation_id": 2,
    "session_id": "abc12345"
  }
}
```

**Step 3: Ask Different Question (Same Session)**

```bash
POST /ask
{
  "question": "What training programs do you offer?",
  "session_id": "abc12345"
}
```

**Response:**

```json
{
  "status": true,
  "code": "00",
  "message": "Response retrieved successfully",
  "data": {
    "answer": "We offer various training programs including...",
    "follow_up_question": "Would you like to know more about how to apply?",
    "conversation_id": 3,
    "session_id": "abc12345"
  }
}
```

---

## Notes

1. **Session Management**: The `session_id` is automatically generated on the first request. Save it and include it in subsequent requests to maintain conversation context.

2. **Follow-up Questions**: The system automatically generates follow-up questions. Users can respond with "Yes" to accept the follow-up, or ask their own question.

3. **Conversation Chaining**: Related questions within a session are automatically detected and answered with context from previous conversations.

4. **Answer Length**: All answers are limited to a maximum of 300 words.

5. **Question Extraction**: When users respond "Yes" to a follow-up question, the system automatically extracts the actual question from the follow-up format.

---

## Support

For issues or questions, please contact the development team.
