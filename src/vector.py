from langchain_chroma import Chroma
from langchain_core.documents import Document
import os
import pandas as pd
from dotenv import load_dotenv, find_dotenv
from .utils.gemini_embeddings import GeminiDirectEmbeddings

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
        # Get the project root (parent of src)
        import pathlib
        project_root = pathlib.Path(__file__).parent.parent
        csv_path = project_root / "src" / "data" / "nithub_question.csv"
        df = pd.read_csv(csv_path)

        db_location = "./chrome_langchain_db_nithub"

        # Create vector store
        # Note: If switching embedding models, the database will be automatically deleted
        # if dimension mismatch is detected
        print("Initializing Chroma vector store...")
        
        import shutil
        import pathlib
        
        # Try to create/open the vector store
        _vector_store = None
        try:
            _vector_store = Chroma(
                collection_name="nithub_qa",
                persist_directory=db_location,
                embedding_function=_embeddings
            )
            # Test that the store works by getting collection count
            # This will raise an error if dimensions don't match or database is corrupted
            _ = _vector_store._collection.count()
        except (KeyError, Exception) as e:
            error_msg = str(e)
            error_type = type(e).__name__
            
            # Check if it's a dimension mismatch error
            is_dimension_error = "dimension" in error_msg.lower() or "384" in error_msg or "768" in error_msg
            
            # Check if it's a database corruption error (missing _type field in ChromaDB config)
            is_corruption_error = (
                error_type == "KeyError" and "_type" in error_msg
            ) or (
                "configuration" in error_msg.lower() and "_type" in error_msg
            ) or (
                "from_json" in error_msg.lower() and "_type" in error_msg
            )
            
            if is_dimension_error or is_corruption_error:
                if is_corruption_error:
                    print(f"⚠️  Database corruption detected (KeyError: '_type'): {error_msg}")
                    print(f"🗑️  Deleting corrupted database to recreate...")
                else:
                    print(f"⚠️  Dimension mismatch detected: {error_msg}")
                    print(f"🗑️  Deleting old database to recreate with correct dimensions...")
                
                # Close ChromaDB connection if it was partially created
                if _vector_store is not None:
                    try:
                        # Try to properly close ChromaDB connections
                        if hasattr(_vector_store, '_client') and _vector_store._client:
                            try:
                                # ChromaDB client cleanup
                                if hasattr(_vector_store._client, '_admin_client'):
                                    _vector_store._client._admin_client = None
                                if hasattr(_vector_store._client, '_server'):
                                    _vector_store._client._server = None
                            except:
                                pass
                            _vector_store._client = None
                        if hasattr(_vector_store, '_chroma_collection'):
                            _vector_store._chroma_collection = None
                    except:
                        pass
                    _vector_store = None
                
                # Force garbage collection to release file handles
                import gc
                gc.collect()
                
                # Wait a moment for file handles to release
                import time
                time.sleep(1)
                
                # Delete the database with retry logic
                db_path = pathlib.Path(db_location)
                if db_path.exists():
                    max_retries = 5
                    deleted = False
                    for attempt in range(max_retries):
                        try:
                            # Try to remove files individually first (more reliable)
                            if db_path.is_dir():
                                # Remove contents first
                                for item in db_path.iterdir():
                                    if item.is_dir():
                                        shutil.rmtree(item, ignore_errors=True)
                                    else:
                                        try:
                                            item.unlink()
                                        except:
                                            pass
                                # Then remove the directory
                                db_path.rmdir()
                            shutil.rmtree(db_location, ignore_errors=True)
                            print(f"✓ Database deleted. Recreating with fresh database.")
                            deleted = True
                            break
                        except (OSError, PermissionError) as delete_error:
                            if attempt < max_retries - 1:
                                wait_time = (attempt + 1) * 0.5
                                print(f"⚠️  Database locked, retrying in {wait_time} seconds... (attempt {attempt + 1}/{max_retries})")
                                time.sleep(wait_time)
                            else:
                                print(f"⚠️  Could not delete database (still locked after {max_retries} attempts).")
                                print(f"⚠️  Please manually delete the volume: docker volume rm faq-agent_chroma_data")
                                print(f"⚠️  Or restart the container to release file locks.")
                                # Use a timestamped location as fallback
                                import datetime
                                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                                db_location = f"./chrome_langchain_db_nithub_{timestamp}"
                                print(f"Using new database location: {db_location}")
                                deleted = True  # Mark as handled
                                break
                
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
        except (KeyError, Exception) as e:
            error_msg = str(e)
            error_type = type(e).__name__
            
            # Check if it's a dimension mismatch error during query
            is_dimension_error = "dimension" in error_msg.lower() or "384" in error_msg or "768" in error_msg
            
            # Check if it's a database corruption error
            is_corruption_error = (
                error_type == "KeyError" and "_type" in error_msg
            ) or (
                "configuration" in error_msg.lower() and "_type" in error_msg
            ) or (
                "from_json" in error_msg.lower() and "_type" in error_msg
            )
            
            if is_dimension_error or is_corruption_error:
                if is_corruption_error:
                    print(f"⚠️  Database corruption detected during query (KeyError: '_type'): {error_msg}")
                else:
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
                    print(f"✓ Database deleted. Reinitializing with fresh database...")
                
                # Reinitialize
                _initialize_vector_store()
                
                # Retry the query
                return _retriever.invoke(*args, **kwargs)
            else:
                # Different error, re-raise it
                raise


# Create proxy instance for backward compatibility
retriever = RetrieverProxy()