"""
backend/services/auth.py — Bearer token verification.

Reads MORI_TOKEN from environment.  If the variable is not set (or empty),
all requests are accepted (development mode).

Usage in FastAPI:
    from backend.services.auth import verify_token

    router = APIRouter(dependencies=[Depends(verify_token)])

    # or per-endpoint:
    @router.get("/protected")
    async def protected(creds=Depends(verify_token)):
        ...
"""

from __future__ import annotations

import os

import structlog
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

log = structlog.get_logger(__name__)

_bearer = HTTPBearer(auto_error=False)


async def verify_token(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> HTTPAuthorizationCredentials | None:
    """
    Validate the Authorization: Bearer <token> header.

    - If MORI_TOKEN is unset or empty  → dev mode, all requests pass.
    - If MORI_TOKEN is set             → header must be present and match exactly.

    Returns the credentials object (or None in dev mode).
    Raises HTTP 401 on mismatch.
    """
    token = os.environ.get("MORI_TOKEN", "").strip()
    if not token:
        # Dev mode — no auth required
        return credentials

    if not credentials:
        log.warning("auth.missing_token")
        raise HTTPException(
            status_code=401,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if credentials.credentials != token:
        log.warning("auth.invalid_token")
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return credentials
