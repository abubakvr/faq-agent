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
        # Use correct endpoint format: https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent
        self.api_endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:embedContent"
        self.batch_size = batch_size
        self.rate_limit_delay = rate_limit_delay
        
        # Set headers with API key
        self.headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json"
        }
    
    def _embed_single(self, text: str) -> List[float]:
        """Embed a single text using direct API call with retry logic."""
        # Payload format according to Gemini API documentation
        # For embedContent, the payload should include model and content
        payload = {
            "model": f"models/{self.model.replace('models/', '')}",  # Ensure models/ prefix
            "content": {
                "parts": [{"text": text}]
            }
        }
        
        max_retries = 3
        last_exception = None
        
        for attempt in range(max_retries):
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
                if hasattr(e, 'response') and e.response is not None:
                    status_code = e.response.status_code
                    response_text = e.response.text
                    
                    if status_code == 429:
                        raise ValueError(
                            f"Quota exceeded. Response: {response_text}. "
                            "You may need to upgrade your API plan or wait for quota reset."
                        )
                    elif status_code == 400:
                        # 400 errors usually indicate payload format issues
                        raise ValueError(
                            f"Bad Request (400): Invalid payload format. "
                            f"This may indicate an issue with the request structure. "
                            f"Response: {response_text}. "
                            f"Endpoint: {self.api_endpoint}. "
                            f"Payload: {payload}"
                        )
                    else:
                        raise ValueError(f"API error (HTTP {status_code}): {e}, Response: {response_text}")
                raise ValueError(f"API error: {e}")
                
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                last_exception = e
                error_str = str(e)
                
                # Check if it's a DNS resolution error
                if "Failed to resolve" in error_str or "NameResolutionError" in error_str or "Temporary failure in name resolution" in error_str:
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 2  # Exponential backoff: 2s, 4s, 6s
                        print(f"⚠️  DNS resolution failed. Retrying in {wait_time} seconds... (attempt {attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise RuntimeError(
                            f"Network error: Cannot resolve 'generativelanguage.googleapis.com'. "
                            f"This indicates a DNS or network connectivity issue. "
                            f"Please check:\n"
                            f"1. Internet connectivity\n"
                            f"2. DNS server configuration\n"
                            f"3. Firewall rules allowing outbound HTTPS connections\n"
                            f"4. If running in Docker, ensure the container has network access\n"
                            f"Original error: {e}"
                        )
                else:
                    # Other connection errors - retry
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 2
                        print(f"⚠️  Connection error. Retrying in {wait_time} seconds... (attempt {attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise RuntimeError(f"Network error calling Gemini API after {max_retries} attempts: {e}")
                        
            except requests.exceptions.RequestException as e:
                # Catch-all for other request exceptions
                last_exception = e
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    print(f"⚠️  Request error. Retrying in {wait_time} seconds... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    raise RuntimeError(f"Network error calling Gemini API after {max_retries} attempts: {e}")
        
        # If we get here, all retries failed
        if last_exception:
            raise RuntimeError(f"Network error calling Gemini API after {max_retries} attempts: {last_exception}")
        else:
            raise RuntimeError("Network error calling Gemini API: Unknown error")
    
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

