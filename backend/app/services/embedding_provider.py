import logging
from typing import Protocol, List, Optional
import httpx
from fastapi import HTTPException
from app.config import settings

logger = logging.getLogger("services.embedding_provider")

class EmbeddingProvider(Protocol):
    async def embed(self, texts: List[str], input_type: str = "passage") -> List[List[float]]:
        ...


class NvidiaEmbeddingProvider(EmbeddingProvider):
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        # Prioritize customized NVIDIA_API_EMBEDDING key, fallback to general NVIDIA_API_KEY
        self.api_key = api_key or settings.NVIDIA_API_EMBEDDING or settings.NVIDIA_API_KEY
        self.model = model or settings.EMBEDDING_MODEL
        self.endpoint = "https://integrate.api.nvidia.com/v1/embeddings"

    async def embed(self, texts: List[str], input_type: str = "passage") -> List[List[float]]:
        if not self.api_key:
            logger.error("NVIDIA_API_EMBEDDING is not configured. Please set it in your environment or .env file.")
            raise ValueError("NVIDIA_API_EMBEDDING key is missing. Ingestion requires an API key for Nemotron embeddings.")

        if not texts:
            return []

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        payload = {
            "input": texts,
            "model": self.model,
            "encoding_format": "float",
            "input_type": input_type
        }

        try:
            logger.info(f"Requesting NVIDIA embeddings for batch size {len(texts)} using model {self.model} with input_type '{input_type}'...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(self.endpoint, json=payload, headers=headers)
                
                if response.status_code != 200:
                    error_text = response.text
                    logger.error(f"NVIDIA API Error ({response.status_code}): {error_text}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"NVIDIA Embedding API error: {error_text}"
                    )
                
                result = response.json()
                data = result.get("data", [])
                
                # Sort by index to preserve order
                data.sort(key=lambda x: x.get("index", 0))
                
                embeddings = [item["embedding"] for item in data]
                
                if len(embeddings) != len(texts):
                    raise ValueError(f"Mismatch: Sent {len(texts)} items, but received {len(embeddings)} vectors.")
                
                return embeddings

        except Exception as e:
            logger.error(f"NVIDIA Embedding API call failed: {str(e)}")
            raise e


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = model or settings.EMBEDDING_MODEL
        self.endpoint = "https://api.openai.com/v1/embeddings"

    async def embed(self, texts: List[str], input_type: str = "passage") -> List[List[float]]:
        if not self.api_key:
            logger.error("OPENAI_API_KEY is not configured.")
            raise ValueError("OPENAI_API_KEY is missing. Please set it in your environment or .env file.")

        if not texts:
            return []

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "input": texts,
            "model": self.model
        }

        try:
            logger.info(f"Requesting OpenAI embeddings for batch of {len(texts)} using model {self.model}...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(self.endpoint, json=payload, headers=headers)
                response.raise_for_status()
                
                result = response.json()
                data = result.get("data", [])
                data.sort(key=lambda x: x.get("index", 0))
                
                return [item["embedding"] for item in data]

        except Exception as e:
            logger.error(f"OpenAI Embedding API call failed: {str(e)}")
            raise e
