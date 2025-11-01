from langchain_chroma import Chroma
from langchain_core.documents import Document
import os
import pandas as pd
from dotenv import load_dotenv, find_dotenv
from src.utils.gemini_embeddings import GeminiDirectEmbeddings

import threading

# Lazy initialization variables
_embeddings = None
_vector_store = None
_retriever = None
_initialized = False
_initialization_lock = threading.Lock()
_initializing = False


def _initialize_vector_store():
    """Initialize vector store and embeddings (lazy loading to speed up startup)."""
    global _embeddings, _vector_store, _retriever, _initialized, _initializing
    
    # Double-check locking pattern
    if _initialized:
        return
    
    with _initialization_lock:
        # Check again after acquiring lock
        if _initialized:
            return
        
        if _initializing:
            # Wait for other thread to finish initialization
            while not _initialized:
                import time
                time.sleep(0.1)
            return
        
        _initializing = True
    
    try:
        print("Initializing vector store and embeddings...")
        
        # Load environment variables
        _dotenv_path = find_dotenv(usecwd=True)
        if _dotenv_path:
            load_dotenv(_dotenv_path)
        else:
            load_dotenv()

        # Initialize Gemini embeddings using direct API endpoint
        # This bypasses the batch API which has stricter quota limits
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY is required for Gemini embeddings. Please set it in .env file.")
        
        print("Initializing Gemini embeddings (direct API endpoint)...")
        _embeddings = GeminiDirectEmbeddings(
            api_key=api_key,
            model="models/text-embedding-004",  # Use text-embedding-004 for better quality
            rate_limit_delay=0.15  # 150ms delay between requests to avoid rate limits
        )
        print("Gemini embeddings initialized.")

        # Read CSV file
        print("Reading CSV file...")
        df = pd.read_csv("nithub_question.csv")

        db_location = "./chrome_langchain_db_nithub"

        # Create vector store
        # Note: If switching embedding models, the database will be automatically deleted
        # if dimension mismatch is detected
        print("Initializing Chroma vector store...")
        
        import shutil
        import pathlib
        
        # Try to create/open the vector store
        try:
            _vector_store = Chroma(
                collection_name="nithub_qa",
                persist_directory=db_location,
                embedding_function=_embeddings
            )
            # Test that the store works by getting collection count
            # This will raise an error if dimensions don't match
            _ = _vector_store._collection.count()
        except Exception as e:
            error_msg = str(e)
            # Check if it's a dimension mismatch error
            if "dimension" in error_msg.lower() or "384" in error_msg or "768" in error_msg:
                print(f"⚠️  Dimension mismatch detected: {error_msg}")
                print(f"🗑️  Deleting old database to recreate with correct dimensions...")
                db_path = pathlib.Path(db_location)
                if db_path.exists():
                    shutil.rmtree(db_location)
                    print(f"✓ Database deleted. Recreating with new embedding dimensions.")
                # Now create a fresh database
                _vector_store = Chroma(
                    collection_name="nithub_qa",
                    persist_directory=db_location,
                    embedding_function=_embeddings
                )
            else:
                # Different error, re-raise it
                raise

        # Check if collection is empty and add documents if needed
        collection_count = _vector_store._collection.count()
        print(f"Chroma collection count: {collection_count}")

        if collection_count == 0:
            print("Collection is empty. Adding documents from CSV...")
            documents = []
            ids = []
            
            for i, row in df.iterrows():
                qa_text = f"Q: {row['Question']}\nA: {row['Answer']}"
                document = Document(
                    page_content=qa_text,
                    metadata={"source": "nithub_faq"},
                    id=str(i)
                )
                ids.append(str(i))
                documents.append(document)
            
            _vector_store.add_documents(documents=documents, ids=ids)
            print(f"Added {len(documents)} documents to Chroma database")
        else:
            print(f"Collection already contains {collection_count} documents")
        
        _retriever = _vector_store.as_retriever(
            search_kwargs={"k":5}
        )
        
        with _initialization_lock:
            _initialized = True
            _initializing = False
        
        print("Vector store initialization complete.")
    except Exception as e:
        with _initialization_lock:
            _initializing = False
        raise


# Property to get retriever (initializes on first access)
def get_retriever():
    """Get the retriever instance, initializing if needed."""
    if not _initialized:
        _initialize_vector_store()
    return _retriever


# For backward compatibility, create a property that triggers initialization
class RetrieverProxy:
    """Proxy class that initializes the retriever on first use."""
    
    def __getattr__(self, name):
        if not _initialized:
            _initialize_vector_store()
        return getattr(_retriever, name)
    
    def invoke(self, *args, **kwargs):
        """Invoke the retriever with the given arguments."""
        global _initialized, _vector_store, _retriever
        
        if not _initialized:
            _initialize_vector_store()
        
        try:
            return _retriever.invoke(*args, **kwargs)
        except Exception as e:
            error_msg = str(e)
            # Check if it's a dimension mismatch error during query
            if "dimension" in error_msg.lower() or "384" in error_msg or "768" in error_msg:
                print(f"⚠️  Dimension mismatch detected during query: {error_msg}")
                print(f"🗑️  Resetting database and reinitializing...")
                
                # Reset initialization state
                _initialized = False
                _vector_store = None
                _retriever = None
                
                # Delete the database
                import shutil
                import pathlib
                db_location = "./chrome_langchain_db_nithub"
                db_path = pathlib.Path(db_location)
                if db_path.exists():
                    shutil.rmtree(db_location)
                    print(f"✓ Database deleted. Reinitializing with correct dimensions...")
                
                # Reinitialize
                _initialize_vector_store()
                
                # Retry the query
                return _retriever.invoke(*args, **kwargs)
            else:
                # Different error, re-raise it
                raise


# Create proxy instance for backward compatibility
retriever = RetrieverProxy()