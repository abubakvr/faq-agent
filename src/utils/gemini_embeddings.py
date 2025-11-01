"""
Custom Gemini embeddings using direct API endpoint to avoid batch API quota limits.
This bypasses the genai.embed_content() batch API which has stricter quota limits.
"""

import os
import requests
from typing import List, Optional
from langchain_core.embeddings import Embeddings
import time


class GeminiDirectEmbeddings(Embeddings):
    """Custom Gemini embeddings using direct HTTP API endpoint."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "models/text-embedding-004",
        batch_size: int = 10,  # Process multiple texts per request
        rate_limit_delay: float = 0.1,  # Delay between requests to avoid rate limits
    ):
        """Initialize Gemini direct embeddings.
        
        Args:
            api_key: Google API key. If None, reads from GOOGLE_API_KEY env var.
            model: Model name (default: text-embedding-004, also supports embedding-001)
            batch_size: Number of texts to embed in parallel (within rate limits)
            rate_limit_delay: Delay in seconds between API calls
        """
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY is required. Set it as parameter or environment variable.")
        
        self.model = model
        # Build endpoint URL from model name
        # Remove "models/" prefix if present for endpoint construction
        model_name = model.replace("models/", "")
        self.api_endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:embedContent"
        self.batch_size = batch_size
        self.rate_limit_delay = rate_limit_delay
        
        # Set headers
        self.headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json"
        }
    
    def _embed_single(self, text: str) -> List[float]:
        """Embed a single text using direct API call."""
        # Use the model name in the payload (some endpoints require it)
        payload = {
            "model": self.model,
            "content": {
                "parts": [{"text": text}]
            }
        }
        
        try:
            response = requests.post(
                self.api_endpoint,
                headers=self.headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            
            # Extract embedding from response
            if "embedding" in result and "values" in result["embedding"]:
                return result["embedding"]["values"]
            else:
                raise ValueError(f"Unexpected API response format: {result}")
                
        except requests.exceptions.HTTPError as e:
            if response.status_code == 429:
                raise ValueError(
                    f"Quota exceeded. Response: {response.text}. "
                    "You may need to upgrade your API plan or wait for quota reset."
                )
            raise ValueError(f"API error: {e}, Response: {response.text}")
        except requests.exceptions.RequestException as e:
            raise ValueError(f"Network error calling Gemini API: {e}")
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple documents using direct API calls with rate limiting."""
        embeddings = []
        
        for i, text in enumerate(texts):
            if i > 0:
                time.sleep(self.rate_limit_delay)  # Rate limiting
            
            embedding = self._embed_single(text)
            embeddings.append(embedding)
            
            # Log progress for large batches
            if (i + 1) % 10 == 0:
                print(f"Embedded {i + 1}/{len(texts)} documents...")
        
        return embeddings
    
    def embed_query(self, text: str) -> List[float]:
        """Embed a single query text."""
        return self._embed_single(text)

