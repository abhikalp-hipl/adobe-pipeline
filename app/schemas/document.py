from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models import DocumentStatus


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime
