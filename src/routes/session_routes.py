"""Routes for session endpoints."""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse

from ..controllers.session_controller import SessionController
from ..types.schemas import APIResponse, SessionInfoResponse, SessionAPIResponse

router = APIRouter(tags=["Session"])


@router.get("/session/{session_id}", response_model=SessionAPIResponse, status_code=status.HTTP_200_OK)
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
        # Session not found or expired - return 404
        error_msg = str(e).lower()
        if "not found" in error_msg or "expired" in error_msg:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=APIResponse(
                    status=False,
                    code="01",
                    message=str(e),
                    data={}
                ).model_dump()
            )
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=APIResponse(
                status=False,
                code="01",
                message=str(e),
                data={}
            ).model_dump()
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=APIResponse(
                status=False,
                code="01",
                message=f"Error retrieving session: {str(e)}",
                data={}
            ).model_dump()
        )

