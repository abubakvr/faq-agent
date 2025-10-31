"""Configuration and initialization utilities."""

import os
import pandas as pd
from dotenv import load_dotenv, find_dotenv
import google.generativeai as genai


def load_environment():
    """Load environment variables from .env file."""
    _dotenv_path = find_dotenv(usecwd=True)
    if _dotenv_path:
        load_dotenv(_dotenv_path)
    else:
        load_dotenv()


_gemini_model = None


def get_gemini_model():
    """
    Initialize and return Gemini model (singleton pattern).
    
    Returns:
        Configured Gemini GenerativeModel
        
    Raises:
        RuntimeError: If GOOGLE_API_KEY is not set
    """
    global _gemini_model
    if _gemini_model is None:
        load_environment()
        
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY is not set. Please add it to .env or export it before starting the server.")
        
        print(f"GOOGLE_API_KEY detected: {'*' * (len(api_key) - 4) + api_key[-4:]}\n")
        genai.configure(api_key=api_key)
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        _gemini_model = genai.GenerativeModel(model_name)
    
    return _gemini_model


_csv_df = None


def get_csv_dataframe(csv_path: str = "nithub_question.csv") -> pd.DataFrame:
    """
    Load CSV file as pandas DataFrame (singleton pattern).
    
    Args:
        csv_path: Path to the CSV file
        
    Returns:
        DataFrame containing the CSV data
    """
    global _csv_df
    if _csv_df is None:
        _csv_df = pd.read_csv(csv_path)
    return _csv_df

