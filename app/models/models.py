from pydantic import BaseModel # type: ignore
from typing import List

class ChatMessage(BaseModel):
    type: str
    content: str

class InvokeRequest(BaseModel):
    messages: List[ChatMessage]

class InvokeResponse(BaseModel):
    messages: List[ChatMessage]

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: str | None = None
