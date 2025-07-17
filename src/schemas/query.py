"""
Pydantic schemas for query-related operations
"""
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

class QueryRequest(BaseModel):
    query: str = Field(..., description="Natural language query")
    max_results: Optional[int] = Field(10, description="Maximum number of search results")
    include_metadata: Optional[bool] = Field(True, description="Include metadata in response")

class QueryResponse(BaseModel):
    query_id: uuid.UUID
    decision: str = Field(..., description="Decision: APPROVED, REJECTED, NEEDS_REVIEW")
    amount: float = Field(0.0, description="Benefit amount if applicable")
    justification: Dict[str, Any] = Field(..., description="Detailed justification")
    confidence_score: float = Field(..., description="Confidence in decision (0-1)")
    processing_time: float = Field(..., description="Processing time in seconds")
    search_results: List[Dict[str, Any]] = Field(..., description="Relevant search results")
    parsed_entities: Dict[str, Any] = Field(..., description="Extracted entities from query")

class QueryLogResponse(BaseModel):
    id: uuid.UUID
    query_text: str
    parsed_entities: Optional[Dict[str, Any]] = None
    search_results: Optional[List[Dict[str, Any]]] = None
    decision: str
    decision_amount: float
    confidence_score: float
    processing_time: float
    justification: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True
