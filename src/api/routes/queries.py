"""
Query processing endpoints
"""
import time
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.core.database import get_db
from src.core.models import QueryLog
from src.schemas.query import QueryRequest, QueryResponse, QueryLogResponse
from src.services.query_processor import QueryProcessor
from src.services.semantic_search import SemanticSearchService
from src.services.decision_engine import DecisionEngine

router = APIRouter()
query_processor = QueryProcessor()
search_service = SemanticSearchService()
decision_engine = DecisionEngine()

@router.post("/process", response_model=QueryResponse)
async def process_query(
    request: QueryRequest,
    db: AsyncSession = Depends(get_db)
):
    """Process a natural language query"""
    
    start_time = time.time()
    
    try:
        # Parse query
        parsed_query = await query_processor.parse_query(request.query)
        
        # Search documents
        search_results = await search_service.search_documents(
            request.query,
            parsed_query.entities,
            top_k=request.max_results or 10
        )
        
        # Make decision
        decision_result = await decision_engine.make_decision(
            request.query,
            parsed_query.entities,
            search_results
        )
        
        processing_time = time.time() - start_time
        
        # Log query
        query_log = QueryLog(
            query_text=request.query,
            parsed_entities=parsed_query.entities,
            search_results=[
                {
                    "chunk_id": str(result.get("chunk_id", "")),
                    "text": result.get("text", ""),
                    "score": result.get("score", 0.0),
                    "section_type": result.get("section_type", "")
                }
                for result in search_results
            ],
            decision=decision_result.decision,
            decision_amount=decision_result.amount,
            confidence_score=decision_result.confidence,
            processing_time=processing_time,
            justification=decision_result.justification
        )
        
        db.add(query_log)
        await db.commit()
        
        return QueryResponse(
            query_id=query_log.id,
            decision=decision_result.decision,
            amount=decision_result.amount,
            justification=decision_result.justification,
            confidence_score=decision_result.confidence,
            processing_time=processing_time,
            search_results=search_results[:5],  # Return top 5 results
            parsed_entities=parsed_query.entities
        )
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to process query: {str(e)}")

@router.get("/history", response_model=List[QueryLogResponse])
async def get_query_history(
    skip: int = 0,
    limit: int = 100,
    decision: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get query history"""
    
    query = select(QueryLog).offset(skip).limit(limit).order_by(QueryLog.created_at.desc())
    
    if decision:
        query = query.where(QueryLog.decision == decision)
    
    result = await db.execute(query)
    query_logs = result.scalars().all()
    
    return [
        QueryLogResponse(
            id=log.id,
            query_text=log.query_text,
            decision=log.decision,
            decision_amount=log.decision_amount,
            confidence_score=log.confidence_score,
            processing_time=log.processing_time,
            created_at=log.created_at
        )
        for log in query_logs
    ]

@router.get("/{query_id}", response_model=QueryLogResponse)
async def get_query_details(
    query_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get detailed query results"""
    
    result = await db.execute(select(QueryLog).where(QueryLog.id == query_id))
    query_log = result.scalar_one_or_none()
    
    if not query_log:
        raise HTTPException(status_code=404, detail="Query not found")
    
    return QueryLogResponse(
        id=query_log.id,
        query_text=query_log.query_text,
        parsed_entities=query_log.parsed_entities,
        search_results=query_log.search_results,
        decision=query_log.decision,
        decision_amount=query_log.decision_amount,
        confidence_score=query_log.confidence_score,
        processing_time=query_log.processing_time,
        justification=query_log.justification,
        created_at=query_log.created_at
    )
