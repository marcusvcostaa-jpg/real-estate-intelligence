from pydantic import BaseModel, Field

from app.models.enums import UserRole


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105 (OAuth token type, not a secret)


class UserOut(BaseModel):
    id: int
    email: str
    role: UserRole

    model_config = {"from_attributes": True}
