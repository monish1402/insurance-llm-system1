"""
File handling utilities
"""
import os
import uuid
import aiofiles
from pathlib import Path
from typing import Optional
from fastapi import UploadFile, HTTPException

from src.core.config import settings

async def save_uploaded_file(file: UploadFile, upload_dir: str) -> str:
    """Save uploaded file to disk"""
    
    # Create upload directory if it doesn't exist
    Path(upload_dir).mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename
    file_extension = file.filename.split('.')[-1] if '.' in file.filename else ''
    unique_filename = f"{uuid.uuid4()}.{file_extension}"
    file_path = os.path.join(upload_dir, unique_filename)
    
    # Save file
    async with aiofiles.open(file_path, 'wb') as buffer:
        content = await file.read()
        await buffer.write(content)
    
    return file_path

def validate_file(file: UploadFile) -> bool:
    """Validate uploaded file"""
    
    # Check file size
    if file.size > settings.MAX_FILE_SIZE:
        return False
    
    # Check file type
    if not file.filename:
        return False
    
    file_extension = file.filename.split('.')[-1].lower()
    if file_extension not in settings.ALLOWED_FILE_TYPES:
        return False
    
    return True
