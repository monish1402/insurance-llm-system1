"""
Shared response schemas for consistent outputs
"""
from typing import Optional, Dict, Any
from pydantic import BaseModel

class BaseResponse(BaseModel):
    message: str
    status: str = "success"
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
