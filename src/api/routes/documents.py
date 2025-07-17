"""
Document management endpoints
"""
import os
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.core.database import get_db
from src.core.models import Document
from src.core.config import settings
from src.schemas.document import DocumentResponse, DocumentCreate, DocumentUpdate
from src.services.document_processor import DocumentProcessor
from src.utils.file_utils import save_uploaded_file, validate_file

router = APIRouter()
document_processor = DocumentProcessor()

@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    document_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Upload and process a document"""
    
    # Validate file
    if not validate_file(file):
        raise HTTPException(status_code=400, detail="Invalid file type or size")
    
    try:
        # Save file
        file_path = await save_uploaded_file(file, settings.UPLOAD_DIR)
        
        # Create document record
        document = Document(
            filename=f"{uuid.uuid4()}_{file.filename}",
            original_filename=file.filename,
            file_path=file_path,
            file_size=file.size,
            file_type=file.filename.split('.')[-1].lower(),
            document_type=document_type or "unknown",
            processing_status="pending"
        )
        
        db.add(document)
        await db.commit()
        await db.refresh(document)
        
        # Process document in background
        background_tasks.add_task(process_document_task, document.id, file_path)
        
        return DocumentResponse(
            id=document.id,
            filename=document.filename,
            original_filename=document.original_filename,
            file_type=document.file_type,
            document_type=document.document_type,
            processing_status=document.processing_status,
            created_at=document.created_at
        )
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to upload document: {str(e)}")

@router.get("/", response_model=List[DocumentResponse])
async def list_documents(
    skip: int = 0,
    limit: int = 100,
    document_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """List all documents"""
    
    query = select(Document).offset(skip).limit(limit)
    
    if document_type:
        query = query.where(Document.document_type == document_type)
    
    result = await db.execute(query)
    documents = result.scalars().all()
    
    return [
        DocumentResponse(
            id=doc.id,
            filename=doc.filename,
            original_filename=doc.original_filename,
            file_type=doc.file_type,
            document_type=doc.document_type,
            processing_status=doc.processing_status,
            created_at=doc.created_at
        )
        for doc in documents
    ]

@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get document by ID"""
    
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return DocumentResponse(
        id=document.id,
        filename=document.filename,
        original_filename=document.original_filename,
        file_type=document.file_type,
        document_type=document.document_type,
        processing_status=document.processing_status,
        processed=document.processed,
        content=document.content,
        metadata=document.metadata,
        created_at=document.created_at,
        updated_at=document.updated_at
    )

@router.delete("/{document_id}")
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete document"""
    
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Delete file
    if os.path.exists(document.file_path):
        os.remove(document.file_path)
    
    await db.delete(document)
    await db.commit()
    
    return {"message": "Document deleted successfully"}

async def process_document_task(document_id: uuid.UUID, file_path: str):
    """Background task to process document"""
    try:
        await document_processor.process_document_async(document_id, file_path)
    except Exception as e:
        print(f"Error processing document {document_id}: {e}")
