"""
Document processing service for extracting and chunking text from various file formats
"""
import asyncio
import logging
import re
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

import PyPDF2
import docx
import spacy
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from src.core.database import AsyncSessionLocal
from src.core.models import Document, DocumentChunk
from src.services.embedding_service import EmbeddingService
from src.core.config import settings

logger = logging.getLogger(__name__)

@dataclass
class ProcessedChunk:
    text: str
    metadata: Dict[str, Any]
    section_type: str
    page_number: Optional[int] = None
    confidence_score: float = 0.0

class DocumentProcessor:
    def __init__(self):
        try:
            self.nlp = spacy.load("en_core_web_sm")
        except OSError:
            logger.warning("spaCy model not found. Install with: python -m spacy download en_core_web_sm")
            self.nlp = None
        
        self.embedding_service = EmbeddingService()
        
    async def process_document_async(self, document_id: uuid.UUID, file_path: str):
        """Process document asynchronously"""
        async with AsyncSessionLocal() as db:
            try:
                # Update status to processing
                await db.execute(
                    update(Document)
                    .where(Document.id == document_id)
                    .values(processing_status="processing")
                )
                await db.commit()
                
                # Get document
                result = await db.execute(select(Document).where(Document.id == document_id))
                document = result.scalar_one_or_none()
                
                if not document:
                    raise ValueError(f"Document {document_id} not found")
                
                # Process based on file type
                chunks = await self._process_file(file_path, document.file_type)
                
                # Generate embeddings and save chunks
                await self._save_chunks(db, document_id, chunks)
                
                # Update document status
                await db.execute(
                    update(Document)
                    .where(Document.id == document_id)
                    .values(
                        processed=True,
                        processing_status="completed",
                        content=self._extract_full_text(chunks)
                    )
                )
                await db.commit()
                
                logger.info(f"Successfully processed document {document_id} with {len(chunks)} chunks")
                
            except Exception as e:
                logger.error(f"Error processing document {document_id}: {e}")
                await db.execute(
                    update(Document)
                    .where(Document.id == document_id)
                    .values(
                        processing_status="failed",
                        error_message=str(e)
                    )
                )
                await db.commit()
                raise
    
    async def _process_file(self, file_path: str, file_type: str) -> List[ProcessedChunk]:
        """Process file based on type"""
        if file_type.lower() == "pdf":
            return await self._process_pdf(file_path)
        elif file_type.lower() == "docx":
            return await self._process_docx(file_path)
        elif file_type.lower() == "txt":
            return await self._process_txt(file_path)
        else:
            raise ValueError(f"Unsupported file type: {file_type}")
    
    async def _process_pdf(self, file_path: str) -> List[ProcessedChunk]:
        """Process PDF documents"""
        chunks = []
        
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            
            for page_num, page in enumerate(pdf_reader.pages):
                try:
                    text = page.extract_text()
                    if not text.strip():
                        continue
                    
                    # Clean and normalize text
                    cleaned_text = self._clean_text(text)
                    
                    # Extract sections from page
                    page_chunks = await self._extract_sections(cleaned_text, page_num + 1)
                    chunks.extend(page_chunks)
                    
                except Exception as e:
                    logger.warning(f"Error processing page {page_num + 1}: {e}")
                    continue
        
        return chunks
    
    async def _process_docx(self, file_path: str) -> List[ProcessedChunk]:
        """Process DOCX documents"""
        chunks = []
        doc = docx.Document(file_path)
        
        current_section = ""
        current_text = ""
        paragraph_count = 0
        
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            
            paragraph_count += 1
            
            # Detect section headers
            if self._is_section_header(text):
                if current_text:
                    chunk = ProcessedChunk(
                        text=current_text,
                        metadata={
                            'section_title': current_section,
                            'document_type': 'DOCX',
                            'paragraph_count': paragraph_count
                        },
                        section_type=self._classify_section_type(current_section)
                    )
                    chunks.append(chunk)
                
                current_section = text
                current_text = ""
            else:
                current_text += f"{text}\n"
        
        # Add final section
        if current_text:
            chunk = ProcessedChunk(
                text=current_text,
                metadata={
                    'section_title': current_section,
                    'document_type': 'DOCX',
                    'paragraph_count': paragraph_count
                },
                section_type=self._classify_section_type(current_section)
            )
            chunks.append(chunk)
        
        return chunks
    
    async def _process_txt(self, file_path: str) -> List[ProcessedChunk]:
        """Process plain text files"""
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Split into chunks of reasonable size
        text_chunks = self._split_text_into_chunks(content)
        
        chunks = []
        for i, chunk_text in enumerate(text_chunks):
            chunk = ProcessedChunk(
                text=chunk_text,
                metadata={
                    'chunk_index': i,
                    'document_type': 'TXT'
                },
                section_type='general'
            )
            chunks.append(chunk)
        
        return chunks
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove special characters that might interfere with processing
        text = re.sub(r'[^\w\s\.\,\;\:\!\?\(\)\-\%\$\₹]', '', text)
        
        # Remove very short lines (likely artifacts)
        lines = text.split('\n')
        filtered_lines = [line for line in lines if len(line.strip()) > 3]
        
        return '\n'.join(filtered_lines).strip()
    
    async def _extract_sections(self, text: str, page_number: int) -> List[ProcessedChunk]:
        """Extract structured sections from text"""
        chunks = []
        
        # Common section patterns in insurance documents
        section_patterns = [
            r'(?i)^(\d+\.?\s*[A-Z][^.]*):?\s*(.+?)(?=^\d+\.|\Z)',
            r'(?i)^([A-Z][^.]*?):\s*(.+?)(?=^[A-Z][^.]*?:|\Z)',
            r'(?i)(exclusion|benefit|coverage|condition|definition)[s]?[:\s]*(.+?)(?=^[A-Z]|\Z)'
        ]
        
        found_sections = False
        for pattern in section_patterns:
            matches = re.finditer(pattern, text, re.MULTILINE | re.DOTALL)
            for match in matches:
                title = match.group(1).strip()
                content = match.group(2).strip()
                
                if len(content) > 50:  # Only process substantial content
                    chunk = ProcessedChunk(
                        text=content,
                        metadata={
                            'section_title': title,
                            'page_number': page_number,
                            'extraction_method': 'pattern_matching'
                        },
                        section_type=self._classify_section_type(title),
                        page_number=page_number,
                        confidence_score=0.8
                    )
                    chunks.append(chunk)
                    found_sections = True
        
        # If no sections found, split text into chunks
        if not found_sections:
            text_chunks = self._split_text_into_chunks(text)
            for i, chunk_text in enumerate(text_chunks):
                chunk = ProcessedChunk(
                    text=chunk_text,
                    metadata={
                        'page_number': page_number,
                        'chunk_index': i,
                        'extraction_method': 'text_splitting'
                    },
                    section_type='general',
                    page_number=page_number,
                    confidence_score=0.5
                )
                chunks.append(chunk)
        
        return chunks
    
    def _split_text_into_chunks(self, text: str) -> List[str]:
        """Split text into manageable chunks"""
        words = text.split()
        chunks = []
        current_chunk = []
        current_length = 0
        
        for word in words:
            if current_length + len(word) + 1 > settings.CHUNK_SIZE:
                if current_chunk:
                    chunks.append(' '.join(current_chunk))
                    # Keep overlap
                    overlap_size = min(len(current_chunk), settings.CHUNK_OVERLAP // 10)
                    current_chunk = current_chunk[-overlap_size:] if overlap_size > 0 else []
                    current_length = sum(len(w) + 1 for w in current_chunk)
            
            current_chunk.append(word)
            current_length += len(word) + 1
        
        if current_chunk:
            chunks.append(' '.join(current_chunk))
        
        return chunks
    
    def _is_section_header(self, text: str) -> bool:
        """Determine if text is a section header"""
        patterns = [
            r'^\d+\.?\s*[A-Z]',  # Numbered sections
            r'^[A-Z][^.]*:$',    # Capitalized headers ending with colon
            r'^SECTION\s+[A-Z]', # Section headers
            r'^PART\s+[A-Z]',    # Part headers
            r'^ARTICLE\s+[A-Z]', # Article headers
        ]
        
        return any(re.match(pattern, text.strip()) for pattern in patterns)
    
    def _classify_section_type(self, title: str) -> str:
        """Classify section type based on title"""
        if not title:
            return 'general'
        
        title_lower = title.lower()
        
        # Insurance-specific classifications
        if any(word in title_lower for word in ['exclusion', 'exclude', 'not covered', 'exception']):
            return 'exclusion'
        elif any(word in title_lower for word in ['benefit', 'coverage', 'cover', 'eligible']):
            return 'benefit'
        elif any(word in title_lower for word in ['condition', 'term', 'requirement', 'clause']):
            return 'condition'
        elif any(word in title_lower for word in ['definition', 'meaning', 'interpret']):
            return 'definition'
        elif any(word in title_lower for word in ['waiting period', 'limit', 'deductible', 'co-payment']):
            return 'limitation'
        elif any(word in title_lower for word in ['claim', 'procedure', 'process']):
            return 'procedure'
        elif any(word in title_lower for word in ['premium', 'payment', 'fee']):
            return 'financial'
        else:
            return 'general'
    
    async def _save_chunks(self, db: AsyncSession, document_id: uuid.UUID, chunks: List[ProcessedChunk]):
        """Save processed chunks to database with embeddings"""
        for i, chunk in enumerate(chunks):
            try:
                # Generate embedding
                embedding = await self.embedding_service.get_embedding(chunk.text)
                
                # Create chunk record
                db_chunk = DocumentChunk(
                    document_id=document_id,
                    chunk_index=i,
                    chunk_text=chunk.text,
                    chunk_metadata=chunk.metadata,
                    section_type=chunk.section_type,
                    page_number=chunk.page_number,
                    confidence_score=chunk.confidence_score,
                    embedding_vector=str(embedding)  # Store as JSON string
                )
                
                db.add(db_chunk)
                
            except Exception as e:
                logger.error(f"Error processing chunk {i}: {e}")
                continue
        
        await db.commit()
    
    def _extract_full_text(self, chunks: List[ProcessedChunk]) -> str:
        """Extract full text from chunks for storage"""
        return '\n\n'.join([chunk.text for chunk in chunks])
