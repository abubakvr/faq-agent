# Source Code Structure

This directory contains the modular source code for the Nithub QA API.

## Quick Reference

### Types (`types/`)

- **schemas.py**: All Pydantic models for requests and responses
  - `AskRequest`, `AskResponse`
  - `ConversationResponse`, `ConversationsListResponse`

### Helpers (`helpers/`)

- **session_manager.py**: Session management

  - `generate_session_id()`: Create new session IDs
  - `get_or_create_session()`: Get/create sessions
  - `cleanup_expired_sessions()`: Remove expired sessions
  - `periodic_cleanup()`: Background cleanup task

- **question_extractor.py**: Question processing
  - `extract_question_from_followup()`: Convert follow-up to direct question

### Validation (`validation/`)

- **validators.py**: Input validation
  - `validate_question()`: Validate question input
  - `validate_session_id()`: Validate session IDs
  - `validate_pagination_params()`: Validate pagination
  - `is_affirmative_response()`: Check for "Yes" responses

### Repository (`repository/`)

- **conversation_repository.py**: Database operations
  - `ConversationRepository.create()`: Save conversation
  - `ConversationRepository.get_by_id()`: Get single conversation
  - `ConversationRepository.get_all()`: Get paginated conversations

### Services (`services/`)

- **qa_service.py**: Answer generation

  - `QAService.retrieve_context()`: Get relevant context
  - `QAService.generate_answer()`: Generate answer using LLM

- **context_service.py**: Context management

  - `ContextService.check_question_relation()`: Check if questions related
  - `ContextService.build_context()`: Build context string

- **followup_service.py**: Follow-up generation
  - `FollowupService.extract_topics_from_followups()`: Get topics from follow-ups
  - `FollowupService.select_question_from_csv()`: Select question (random/related)
  - `FollowupService.generate_followup()`: Generate follow-up question

### Controllers (`controllers/`)

- **qa_controller.py**: Q&A orchestration

  - `QAController.ask_question()`: Main Q&A handler

- **conversation_controller.py**: Conversation retrieval

  - `ConversationController.get_conversations()`: Get paginated list
  - `ConversationController.get_conversation()`: Get single conversation

- **session_controller.py**: Session management
  - `SessionController.get_session_info()`: Get session information

### Routes (`routes/`)

- **qa_routes.py**: `POST /ask`
- **conversation_routes.py**: `GET /conversations`, `GET /conversations/{id}`
- **session_routes.py**: `GET /session/{session_id}`

### Utils (`utils/`)

- **config.py**: Configuration

  - `get_gemini_model()`: Get Gemini LLM model (singleton)
  - `get_csv_dataframe()`: Load CSV (singleton)

- **prompts.py**: Prompt templates
  - `get_answer_prompt()`: Build answer generation prompt
  - `get_followup_prompt()`: Build follow-up prompt
  - `get_relation_check_prompt()`: Build relation check prompt

## Import Guidelines

Within `src/` package, use relative imports:

```python
from ..types.schemas import AskRequest
from ..services.qa_service import QAService
```

From outside `src/`, use absolute imports:

```python
from src.routes import qa_router
from src.helpers.session_manager import periodic_cleanup
```

## Adding New Features

### New Endpoint

1. Add route in `routes/`
2. Add controller method in `controllers/`
3. Add any new services if needed

### New Service

1. Create service class in `services/`
2. Use services from other modules as needed
3. Keep business logic here, not in controllers

### New Validation

1. Add validator function in `validation/validators.py`
2. Use in controllers before processing requests

### New Type

1. Add Pydantic model in `types/schemas.py`
2. Export in `types/__init__.py`
