"""
Semantic search service for finding relevant document chunks
"""
import json
import logging
import numpy as np
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from src.core.database import AsyncSessionLocal
from src.core.models import DocumentChunk, Document
from src.services.embedding_service import EmbeddingService
from src.core.config import settings

logger = logging.getLogger(__name__)

class SemanticSearchService:
    def __init__(self):
        self.embedding_service = EmbeddingService()
    
    async def search_documents(
        self, 
        query: str, 
        entities: Dict[str, Any],
        top_k: int = 10,
        similarity_threshold: float = None
    ) -> List[Dict[str, Any]]:
        """Search for relevant document chunks using semantic similarity"""
        
        if similarity_threshold is None:
            similarity_threshold = settings.SIMILARITY_THRESHOLD
        
        try:
            # Generate query embedding
            query_embedding = await self.embedding_service.get_embedding(query)
            
            # Perform vector search
            search_results = await self._vector_search(query_embedding, top_k * 2)  # Get more for filtering
            
            # Enhance with hybrid search
            enhanced_results = await self._enhance_with_keyword_search(query, entities, search_results)
            
            # Rank and filter results
            ranked_results = self._rank_and_filter_results(
                enhanced_results, 
                entities, 
                similarity_threshold,
                top_k
            )
            
            return ranked_results
            
        except Exception as e:
            logger.error(f"Error in semantic search: {e}")
            return []
    
    async def _vector_search(self, query_embedding: List[float], top_k: int) -> List[Dict[str, Any]]:
        """Perform vector similarity search"""
        async with AsyncSessionLocal() as db:
            try:
                if settings.VECTOR_DB_TYPE == "postgres":
                    return await self._postgres_vector_search(db, query_embedding, top_k)
                else:
                    # Fallback to basic search if vector DB not configured
                    return await self._basic_text_search(db, top_k)
                    
            except Exception as e:
                logger.error(f"Vector search error: {e}")
                return []
    
    async def _postgres_vector_search(
        self, 
        db: AsyncSession, 
        query_embedding: List[float], 
        top_k: int
    ) -> List[Dict[str, Any]]:
        """PostgreSQL vector search using pgvector"""
        try:
            # Convert embedding to string format for PostgreSQL
            embedding_str = f"[{','.join(map(str, query_embedding))}]"
            
            # Vector similarity search query
            query_sql = text("""
                SELECT 
                    dc.id,
                    dc.chunk_text,
                    dc.section_type,
                    dc.chunk_metadata,
                    dc.page_number,
                    dc.confidence_score,
                    d.filename,
                    d.document_type,
                    1 - (dc.embedding_vector::vector <=> :query_embedding::vector) as similarity_score
                FROM document_chunks dc
                JOIN documents d ON dc.document_id = d.id
                WHERE dc.embedding_vector IS NOT NULL
                ORDER BY dc.embedding_vector::vector <=> :query_embedding::vector
                LIMIT :limit
            """)
            
            result = await db.execute(
                query_sql, 
                {
                    "query_embedding": embedding_str,
                    "limit": top_k
                }
            )
            
            results = []
            for row in result:
                results.append({
                    'chunk_id': str(row.id),
                    'text': row.chunk_text,
                    'section_type': row.section_type,
                    'metadata': row.chunk_metadata or {},
                    'page_number': row.page_number,
                    'confidence_score': row.confidence_score,
                    'filename': row.filename,
                    'document_type': row.document_type,
                    'similarity_score': float(row.similarity_score)
                })
            
            return results
            
        except Exception as e:
            logger.error(f"PostgreSQL vector search error: {e}")
            # Fallback to basic search
            return await self._basic_text_search(db, top_k)
    
    async def _basic_text_search(self, db: AsyncSession, top_k: int) -> List[Dict[str, Any]]:
        """Basic text search fallback"""
        try:
            # Simple query to get recent chunks
            query = select(DocumentChunk, Document).join(Document).limit(top_k)
            result = await db.execute(query)
            
            results = []
            for chunk, document in result:
                results.append({
                    'chunk_id': str(chunk.id),
                    'text': chunk.chunk_text,
                    'section_type': chunk.section_type,
                    'metadata': chunk.chunk_metadata or {},
                    'page_number': chunk.page_number,
                    'confidence_score': chunk.confidence_score,
                    'filename': document.filename,
                    'document_type': document.document_type,
                    'similarity_score': 0.5  # Default score
                })
            
            return results
            
        except Exception as e:
            logger.error(f"Basic text search error: {e}")
            return []
    
    async def _enhance_with_keyword_search(
        self, 
        query: str, 
        entities: Dict[str, Any], 
        vector_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Enhance vector search results with keyword matching"""
        
        enhanced_results = []
        
        for result in vector_results:
            # Calculate keyword boost
            keyword_boost = self._calculate_keyword_boost(query, entities, result['text'])
            
            # Calculate section type boost
            section_boost = self._calculate_section_boost(entities, result['section_type'])
            
            # Calculate entity match boost
            entity_boost = self._calculate_entity_boost(entities, result['text'])
            
            # Update similarity score
            original_score = result.get('similarity_score', 0.0)
            boosted_score = min(original_score + keyword_boost + section_boost + entity_boost, 1.0)
            
            result['similarity_score'] = boosted_score
            result['boost_factors'] = {
                'keyword_boost': keyword_boost,
                'section_boost': section_boost,
                'entity_boost': entity_boost
            }
            
            enhanced_results.append(result)
        
        return enhanced_results
    
    def _calculate_keyword_boost(self, query: str, entities: Dict[str, Any], text: str) -> float:
        """Calculate keyword matching boost"""
        boost = 0.0
        
        query_words = query.lower().split()
        text_lower = text.lower()
        
        # Boost for exact phrase matches
        for word in query_words:
            if word in text_lower:
                boost += 0.02
        
        # Boost for multi-word phrases
        if len(query_words) > 1:
            bigrams = [f"{query_words[i]} {query_words[i+1]}" for i in range(len(query_words)-1)]
            for bigram in bigrams:
                if bigram in text_lower:
                    boost += 0.05
        
        return min(boost, 0.2)  # Cap boost at 0.2
    
    def _calculate_section_boost(self, entities: Dict[str, Any], section_type: str) -> float:
        """Calculate section type relevance boost"""
        
        # Map entity types to relevant sections
        entity_section_mapping = {
            'procedure': ['benefit', 'coverage', 'condition'],
            'amount': ['benefit', 'financial', 'limitation'],
            'policy_duration': ['limitation', 'condition'],
        }
        
        boost = 0.0
        
        for entity_type in entities.keys():
            if entity_type in entity_section_mapping:
                if section_type in entity_section_mapping[entity_type]:
                    boost += 0.1
        
        # Specific boosts for common query types
        if section_type == 'exclusion':
            boost += 0.05  # Exclusions are often relevant
        elif section_type == 'benefit':
            boost += 0.1   # Benefits are highly relevant
        
        return min(boost, 0.3)
    
    def _calculate_entity_boost(self, entities: Dict[str, Any], text: str) -> float:
        """Calculate boost based on entity matches in text"""
        boost = 0.0
        text_lower = text.lower()
        
        # Boost for entity value matches
        for entity_type, entity_value in entities.items():
            if entity_type == 'procedure' and entity_value:
                if entity_value.lower() in text_lower:
                    boost += 0.15
            elif entity_type == 'location' and entity_value:
                if entity_value.lower() in text_lower:
                    boost += 0.05
            elif entity_type == 'age' and entity_value:
                if str(entity_value) in text_lower:
                    boost += 0.1
        
        return min(boost, 0.25)
    
    def _rank_and_filter_results(
        self, 
        results: List[Dict[str, Any]], 
        entities: Dict[str, Any],
        similarity_threshold: float,
        top_k: int
    ) -> List[Dict[str, Any]]:
        """Rank and filter results based on relevance"""
        
        # Filter by similarity threshold
        filtered_results = [
            result for result in results 
            if result.get('similarity_score', 0.0) >= similarity_threshold
        ]
        
        # Sort by similarity score
        sorted_results = sorted(
            filtered_results, 
            key=lambda x: x.get('similarity_score', 0.0), 
            reverse=True
        )
        
        # Add relevance explanations
        for result in sorted_results:
            result['relevance_factors'] = self._explain_relevance(result, entities)
        
        # Return top k results
        return sorted_results[:top_k]
    
    def _explain_relevance(self, result: Dict[str, Any], entities: Dict[str, Any]) -> List[str]:
        """Explain why this result is relevant"""
        factors = []
        
        score = result.get('similarity_score', 0.0)
        if score > 0.8:
            factors.append("High semantic similarity")
        elif score > 0.6:
            factors.append("Good semantic similarity")
        
        # Check for entity matches
        text_lower = result['text'].lower()
        for entity_type, entity_value in entities.items():
            if entity_value and str(entity_value).lower() in text_lower:
                factors.append(f"Contains {entity_type}: {entity_value}")
        
        # Check section type relevance
        section_type = result.get('section_type', '')
        if section_type in ['benefit', 'coverage']:
            factors.append("Relevant policy section")
        elif section_type == 'exclusion':
            factors.append("Important exclusion clause")
        
        # Check boost factors
        boost_factors = result.get('boost_factors', {})
        if boost_factors.get('keyword_boost', 0) > 0.05:
            factors.append("Strong keyword match")
        
        return factors
