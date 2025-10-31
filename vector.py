from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
import os
import pandas as pd
from dotenv import load_dotenv, find_dotenv

# Load environment variables
_dotenv_path = find_dotenv(usecwd=True)
if _dotenv_path:
    load_dotenv(_dotenv_path)
else:
    load_dotenv()

# Initialize HuggingFace embeddings (free, no API key needed)
# Using a lightweight model that works well for semantic search
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    model_kwargs={'device': 'cpu'},  # Use CPU in Docker
    encode_kwargs={'normalize_embeddings': True}
)

df = pd.read_csv("nithub_question.csv")

db_location = "./chrome_langchain_db_nithub"

# Create vector store
vector_store = Chroma(
    collection_name="nithub_qa",
    persist_directory=db_location,
    embedding_function=embeddings
)

# Check if collection is empty and add documents if needed
collection_count = vector_store._collection.count()
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
    
    vector_store.add_documents(documents=documents, ids=ids)
    print(f"Added {len(documents)} documents to Chroma database")
else:
    print(f"Collection already contains {collection_count} documents")
    
retriever = vector_store.as_retriever(
    search_kwargs={"k":5}
)