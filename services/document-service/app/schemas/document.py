from datetime import datetime

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: str
    user_id: str
    filename: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
