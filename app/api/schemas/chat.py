from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    telegram_chat_id: int
    message: str = Field(min_length=1, max_length=4096)
    sender_telegram_id: int
    chat_title: str | None = None
    chat_type: str | None = None
    sender_username: str | None = None
    sender_first_name: str | None = None
    sender_last_name: str | None = None
    mentions_bot: bool = False
    reply_to_bot: bool = False
    reply_to_other_user: bool = False


class ChatResponse(BaseModel):
    action: str
    reason: str
    reply: str | None = None
    context_count: int = 0
    relevance_score: float = 0.0
