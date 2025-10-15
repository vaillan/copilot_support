from sqlmodel import Field, SQLModel, Relationship
from typing import Optional, List

class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    email: str = Field(default=None)
    hashed_password: str = Field(default=None)
    disabled: bool = Field(default=False)

class Thread(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str | None = Field(default=None, index=True)
    description: str | None = Field(default=None, index=True)
    messages: List["Messages"] = Relationship(back_populates="thread")

class Messages(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    type: Optional[str] = Field(default=None)
    content: Optional[str] = Field(default=None)
    thread_id: Optional[int] = Field(default=None, foreign_key="thread.id")
    thread: Optional["Thread"] = Relationship(back_populates="messages")
