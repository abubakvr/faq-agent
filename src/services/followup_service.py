"""Service for generating follow-up questions."""

import random
from typing import Optional
import pandas as pd
from vector import retriever
from ..utils.config import get_gemini_model, get_csv_dataframe
from ..utils.prompts import get_followup_prompt


def _get_gemini_model():
    """Lazy initialization of Gemini model."""
    return get_gemini_model()


def _get_csv_dataframe():
    """Lazy initialization of CSV dataframe."""
    return get_csv_dataframe()


class FollowupService:
    """Service for generating follow-up questions."""
    
    @staticmethod
    def extract_topics_from_followups(recent_follow_ups: list) -> set:
        """
        Extract topics from recent follow-up questions to avoid repetition.
        
        Args:
            recent_follow_ups: List of recent follow-up questions
            
        Returns:
            Set of topic keywords
        """
        previous_topics = set()
        for fu in recent_follow_ups:
            fu_lower = fu.lower()
            if "program" in fu_lower:
                previous_topics.add("program")
            if "event" in fu_lower:
                previous_topics.add("event")
            if "incubation" in fu_lower or "startup" in fu_lower:
                previous_topics.add("startup")
            if "location" in fu_lower or "where" in fu_lower:
                previous_topics.add("location")
            if "training" in fu_lower or "course" in fu_lower:
                previous_topics.add("training")
        return previous_topics
    
    @staticmethod
    def select_question_from_csv(question_text: str, previous_topics: set, 
                                use_random: bool = False) -> Optional[str]:
        """
        Select a question from CSV for follow-up (either related or random).
        
        Args:
            question_text: The current question
            previous_topics: Set of topics from recent follow-ups
            use_random: Whether to select randomly instead of semantically
            
        Returns:
            Selected question string or None
        """
        question_lower = question_text.lower()
        selected_question = None
        
        csv_df = _get_csv_dataframe()
        
        if use_random:
            # Pick a random question from CSV
            print("Using random question selection for variety")
            if len(csv_df) > 0:
                available_questions = csv_df[
                    csv_df['Question'].str.lower() != question_lower
                ]['Question'].tolist()
                
                if available_questions:
                    filtered = [q for q in available_questions 
                               if q.lower() not in question_lower and question_lower not in q.lower()]
                    
                    # Try to avoid recent topics if possible
                    if previous_topics and filtered:
                        topic_diverse = [q for q in filtered 
                                        if not any(topic in q.lower() for topic in previous_topics)]
                        if topic_diverse:
                            selected_question = random.choice(topic_diverse)
                        else:
                            selected_question = random.choice(filtered)
                    elif filtered:
                        selected_question = random.choice(filtered)
                    else:
                        selected_question = random.choice(available_questions)
        else:
            # Try to find a related question
            print("Using related question selection")
            related_docs = retriever.invoke(question_text)
            
            # Extract questions from retrieved documents
            related_questions = []
            for doc in related_docs:
                if isinstance(doc, dict):
                    content = doc.get("page_content", "")
                else:
                    content = getattr(doc, "page_content", str(doc))
                
                if content.startswith("Q:"):
                    parts = content.split("\nA:")
                    if len(parts) > 0:
                        q = parts[0].replace("Q:", "").strip()
                        if q.startswith('"') and q.endswith('"'):
                            q = q[1:-1]
                        related_questions.append(q)
            
            # Find a different question from retrieved ones
            for q in related_questions:
                q_lower = q.lower()
                if q_lower != question_lower and q_lower not in question_lower and question_lower not in q_lower:
                    if previous_topics:
                        q_topics = [t for t in previous_topics if t in q_lower]
                        if not q_topics:
                            selected_question = q
                            break
                    if not selected_question:
                        selected_question = q
            
            # If no good related question, search CSV for keyword matches
            if not selected_question and len(csv_df) > 0:
                keywords = [w.lower() for w in question_lower.split() if len(w) > 3]
                best_score = 0
                best_question = None
                diverse_candidates = []
                
                for _, row in csv_df.iterrows():
                    csv_q = str(row['Question']).strip()
                    csv_q_lower = csv_q.lower()
                    
                    if csv_q_lower == question_lower:
                        continue
                    if csv_q_lower in question_lower or question_lower in csv_q_lower:
                        continue
                    
                    score = sum(1 for keyword in keywords if keyword in csv_q_lower)
                    q_topics = [t for t in previous_topics if t in csv_q_lower]
                    is_diverse = not q_topics if previous_topics else True
                    
                    if score > 0:
                        if is_diverse:
                            diverse_candidates.append((csv_q, score))
                        if score > best_score:
                            best_score = score
                            best_question = csv_q
                
                if diverse_candidates:
                    diverse_candidates.sort(key=lambda x: x[1], reverse=True)
                    selected_question = diverse_candidates[0][0]
                elif best_question:
                    selected_question = best_question
        
        # Fallback: random question
        if not selected_question and len(csv_df) > 0:
            print("Fallback: Using random question")
            available_questions = csv_df[
                csv_df['Question'].str.lower() != question_lower
            ]['Question'].tolist()
            
            if available_questions:
                filtered = [q for q in available_questions 
                           if q.lower() not in question_lower and question_lower not in q.lower()]
                if filtered:
                    selected_question = random.choice(filtered)
                else:
                    selected_question = random.choice(available_questions)
        
        return selected_question
    
    @staticmethod
    def generate_followup(selected_question: str) -> Optional[str]:
        """
        Generate a follow-up question in invitation format.
        
        Args:
            selected_question: The question to convert to follow-up format
            
        Returns:
            Follow-up question string or None if generation fails
        """
        try:
            follow_up_prompt = get_followup_prompt(selected_question)
            gemini_model = _get_gemini_model()
            follow_up_response = gemini_model.generate_content(follow_up_prompt)
            follow_up_text = getattr(follow_up_response, "text", "").strip()
            follow_up_question = " ".join(follow_up_text.split())
            
            # Remove quotes if present
            if follow_up_question.startswith('"') and follow_up_question.endswith('"'):
                follow_up_question = follow_up_question[1:-1]
            if follow_up_question.startswith("'") and follow_up_question.endswith("'"):
                follow_up_question = follow_up_question[1:-1]
            
            # Ensure it starts with "Would you like to know"
            if not follow_up_question.lower().startswith("would you like to know"):
                if "?" in follow_up_question:
                    parts = follow_up_question.split("?")
                    if parts:
                        potential = parts[0].strip()
                        if potential.lower().startswith("would you like"):
                            follow_up_question = potential + "?"
            
            # Ensure it ends with a question mark
            if not follow_up_question.endswith("?"):
                follow_up_question = follow_up_question.rstrip(".") + "?"
            
            print(f"Generated follow-up question from CSV: {follow_up_question} (based on: {selected_question})")
            return follow_up_question
        except Exception as e:
            print(f"Error generating follow-up question: {e}")
            import traceback
            traceback.print_exc()
            return None

