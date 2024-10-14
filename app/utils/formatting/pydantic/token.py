from pydantic import BaseModel


class AuthToken(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str | None = None
