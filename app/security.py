from __future__ import annotations

import hashlib
import hmac

from fastapi import HTTPException, Request, status

from app.config import Settings


def hash_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def verify_bearer_token(settings: Settings, authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization: Bearer token",
        )
    supplied = authorization.split(" ", 1)[1].strip()
    if not supplied:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Empty API key")
    if not any(hmac.compare_digest(supplied, valid) for valid in settings.api_keys):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return supplied


def optional_bearer_token(settings: Settings, authorization: str | None) -> str | None:
    if not settings.require_api_auth:
        return None
    return verify_bearer_token(settings, authorization)
