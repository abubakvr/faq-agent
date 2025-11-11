"""Prompt templates for LLM interactions."""


def get_answer_prompt(context_block: str, question_text: str, previous_context: str = "", 
                     is_related: bool = False, recent_follow_ups: list = None) -> str:
    """
    Build the prompt for generating an answer and follow-up question in JSON format.
    
    Args:
        context_block: Knowledge base context
        question_text: The user's question
        previous_context: Previous conversation context
        is_related: Whether this is a follow-up question
        recent_follow_ups: List of recently suggested follow-up questions to avoid repetition
        
    Returns:
        Complete prompt string
    """
    recent_follow_ups = recent_follow_ups or []
    
    prompt_text = (
        "You are an expert assistant answering questions about Nithub (an innovation hub in Lagos).\n\n"
        "INSTRUCTIONS:\n"
        "- Use the knowledge entries provided below to answer the question.\n"
        "- You can combine information from multiple entries to provide a complete answer.\n"
        "- When referring to Nithub, always use 'we' or 'our' (first person from Nithub's perspective), never 'they' or 'their'.\n"
        "- If the question asks about location/where, use any location information from the entries.\n"
        "- If the question asks 'why', provide relevant context from the entries that explains the reason.\n"
        "- Answer in a natural, helpful way based on the provided knowledge entries.\n"
        "- IMPORTANT: Keep your answer concise. Maximum 300 words. Be direct and informative without unnecessary elaboration.\n"
        "- CRITICAL: Never start your answer with 'Yes', 'Yes,', 'Yes we', or any variation of 'Yes'. Start directly with the answer content.\n"
        "- If the question cannot be answered from the provided entries at all, then respond with: 'I don't have that information in my knowledge base. Please contact Nithub directly for this information.'\n\n"
    )
    
    # Add previous context if available
    if previous_context:
        prompt_text += f"Previous conversation context:\n{previous_context}\n"
        if is_related:
            prompt_text += "The current question is a follow-up or continuation of the previous conversation. Use both the previous context and the knowledge entries below to provide a comprehensive answer that builds on what was discussed.\n\n"
        else:
            prompt_text += "Use the previous conversation context to provide consistent information. The knowledge entries below should be used to answer the current question.\n\n"
    
    # Extract available questions from context for follow-up selection
    prompt_text += (
        f"Knowledge entries from CSV:\n{context_block}\n\n"
        f"Question: {question_text}\n\n"
    )
    
    if recent_follow_ups:
        prompt_text += f"Recently suggested follow-up questions (avoid repeating these topics): {', '.join(recent_follow_ups[-3:])}\n\n"
    
    prompt_text += (
        "TASK: Return a JSON object with two fields:\n"
        "1. 'answer': Your answer to the question (maximum 300 words, use 'we' or 'our' when referring to Nithub)\n"
        "2. 'follow_up_question': A follow-up question in invitation format starting with 'Would you like to know'\n\n"
        "For the follow-up question:\n"
        "- Select a question from the knowledge entries above (either related to the current topic OR a different interesting topic for variety)\n"
        "- Extract the TOPIC or ACTION from the selected question, NOT the literal question text\n"
        "- Convert it to a natural phrase like 'how you can visit', 'what our programs are', 'how to apply', etc.\n"
        "- Use the format: 'Would you like to know more about [natural phrase]?'\n"
        "- Do NOT include the original question text verbatim\n"
        "- Use 'you' or 'we' appropriately (e.g., 'how you can visit', 'what we offer', 'how to join us')\n"
        "- Be concise (one sentence ending with '?')\n"
        "- Be natural and inviting\n"
        "- Vary between related questions (60%) and random different topics (40%) for conversation variety\n"
        "- Avoid topics from recently suggested follow-ups\n\n"
        "Examples of good follow-up question conversions:\n"
        "- Original: 'Can I visit Nithub in person?' → 'Would you like to know more about how you can visit us in person?'\n"
        "- Original: 'What training programs do you offer?' → 'Would you like to know more about what training programs we offer?'\n"
        "- Original: 'How do I apply?' → 'Would you like to know more about how to apply to our programs?'\n"
        "- Original: 'What is Nithub?' → 'Would you like to know more about our programs?'\n"
        "- Original: 'Where is Nithub located?' → 'Would you like to know more about how to visit us?'\n"
        "- Original: 'Are internships paid?' → 'Would you like to know more about our internship opportunities?'\n\n"
        "IMPORTANT:\n"
        "- Convert the question to a natural phrase, don't use the literal question text\n"
        "- Use proper capitalization (Nithub, not nithub)\n"
        "- Return ONLY valid JSON, no other text\n"
        "- Format:\n"
        '{\n'
        '  "answer": "your answer here",\n'
        '  "follow_up_question": "Would you like to know more about how you can [action/topic]?"\n'
        '}'
    )
    
    return prompt_text


def get_followup_prompt(selected_question: str) -> str:
    """
    Build the prompt for generating a follow-up question.
    
    Args:
        selected_question: The question to convert to follow-up format
        
    Returns:
        Complete prompt string
    """
    return (
        "Convert this question into an invitation format starting with 'Would you like to know'.\n\n"
        "The invitation should:\n"
        "- Start with 'Would you like to know' or 'Would you like to know about' or 'Would you like to know how to' or 'Would you like to know the benefits of'\n"
        "- Use varied formats (not always 'more about')\n"
        "- Use 'our' or 'we' when referring to Nithub\n"
        "- Be concise (one sentence ending with '?')\n"
        "- Be natural and inviting\n\n"
        f"Original question to convert: {selected_question}\n\n"
        "Examples of conversions:\n"
        "- 'What is Nithub?' → 'Would you like to know about our programs?'\n"
        "- 'Tell me about your incubation program' → 'Would you like to know the benefits of joining our incubation team?'\n"
        "- 'What training programs do you offer?' → 'Would you like to know the benefits of joining our programs?'\n"
        "- 'Where is Nithub located?' → 'Would you like to know how to sign up to our programs?'\n\n"
        "Generate ONLY the invitation question (no explanation):"
    )


def get_relation_check_prompt(previous_question: str, previous_answer: str, 
                             current_question: str, previous_followup: str = None) -> str:
    """
    Build the prompt for checking if two questions are related.
    
    Args:
        previous_question: The previous question
        previous_answer: The previous answer
        current_question: The current question
        previous_followup: Optional previous follow-up question
        
    Returns:
        Complete prompt string
    """
    prompt = (
        "Determine if these two questions are related to each other. "
        "They are related if the second question is a follow-up, clarification, continuation, or builds on the first.\n\n"
        f"Previous Question: {previous_question}\n"
        f"Previous Answer: {previous_answer}\n"
    )
    
    if previous_followup:
        prompt += f"Previous Follow-up Question: {previous_followup}\n"
    
    prompt += (
        f"Current Question: {current_question}\n\n"
        "Respond with only 'YES' if related, or 'NO' if not related:"
    )
    
    return prompt

