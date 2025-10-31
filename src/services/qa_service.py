"""Service for answering questions using LLM and vector search."""

import json
import re
from typing import Optional, Tuple, Dict
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
    def generate_answer_with_followup(question_text: str, context_block: str, 
                                      previous_context: str = "", is_related: bool = False,
                                      recent_follow_ups: list = None) -> Dict[str, str]:
        """
        Generate both answer and follow-up question using a single LLM call.
        Returns JSON with both answer and follow_up_question.
        
        Args:
            question_text: The user's question
            context_block: Retrieved knowledge base context
            previous_context: Previous conversation context
            is_related: Whether this is a follow-up question
            recent_follow_ups: List of recently suggested follow-ups to avoid repetition
            
        Returns:
            Dictionary with 'answer' and 'follow_up_question' keys
            
        Raises:
            RuntimeError: If LLM generation fails
        """
        recent_follow_ups = recent_follow_ups or []
        prompt_text = get_answer_prompt(context_block, question_text, previous_context, 
                                       is_related, recent_follow_ups)
        
        try:
            gemini_model = _get_gemini_model()
            gemini_response = gemini_model.generate_content(prompt_text)
        except Exception as e:
            model_name = "gemini-2.5-flash"  # Default
            raise RuntimeError(f"Gemini API error using model '{model_name}': {e}")
        
        result_text = getattr(gemini_response, "text", "") or str(gemini_response)
        
        # Try to parse JSON from response
        json_data = None
        
        # Extract JSON from markdown code blocks if present
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', result_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find JSON object directly
            json_match = re.search(r'\{.*"answer".*"follow_up_question".*\}', result_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = result_text.strip()
        
        try:
            json_data = json.loads(json_str)
        except json.JSONDecodeError:
            # Fallback: try to extract fields manually
            answer_match = re.search(r'"answer"\s*:\s*"([^"]+)"', json_str, re.DOTALL)
            followup_match = re.search(r'"follow_up_question"\s*:\s*"([^"]+)"', json_str, re.DOTALL)
            
            if answer_match and followup_match:
                json_data = {
                    "answer": answer_match.group(1),
                    "follow_up_question": followup_match.group(1)
                }
            else:
                # Last resort: use entire response as answer, no follow-up
                print(f"Warning: Could not parse JSON from LLM response. Using fallback.")
                cleaned_answer = " ".join(result_text.split())
                # Enforce 300 word limit
                words = cleaned_answer.split()
                if len(words) > 300:
                    cleaned_answer = " ".join(words[:300])
                json_data = {
                    "answer": cleaned_answer,
                    "follow_up_question": None
                }
        
        # Clean and validate answer
        answer = json_data.get("answer", "").strip()
        if not answer:
            answer = "I don't have that information in my knowledge base. Please contact Nithub directly for this information."
        
        # Normalize whitespace
        answer = " ".join(answer.split())
        
        # Enforce 300 word maximum limit
        words = answer.split()
        if len(words) > 300:
            answer = " ".join(words[:300])
            # Ensure sentence ends properly
            if answer and not answer[-1] in ".!?":
                last_period = answer.rfind(".")
                if last_period > len(answer) * 0.8:
                    answer = answer[:last_period + 1]
        
        # Clean and validate follow-up question
        follow_up_question = json_data.get("follow_up_question", "").strip()
        if follow_up_question:
            # Normalize whitespace
            follow_up_question = " ".join(follow_up_question.split())
            
            # Remove double question marks
            follow_up_question = follow_up_question.replace("??", "?")
            
            # Fix common issues
            # Replace lowercase 'nithub' with 'Nithub'
            follow_up_question = re.sub(r'\bnithub\b', 'Nithub', follow_up_question, flags=re.IGNORECASE)
            
            # If it doesn't start with the proper format, try to fix it
            if not follow_up_question.lower().startswith("would you like to know"):
                # If it's just the topic, wrap it properly
                if not "would you like" in follow_up_question.lower():
                    follow_up_question = f"Would you like to know more about {follow_up_question}?"
            
            # Ensure it ends with a single question mark
            follow_up_question = follow_up_question.rstrip("?").rstrip() + "?"
            
            # Ensure proper capitalization of first letter
            if follow_up_question and not follow_up_question[0].isupper():
                follow_up_question = follow_up_question[0].upper() + follow_up_question[1:]
        else:
            follow_up_question = None
        
        return {
            "answer": answer,
            "follow_up_question": follow_up_question
        }

