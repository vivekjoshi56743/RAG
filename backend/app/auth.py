from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import firebase_admin
from firebase_admin import auth as firebase_auth, credentials

from app.config import settings

_firebase_app = None

def get_firebase_app():
    global _firebase_app
    if _firebase_app is None:
        cred = credentials.ApplicationDefault()
        _firebase_app = firebase_admin.initialize_app(cred, {
            "projectId": settings.firebase_project_id
        })
    return _firebase_app


bearer_scheme = HTTPBearer()


async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    """Verify Firebase JWT and return the decoded token payload."""
    if settings.dev_auth_enabled:
        if creds.credentials != settings.dev_auth_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid development token",
            )
        return {
            "uid": settings.dev_auth_uid,
            "email": settings.dev_auth_email,
            "dev_auth": True,
        }

    get_firebase_app()
    try:
        decoded = firebase_auth.verify_id_token(creds.credentials)
        return decoded
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
