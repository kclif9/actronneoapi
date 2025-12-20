"""Authentication models for Actron Air API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ActronAirDeviceCode(BaseModel):
    """Device code response model."""

    device_code: str = Field(..., description="Device verification code")
    user_code: str = Field(..., description="User verification code")
    verification_uri: str = Field(..., description="Verification URI")
    verification_uri_complete: str | None = Field(
        None, description="Complete verification URI with user code"
    )
    expires_in: int = Field(..., description="Expiration time in seconds")
    interval: int = Field(..., description="Polling interval in seconds")


class ActronAirToken(BaseModel):
    """OAuth2 token response model."""

    access_token: str = Field(..., description="Access token")
    refresh_token: str | None = Field(None, description="Refresh token")
    token_type: str = Field("Bearer", description="Token type")
    expires_in: int = Field(3600, description="Expiration time in seconds")
    scope: str | None = Field(None, description="Token scope")
