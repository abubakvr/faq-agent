"""Service for generating follow-up questions."""

import random
from typing import Optional
import pandas as pd
from ..vector import retriever
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
    def generate_followup_fast(selected_question: str) -> Optional[str]:
        """
        Generate a follow-up question using fast pattern matching (no LLM call).
        
        Args:
            selected_question: The question to convert to follow-up format
            
        Returns:
            Follow-up question string or None if generation fails
        """
        q_lower = selected_question.lower().strip("?.")
        
        # Pattern-based conversion (fast, no LLM)
        if "what is" in q_lower or "what are" in q_lower:
            # Extract topic after "what is/are"
            if "what is " in q_lower:
                topic = q_lower.split("what is ", 1)[1].strip()
            elif "what are " in q_lower:
                topic = q_lower.split("what are ", 1)[1].strip()
            else:
                topic = q_lower.replace("what is", "").replace("what are", "").strip()
            
            # Clean topic
            topic = topic.replace("nithub", "").replace("our", "").strip()
            
            if "program" in topic or "programs" in topic:
                return "Would you like to know about our programs?"
            elif "location" in topic or "where" in topic or "located" in topic:
                return "Would you like to know how to visit us?"
            elif "training" in topic or "course" in topic:
                return "Would you like to know about our training programs?"
            elif "incubation" in topic or "startup" in topic:
                return "Would you like to know the benefits of joining our incubation team?"
            elif "event" in topic or "events" in topic:
                return "Would you like to know about our events?"
            else:
                return f"Would you like to know more about {topic}?"
        
        elif "tell me about" in q_lower or "tell me" in q_lower:
            if "tell me about " in q_lower:
                topic = q_lower.split("tell me about ", 1)[1].strip()
            else:
                topic = q_lower.replace("tell me", "").strip()
            
            if "program" in topic:
                return "Would you like to know about our programs?"
            elif "incubation" in topic or "startup" in topic:
                return "Would you like to know the benefits of joining our incubation team?"
            else:
                return f"Would you like to know more about {topic}?"
        
        elif "how" in q_lower:
            if "how to" in q_lower:
                action = q_lower.split("how to", 1)[1].strip()
                if "sign up" in action or "register" in action or "join" in action:
                    return "Would you like to know how to sign up to our programs?"
                elif "contact" in action or "reach" in action:
                    return "Would you like to know how to contact us?"
                else:
                    return f"Would you like to know how to {action}?"
            else:
                return "Would you like to know how we can help you?"
        
        elif "where" in q_lower:
            return "Would you like to know how to visit us?"
        
        elif "who" in q_lower:
            if "research" in q_lower:
                return "Would you like to know about our research team?"
            elif "team" in q_lower:
                return "Would you like to know about our team?"
            else:
                return "Would you like to know about our team?"
        
        elif "when" in q_lower:
            return "Would you like to know about our programs?"
        
        # Default pattern
        if q_lower.startswith("are "):
            topic = q_lower.replace("are ", "").strip()
            if "internships" in topic and "paid" in topic:
                return "Would you like to know about our internship opportunities?"
            return f"Would you like to know about {topic}?"
        
        # Generic fallback
        if len(q_lower.split()) <= 10:  # Short questions
            return f"Would you like to know more about {selected_question.lower()}?"
        
        return f"Would you like to know about our programs?"
    
    @staticmethod
    def generate_followup(selected_question: str, use_fast: bool = True) -> Optional[str]:
        """
        Generate a follow-up question in invitation format.
        
        Args:
            selected_question: The question to convert to follow-up format
            use_fast: Use fast pattern matching instead of LLM (default: True for speed)
            
        Returns:
            Follow-up question string or None if generation fails
        """
        # Use fast pattern-based generation by default (much faster)
        if use_fast:
            follow_up_question = FollowupService.generate_followup_fast(selected_question)
            if follow_up_question:
                print(f"Generated follow-up question (fast): {follow_up_question} (based on: {selected_question})")
                return follow_up_question
        
        # Fallback to LLM if fast method didn't work (rarely needed)
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
            
            print(f"Generated follow-up question from LLM: {follow_up_question} (based on: {selected_question})")
            return follow_up_question
        except Exception as e:
            print(f"Error generating follow-up question: {e}")
            # Fallback to fast method if LLM fails
            return FollowupService.generate_followup_fast(selected_question)

