"""Controller for handling Q&A requests."""

import random
from sqlalchemy.orm import Session
from typing import Tuple
from datetime import datetime

from ..types.schemas import AskRequest, AskResponse
from ..validation.validators import validate_question, is_affirmative_response
from ..helpers.session_manager import get_or_create_session, get_session_storage
from ..helpers.question_extractor import extract_question_from_followup
from ..services.qa_service import QAService
from ..services.context_service import ContextService
from ..services.followup_service import FollowupService
from ..repository.conversation_repository import ConversationRepository


class QAController:
    """Controller for question answering."""
    
    def __init__(self, db: Session):
        self.db = db
        self.qa_service = QAService()
        self.context_service = ContextService()
        self.followup_service = FollowupService()
        self.repo = ConversationRepository(db)
    
    async def ask_question(self, request: AskRequest) -> AskResponse:
        """
        Process a question and return an answer with follow-up.
        
        Args:
            request: AskRequest containing question and optional session_id
            
        Returns:
            AskResponse with answer, follow-up question, conversation_id, and session_id
        """
        # Validate input
        original_question = validate_question(request.question)
        question_text = original_question
        
        # Get or create session
        session_storage = get_session_storage()
        session_id = get_or_create_session(request.session_id)
        session_data = session_storage[session_id]
        
        previous_context = ""
        is_related = False
        previous_conv_id = session_data.get("previous_conv_id")
        
        print(f"Received question: {original_question} (Session: {session_id})")
        
        # Handle affirmative responses
        if is_affirmative_response(question_text):
            if session_data.get("follow_up_question"):
                follow_up_q = session_data["follow_up_question"]
                print(f"User answered affirmatively ('{original_question}'). Extracting question from follow-up...")
                question_text = extract_question_from_followup(follow_up_q)
                is_related = True
            elif session_data.get("previous_question"):
                question_text = f"Tell me more about {session_data['previous_question']}"
                is_related = True
                print(f"User said '{original_question}' but no follow-up. Expanding previous question: {question_text}")
        
        # Check if question is related to previous conversation
        if session_data.get("previous_question") and session_data.get("previous_answer") and not is_related:
            is_related = self.context_service.check_question_relation(
                session_data['previous_question'],
                session_data['previous_answer'],
                question_text,
                session_data.get('follow_up_question')
            )
            
            if is_related:
                previous_context = self.context_service.build_context(
                    session_data['previous_question'],
                    session_data['previous_answer'],
                    session_data.get('follow_up_question')
                )
                print("Questions are related. Using previous context from session.")
        
        # Retrieve context and generate answer
        context_block = self.qa_service.retrieve_context(
            question_text, 
            session_data.get("previous_question") if is_related else None
        )
        
        # Build previous context if available
        if session_data.get("previous_question") and session_data.get("previous_answer"):
            if not previous_context:
                previous_context = self.context_service.build_context(
                    session_data['previous_question'],
                    session_data['previous_answer'],
                    session_data.get('follow_up_question')
                )
        
        # Generate answer (main task - LLM call)
        answer = self.qa_service.generate_answer(
            question_text, context_block, previous_context, is_related
        )
        
        # Generate follow-up question (fast pattern-based, no LLM call)
        recent_follow_ups = session_data.get("recent_follow_ups", [])
        previous_topics = self.followup_service.extract_topics_from_followups(recent_follow_ups)
        use_random = random.random() < 0.4  # 40% random, 60% related
        
        selected_question = self.followup_service.select_question_from_csv(
            question_text, previous_topics, use_random
        )
        
        follow_up_question = None
        if selected_question:
            # Use fast pattern-based generation (no LLM call, instant)
            follow_up_question = self.followup_service.generate_followup(selected_question, use_fast=True)
        
        # Save to database
        conversation = self.repo.create(
            question=original_question,
            answer=answer,
            follow_up_question=follow_up_question,
            previous_conversation_id=previous_conv_id if is_related else None
        )
        
        # Update session (recent_follow_ups already defined above)
        if follow_up_question:
            recent_follow_ups.append(follow_up_question)
            if len(recent_follow_ups) > 5:
                recent_follow_ups = recent_follow_ups[-5:]
        
        session_storage[session_id].update({
            "last_activity": datetime.utcnow(),
            "previous_question": original_question,
            "previous_answer": answer,
            "previous_conv_id": conversation.id,
            "follow_up_question": follow_up_question,
            "recent_follow_ups": recent_follow_ups
        })
        
        return AskResponse(
            answer=answer,
            follow_up_question=follow_up_question,
            conversation_id=conversation.id,
            session_id=session_id
        )

