"""Service for answering questions using LLM and vector search."""

from typing import Optional, Tuple
from vector import retriever
from ..utils.config import get_gemini_model
from ..utils.prompts import get_answer_prompt


def _get_gemini_model():
    """Lazy initialization of Gemini model."""
    return get_gemini_model()


class QAService:
    """Service for generating answers to questions."""
    
    @staticmethod
    def retrieve_context(question_text: str, previous_question: Optional[str] = None) -> str:
        """
        Retrieve relevant context from the knowledge base.
        
        Args:
            question_text: The question to search for
            previous_question: Optional previous question to enhance search
            
        Returns:
            Context block string
        """
        # Enhance search query with previous context if available
        search_query = question_text
        if previous_question:
            search_query = f"{question_text} {previous_question}"
        
        reviews = retriever.invoke(search_query)
        print(f"Retrieved reviews for query: {search_query}")
        
        # Convert retrieved Documents to a compact text context
        if isinstance(reviews, list):
            context_parts = []
            for doc in reviews:
                try:
                    context_parts.append(str(getattr(doc, "page_content", doc)))
                except Exception:
                    context_parts.append(str(doc))
            context_block = "\n\n".join(context_parts)
        else:
            context_block = str(reviews)
        
        return context_block
    
    @staticmethod
    def generate_answer(question_text: str, context_block: str, 
                       previous_context: str = "", is_related: bool = False) -> str:
        """
        Generate an answer using the LLM.
        
        Args:
            question_text: The user's question
            context_block: Retrieved knowledge base context
            previous_context: Previous conversation context
            is_related: Whether this is a follow-up question
            
        Returns:
            Generated answer string
            
        Raises:
            RuntimeError: If LLM generation fails
        """
        prompt_text = get_answer_prompt(context_block, question_text, previous_context, is_related)
        
        try:
            gemini_model = _get_gemini_model()
            gemini_response = gemini_model.generate_content(prompt_text)
        except Exception as e:
            model_name = "gemini-2.5-flash"  # Default
            raise RuntimeError(f"Gemini API error using model '{model_name}': {e}")
        
        result_text = getattr(gemini_response, "text", "") or str(gemini_response)
        
        # Normalize whitespace to avoid \n in responses
        cleaned_answer = " ".join(result_text.split())
        
        # Enforce 300 word maximum limit
        words = cleaned_answer.split()
        if len(words) > 300:
            cleaned_answer = " ".join(words[:300])
            # Ensure sentence ends properly (remove incomplete last sentence if needed)
            if cleaned_answer and not cleaned_answer[-1] in ".!?":
                last_period = cleaned_answer.rfind(".")
                if last_period > len(cleaned_answer) * 0.8:  # Only truncate if period is in last 20%
                    cleaned_answer = cleaned_answer[:last_period + 1]
        
        return cleaned_answer

