"""
Service to handle text embedding generation using OpenAI
"""
import openai
import logging
from src.core.config import settings

logger = logging.getLogger(__name__)

class EmbeddingService:
    def __init__(self):
        openai.api_key = settings.OPENAI_API_KEY

    async def get_embedding(self, text: str) -> list:
        try:
            response = openai.Embedding.create(
                model=settings.EMBEDDING_MODEL,
                input=text
            )
            return response["data"][0]["embedding"]
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            # Return a zero vector or handle according to your fallback
            return [0.0] * 1536  # Adjust length for your embedding model
