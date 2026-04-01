import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import authenticate_user, create_access_token
from ..config import get_settings
from ..database import get_db
from ..schemas import LoginRequest, OAuthExchangeRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = authenticate_user(db, payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    token = create_access_token({"sub": user.username})
    return TokenResponse(access_token=token)


@router.post("/oauth/exchange", response_model=TokenResponse)
async def oauth_exchange(payload: OAuthExchangeRequest) -> TokenResponse:
    if not settings.oauth_introspection_url:
        raise HTTPException(status_code=501, detail="OAuth introspection is not configured")

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            settings.oauth_introspection_url,
            data={
                "token": payload.provider_token,
                "client_id": settings.oauth_client_id,
                "client_secret": settings.oauth_client_secret,
            },
        )
        if resp.status_code >= 400:
            raise HTTPException(status_code=401, detail="OAuth token validation failed")
        body = resp.json()

    username = body.get("username") or body.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="OAuth token did not include principal")

    token = create_access_token({"sub": username})
    return TokenResponse(access_token=token)
