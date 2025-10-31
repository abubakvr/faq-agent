# Project Structure Documentation

This document describes the modular architecture of the Nithub QA API project.

## Directory Structure

```
ollama-agent/
├── src/
│   ├── types/              # Pydantic models and schemas
│   ├── helpers/            # Utility helper functions
│   ├── validation/         # Input validation functions
│   ├── repository/         # Data access layer (database operations)
│   ├── services/           # Business logic layer
│   ├── controllers/        # Request handling and orchestration
│   ├── routes/             # FastAPI route definitions
│   └── utils/              # Configuration and utilities
├── migrations/             # Database migration files
├── main.py                 # FastAPI application entry point
├── database.py             # Database connection and models
├── vector.py               # Vector store initialization
├── migrate.py              # Migration runner
└── requirements.txt        # Python dependencies
```

## Module Breakdown

### 1. Types (`src/types/`)

**Purpose**: Define data models and schemas for API requests/responses.

**Files**:

- `schemas.py`: Pydantic models
  - `AskRequest`: Request model for asking questions
  - `AskResponse`: Response model with answer and follow-up
  - `ConversationResponse`: Single conversation model
  - `ConversationsListResponse`: Paginated conversations model

### 2. Helpers (`src/helpers/`)

**Purpose**: Reusable helper functions for common operations.

**Files**:

- `session_manager.py`: Session management functions
  - `generate_session_id()`: Generate short session IDs
  - `get_or_create_session()`: Session creation/retrieval
  - `cleanup_expired_sessions()`: Remove expired sessions
  - `periodic_cleanup()`: Background cleanup task
- `question_extractor.py`: Question extraction utilities
  - `extract_question_from_followup()`: Convert follow-up questions to direct questions

### 3. Validation (`src/validation/`)

**Purpose**: Input validation and sanitization.

**Files**:

- `validators.py`: Validation functions
  - `validate_question()`: Validate question input
  - `validate_session_id()`: Validate session ID format
  - `validate_pagination_params()`: Validate pagination
  - `is_affirmative_response()`: Check if response is affirmative

### 4. Repository (`src/repository/`)

**Purpose**: Data access layer for database operations.

**Files**:

- `conversation_repository.py`: Conversation data access
  - `ConversationRepository`: Repository class
    - `create()`: Create new conversation
    - `get_by_id()`: Get conversation by ID
    - `get_all()`: Get paginated conversations

### 5. Services (`src/services/`)

**Purpose**: Business logic layer.

**Files**:

- `qa_service.py`: Question answering service

  - `QAService`: Service for generating answers
    - `retrieve_context()`: Get relevant context from vector store
    - `generate_answer()`: Generate answer using LLM

- `context_service.py`: Conversation context management

  - `ContextService`: Service for context handling
    - `check_question_relation()`: Check if questions are related
    - `build_context()`: Build context string
    - `get_session_data()`: Get session data

- `followup_service.py`: Follow-up question generation
  - `FollowupService`: Service for generating follow-ups
    - `extract_topics_from_followups()`: Extract topics from recent follow-ups
    - `select_question_from_csv()`: Select question from CSV (related or random)
    - `generate_followup()`: Convert question to follow-up format

### 6. Controllers (`src/controllers/`)

**Purpose**: Orchestrate services and handle requests.

**Files**:

- `qa_controller.py`: Q&A request handling

  - `QAController`: Controller for question answering
    - `ask_question()`: Main method to process questions

- `conversation_controller.py`: Conversation retrieval

  - `ConversationController`: Controller for conversations
    - `get_conversations()`: Get paginated conversations
    - `get_conversation()`: Get single conversation

- `session_controller.py`: Session management
  - `SessionController`: Controller for sessions
    - `get_session_info()`: Get session information

### 7. Routes (`src/routes/`)

**Purpose**: FastAPI route definitions.

**Files**:

- `qa_routes.py`: Q&A endpoints

  - `POST /ask`: Ask a question

- `conversation_routes.py`: Conversation endpoints

  - `GET /conversations`: List conversations
  - `GET /conversations/{id}`: Get single conversation

- `session_routes.py`: Session endpoints
  - `GET /session/{session_id}`: Get session info

### 8. Utils (`src/utils/`)

**Purpose**: Configuration and utility functions.

**Files**:

- `config.py`: Configuration management

  - `get_gemini_model()`: Initialize Gemini model
  - `get_csv_dataframe()`: Load CSV data

- `prompts.py`: LLM prompt templates
  - `get_answer_prompt()`: Build answer generation prompt
  - `get_followup_prompt()`: Build follow-up generation prompt
  - `get_relation_check_prompt()`: Build relation check prompt

## Data Flow

```
Request → Routes → Controllers → Services → Repository → Database
                                    ↓
                                 Helpers/Utils
```

1. **Routes** receive HTTP requests and validate basic structure
2. **Controllers** orchestrate the flow:
   - Validate input using validation layer
   - Call services for business logic
   - Handle errors and format responses
3. **Services** contain business logic:
   - QA Service: Answer generation
   - Context Service: Conversation context management
   - Follow-up Service: Follow-up question generation
4. **Repository** handles all database operations
5. **Helpers/Utils** provide reusable utilities

## Benefits of This Structure

1. **Separation of Concerns**: Each layer has a specific responsibility
2. **Testability**: Easy to mock dependencies for testing
3. **Maintainability**: Changes are localized to specific modules
4. **Scalability**: Easy to add new features without affecting existing code
5. **Reusability**: Services and helpers can be reused across controllers
6. **Readability**: Clear organization makes code easier to understand

## Import Patterns

- **Relative imports** (`..`) are used within `src/` package
- **Absolute imports** from root for external modules (e.g., `database`, `vector`)
- **Type imports** from `src.types` for schemas
- **Service imports** from `src.services` for business logic

## Adding New Features

1. **New endpoint**: Add route in `routes/`, controller in `controllers/`
2. **New service**: Create service class in `services/`
3. **New validation**: Add validator in `validation/`
4. **New type**: Add schema in `types/schemas.py`
5. **New database model**: Add to `database.py` and create repository method
