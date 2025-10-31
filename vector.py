from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
import os
import pandas as pd
from dotenv import load_dotenv, find_dotenv

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

        # Initialize HuggingFace embeddings (free, no API key needed)
        # Using a lightweight model that works well for semantic search
        print("Loading HuggingFace embeddings model...")
        _embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={'device': 'cpu'},  # Use CPU in Docker
            encode_kwargs={'normalize_embeddings': True}
        )
        print("Embeddings model loaded.")

        # Read CSV file
        print("Reading CSV file...")
        df = pd.read_csv("nithub_question.csv")

        db_location = "./chrome_langchain_db_nithub"

        # Create vector store
        print("Initializing Chroma vector store...")
        _vector_store = Chroma(
            collection_name="nithub_qa",
            persist_directory=db_location,
            embedding_function=_embeddings
        )

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
        if not _initialized:
            _initialize_vector_store()
        return _retriever.invoke(*args, **kwargs)


# Create proxy instance for backward compatibility
retriever = RetrieverProxy()