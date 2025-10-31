"""Routes for session endpoints."""

from fastapi import APIRouter, HTTPException

from ..controllers.session_controller import SessionController
from ..types.schemas import APIResponse, SessionInfoResponse, SessionAPIResponse

router = APIRouter(tags=["Session"])


@router.get("/session/{session_id}", response_model=SessionAPIResponse)
async def get_session_info(session_id: str):
    """
    Get information about a session.
    Returns session data if exists, or error response if session expired/not found.
    """
    controller = SessionController()
    try:
        result = controller.get_session_info(session_id)
        # Convert dict to SessionInfoResponse
        session_info = SessionInfoResponse(**result)
        return APIResponse(
            status=True,
            code="00",
            message="Response retrieved successfully",
            data=session_info
        )
    except ValueError as e:
        return APIResponse(
            status=False,
            code="01",
            message=str(e),
            data={}  # Empty dict for errors
        )
    except Exception as e:
        return APIResponse(
            status=False,
            code="01",
            message=f"Error retrieving session: {str(e)}",
            data={}  # Empty dict for errors
        )

