"""Main FastAPI application entry point."""

import asyncio
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware

from src.config.database import init_db
from scripts.migrate import run_migrations
from src.vector import get_retriever
from src.helpers.session_manager import periodic_cleanup
from src.routes import qa_router, conversation_router, session_router
from src.types.schemas import APIResponse, RootAPIResponse

# Initialize FastAPI app
app = FastAPI(
    title="Nithub QA API",
    description="API to answer questions about Nithub using a curated Q&A knowledge base.",
)

# Configure CORS to allow all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=False,  # Cannot be True when allow_origins=["*"]
    allow_methods=["*"],  # Allow all HTTP methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],  # Allow all headers
)

# Register routes
app.include_router(qa_router)
app.include_router(conversation_router)
app.include_router(session_router)


@app.on_event("startup")
async def startup_event():
    """Initialize database, vector store, and start background tasks on startup."""
    try:
        # Run migrations first to ensure schema is up to date
        run_migrations()
        
        # Initialize database tables (creates tables if they don't exist)
        init_db()
        print("Database initialized successfully")
    except Exception as e:
        print(f"Database initialization error: {e}")
        raise  # Re-raise to prevent starting with broken database
    
    # Initialize vector store in background (non-blocking)
    # This initializes Gemini embeddings and sets up ChromaDB
    print("Starting vector store initialization in background...")
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, get_retriever)
    
    # Start background task for session cleanup
    asyncio.create_task(periodic_cleanup())
    print("Session cleanup task started")


@app.get("/", response_model=RootAPIResponse, status_code=status.HTTP_200_OK)
async def root():
    """Root endpoint for health check."""
    return APIResponse(
        status=True,
        code="00",
        message="Nithub QA API is running!",
        data={"message": "Nithub QA API is running!"}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

