"""Main FastAPI application entry point."""

import asyncio
from fastapi import FastAPI

from database import init_db
from migrate import run_migrations
from src.helpers.session_manager import periodic_cleanup
from src.routes import qa_router, conversation_router, session_router

# Initialize FastAPI app
app = FastAPI(
    title="Nithub QA API",
    description="API to answer questions about Nithub using a curated Q&A knowledge base.",
)

# Register routes
app.include_router(qa_router)
app.include_router(conversation_router)
app.include_router(session_router)


@app.on_event("startup")
async def startup_event():
    """Initialize database and start background tasks on startup."""
    try:
        # Run migrations first to ensure schema is up to date
        run_migrations()
        
        # Initialize database tables (creates tables if they don't exist)
        init_db()
        print("Database initialized successfully")
    except Exception as e:
        print(f"Database initialization error: {e}")
        raise  # Re-raise to prevent starting with broken database
    
    # Start background task for session cleanup
    asyncio.create_task(periodic_cleanup())
    print("Session cleanup task started")


@app.get("/")
async def root():
    """Root endpoint for health check."""
    return {"message": "Nithub QA API is running!"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

