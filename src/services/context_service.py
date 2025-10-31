"""Service for managing conversation context and relation checking."""

from typing import Optional
from ..helpers.session_manager import get_session_storage


class ContextService:
    """Service for managing conversation context."""
    
    @staticmethod
    def check_question_relation(previous_question: str, previous_answer: str,
                                current_question: str, previous_followup: Optional[str] = None) -> bool:
        """
        Check if the current question is related to the previous conversation.
        Uses fast keyword-based matching instead of LLM to improve response time.
        
        Args:
            previous_question: The previous question
            previous_answer: The previous answer
            current_question: The current question
            previous_followup: Optional previous follow-up question
            
        Returns:
            True if questions are related, False otherwise
        """
        # Fast keyword-based relation check (no LLM call)
        prev_lower = previous_question.lower()
        curr_lower = current_question.lower()
        prev_answer_lower = previous_answer.lower()
        
        # Extract meaningful keywords (longer than 3 chars, not common words)
        stop_words = {"the", "what", "where", "when", "how", "why", "who", "is", "are", "do", "does", "can", "will", "would", "like", "to", "know", "about", "our", "you", "your", "we", "us"}
        
        def extract_keywords(text: str) -> set:
            words = text.lower().split()
            return {w for w in words if len(w) > 3 and w not in stop_words}
        
        prev_keywords = extract_keywords(prev_lower)
        curr_keywords = extract_keywords(curr_lower)
        answer_keywords = extract_keywords(prev_answer_lower)
        
        # Check for keyword overlap
        overlap_with_question = len(prev_keywords & curr_keywords)
        overlap_with_answer = len(answer_keywords & curr_keywords)
        
        # Check for pronouns/references that indicate relation
        reference_words = ["it", "they", "them", "this", "that", "these", "those", "here", "there"]
        has_reference = any(ref in curr_lower for ref in reference_words)
        
        # Check if current question contains words from previous
        shared_significant_words = prev_keywords & curr_keywords
        if len(shared_significant_words) >= 1:
            return True
        
        # Check if referencing previous topic
        if has_reference and len(curr_keywords) < 5:  # Short questions with references are likely related
            return True
        
        # Check if overlapping with answer keywords
        if overlap_with_answer >= 2:
            return True
        
        # Check for common question patterns that indicate follow-up
        follow_up_patterns = ["more", "also", "and", "another", "other", "else", "what about", "how about"]
        if any(pattern in curr_lower for pattern in follow_up_patterns):
            return True
        
        # Default: assume not related for speed (can be overridden if needed)
        return False
    
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

