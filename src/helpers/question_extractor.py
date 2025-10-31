"""Helper functions for extracting questions from follow-up responses."""

import re


def extract_question_from_followup(follow_up_q: str) -> str:
    """
    Extract the actual question from 'Would you like to know [question]?' format.
    
    Args:
        follow_up_q: The follow-up question in invitation format
        
    Returns:
        The extracted question in direct format
    """
    extracted_q = follow_up_q
    
    # Remove common prefixes
    prefixes_to_remove = [
        "would you like to know ",
        "would you like to know about ",
        "would you like to know the ",
        "would you like to know how to ",
        "would you like to know how ",
        "would you like to ",
    ]
    
    follow_up_lower = follow_up_q.lower().strip("?.")
    for prefix in prefixes_to_remove:
        if follow_up_lower.startswith(prefix):
            # Extract what comes after the prefix
            remaining = follow_up_q[len(prefix):].strip("?.")
            
            # Convert to a question if it's not already one
            remaining = remaining.strip()
            if remaining:
                # Check if it already contains question words (what, how, when, where, why, who)
                has_question_word = any(
                    remaining.lower().startswith(qw + " ") or remaining.lower().startswith(qw) 
                    for qw in ["what", "how", "when", "where", "why", "who"]
                )
                
                if has_question_word:
                    # Already a question format, just fix "us"/"you" -> "Nithub" and ensure proper capitalization
                    extracted_q = remaining
                    
                    # Fix pronouns - be careful with word boundaries
                    # Replace " us " (with spaces) -> " Nithub "
                    extracted_q = re.sub(r'\b us \b', ' Nithub ', extracted_q, flags=re.IGNORECASE)
                    # Replace " us" at end -> " Nithub"
                    extracted_q = re.sub(r'\b us\b', ' Nithub', extracted_q, flags=re.IGNORECASE)
                    # Replace "us " at start -> "Nithub "
                    extracted_q = re.sub(r'\bus \b', 'Nithub ', extracted_q, flags=re.IGNORECASE)
                    
                    # Replace " you " (with spaces) -> " Nithub "
                    extracted_q = re.sub(r'\b you \b', ' Nithub ', extracted_q, flags=re.IGNORECASE)
                    # Replace " you" at end -> " Nithub"
                    extracted_q = re.sub(r'\b you\b', ' Nithub', extracted_q, flags=re.IGNORECASE)
                    # Replace "you " at start -> "Nithub "
                    extracted_q = re.sub(r'\byou \b', 'Nithub ', extracted_q, flags=re.IGNORECASE)
                    
                    # Clean up extra spaces
                    extracted_q = re.sub(r' +', ' ', extracted_q).strip()
                    
                    # Capitalize first letter if needed
                    if extracted_q and not extracted_q[0].isupper():
                        extracted_q = extracted_q[0].upper() + extracted_q[1:]
                elif remaining.lower().startswith("our "):
                    # "our programs" -> "What are our programs?"
                    topic = remaining[4:]  # Remove "our "
                    extracted_q = f"What are our {topic}?"
                elif remaining.lower().startswith("the "):
                    # "the benefits of..." -> "What are the benefits of...?"
                    topic = remaining[4:]  # Remove "the "
                    extracted_q = f"What are the {topic}?"
                elif remaining.lower().startswith("how to "):
                    # "how to sign up" -> "How do I sign up?"
                    action = remaining[7:]  # Remove "how to "
                    extracted_q = f"How do I {action}?"
                elif remaining.lower().startswith("how "):
                    # "how we support" -> "How do you support startups?"
                    extracted_q = f"How do you {remaining[4:]}?"
                else:
                    # Default: make it a "what is" or "tell me about" question
                    extracted_q = f"What is {remaining}?" if not any(word in remaining.lower() for word in ["about", "are", "is"]) else f"Tell me {remaining}?"
            
            if not extracted_q.endswith("?"):
                extracted_q += "?"
            
            break
    
    # If no prefix matched, try to convert the follow-up to a direct question
    if extracted_q == follow_up_q:
        # Remove "Would you like to know" if present
        if "would you like to know" in follow_up_lower:
            # Extract the part after "would you like to know"
            parts = follow_up_q.lower().split("would you like to know", 1)
            if len(parts) > 1:
                topic = parts[1].strip().strip("?.").strip()
                
                # Handle special cases based on topic content
                if "what makes" in topic or "what makes us" in topic or "what makes you" in topic:
                    # "what makes us stand out" -> "What makes Nithub stand out?"
                    if "us" in topic:
                        topic = topic.replace("us", "Nithub").replace("you", "Nithub")
                    if "stand out" in topic or "different" in topic:
                        extracted_q = f"What makes Nithub stand out?" if "stand out" in topic else f"What makes Nithub different?"
                    else:
                        extracted_q = f"What makes Nithub {topic.replace('what makes ', '').replace('what makes us ', '').replace('what makes you ', '')}?"
                elif topic.startswith("about "):
                    topic = topic[6:]
                    if topic.startswith("our "):
                        extracted_q = f"What are our {topic[4:]}?"
                    else:
                        extracted_q = f"Tell me about {topic}"
                elif topic.startswith("the "):
                    topic = topic[4:]
                    if "benefits" in topic:
                        extracted_q = f"What are the {topic}?"
                    else:
                        extracted_q = f"Tell me about the {topic}"
                elif topic.startswith("how to "):
                    topic = topic[7:]
                    extracted_q = f"How do I {topic}?"
                elif topic.startswith("how "):
                    # "how we support" -> "How do you support startups?"
                    topic = topic[4:]
                    extracted_q = f"How do you {topic}?"
                elif topic.startswith("our "):
                    extracted_q = f"Tell me about our {topic[4:]}"
                else:
                    # Check if it's already a question format
                    if any(word in topic.lower() for word in ["what", "how", "when", "where", "why", "who"]):
                        extracted_q = topic.capitalize() if not topic[0].isupper() else topic
                    else:
                        extracted_q = f"Tell me about {topic}"
                
                if not extracted_q.endswith("?"):
                    extracted_q += "?"
    
    return extracted_q

