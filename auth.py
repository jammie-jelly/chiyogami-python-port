from fastapi import HTTPException, status, Request

async def require_session(request: Request):
    """Require a server-side session cookie."""

    if request is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing request")

    session = getattr(request, "session", None)
    user_id = session.get("user_id") if session else None

    if user_id:
        return {"type": "session", "user_id": user_id}

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing session")
