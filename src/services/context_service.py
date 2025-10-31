"""Service for managing conversation context and relation checking."""

from typing import Optional, Tuple
from ..utils.config import get_gemini_model
from ..utils.prompts import get_relation_check_prompt
from ..helpers.session_manager import get_session_storage


def _get_gemini_model():
    """Lazy initialization of Gemini model."""
    return get_gemini_model()


class ContextService:
    """Service for managing conversation context."""
    
    @staticmethod
    def check_question_relation(previous_question: str, previous_answer: str,
                                current_question: str, previous_followup: Optional[str] = None) -> bool:
        """
        Check if the current question is related to the previous conversation.
        
        Args:
            previous_question: The previous question
            previous_answer: The previous answer
            current_question: The current question
            previous_followup: Optional previous follow-up question
            
        Returns:
            True if questions are related, False otherwise
        """
        try:
            prompt = get_relation_check_prompt(
                previous_question, previous_answer, current_question, previous_followup
            )
            gemini_model = _get_gemini_model()
            relation_response = gemini_model.generate_content(prompt)
            relation_text = getattr(relation_response, "text", "").strip().upper()
            return "YES" in relation_text
        except Exception as e:
            print(f"Error checking question relation: {e}")
            # On error, assume related to be safe
            return True
    
    @staticmethod
    def build_context(previous_question: str, previous_answer: str, 
                     previous_followup: Optional[str] = None) -> str:
        """
        Build context string from previous conversation.
        
        Args:
            previous_question: The previous question
            previous_answer: The previous answer
            previous_followup: Optional previous follow-up question
            
        Returns:
            Formatted context string
        """
        context = f"Previous question: {previous_question}\nPrevious answer: {previous_answer}\n"
        if previous_followup:
            context += f"Previous follow-up suggestion: {previous_followup}\n"
        context += "\n"
        return context
    
    @staticmethod
    def get_session_data(session_id: str) -> Optional[dict]:
        """
        Get session data.
        
        Args:
            session_id: The session ID
            
        Returns:
            Session data dictionary or None if not found
        """
        session_storage = get_session_storage()
        return session_storage.get(session_id)

