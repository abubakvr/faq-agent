"""Routes for session endpoints."""

from fastapi import APIRouter, HTTPException

from ..controllers.session_controller import SessionController

router = APIRouter(tags=["Session"])


@router.get("/session/{session_id}")
async def get_session_info(session_id: str):
    """
    Get information about a session.
    Returns session data if exists, or 404 if session expired/not found.
    """
    controller = SessionController()
    try:
        return controller.get_session_info(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving session: {str(e)}")

