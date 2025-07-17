"""
Pydantic schemas for document-related operations
"""
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

class DocumentCreate(BaseModel):
    filename: str
    document_type: Optional[str] = None

class DocumentUpdate(BaseModel):
    document_type: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class DocumentResponse(BaseModel):
    id: uuid.UUID
    filename: str
    original_filename: str
    file_type: str
    document_type: str
    processing_status: str
    processed: Optional[bool] = None
    content: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
