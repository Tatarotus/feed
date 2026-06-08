import hashlib
import logging
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import EmbeddingCache
from app.services.embedding_provider import NvidiaEmbeddingProvider, OpenAIEmbeddingProvider

logger = logging.getLogger("pipeline.enrichment.embedder")

class EmbedderService:
    _instance = None
    _provider = None

    # High-speed in-memory query embedding cache (avoids DB hits for repeating search queries)
    _query_cache: Dict[str, List[float]] = {}

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(EmbedderService, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    @property
    def provider(self):
        """Lazy load the API embedding provider based on config."""
        if self._provider is None:
            prov_name = settings.EMBEDDING_PROVIDER.lower()
            logger.info(f"Initializing API embedding provider: '{prov_name}' (Model: {settings.EMBEDDING_MODEL})")

            if prov_name == "openai":
                self._provider = OpenAIEmbeddingProvider()
            else:
                self._provider = NvidiaEmbeddingProvider()
        return self._provider

    def compute_hash(self, text: str) -> str:
        """Helper to generate a clean SHA-256 text hash."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    async def generate_embedding(self, text: str, db: Optional[Session] = None, input_type: str = "passage") -> List[float]:
        """
        Generate a single vector embedding for a text string.
        Checks in-memory query cache, then SQL cache, falling back to external API.
        Uses short-lived database sessions internally to avoid holding connections open during network calls.
        """
        if not text.strip():
            return [0.0] * settings.EMBEDDING_DIM

        text_clean = text.strip()

        # 1. High-Speed In-Memory Cache Lookup
        if text_clean in self._query_cache:
            logger.debug(f"In-memory query cache HIT for: '{text_clean}'")
            return self._query_cache[text_clean]

        text_hash = self.compute_hash(text_clean)

        # 2. SQL Database Cache Lookup (using short-lived session)
        if settings.EMBEDDING_CACHE_ENABLED:
            cache_db = SessionLocal()
            try:
                cached = cache_db.scalar(select(EmbeddingCache).where(EmbeddingCache.text_hash == text_hash))
                if cached:
                    logger.debug(f"SQL cache HIT for text hash {text_hash[:8]}")
                    # Save to in-memory cache for subsequent calls
                    self._query_cache[text_clean] = cached.embedding
                    return cached.embedding
            except Exception as cache_err:
                logger.warning(f"SQL cache read failed (non-blocking): {str(cache_err)}")
            finally:
                cache_db.close()

        # 3. Cache Miss: Request from API provider (WITHOUT active database connection)
        try:
            logger.debug(f"Cache MISS for '{text_clean[:20]}'. Querying external API...")
            vectors = await self.provider.embed([text_clean], input_type=input_type)
            vector = vectors[0]

            # Save to in-memory cache
            self._query_cache[text_clean] = vector

            # Save to SQL Cache (using separate short-lived session)
            if settings.EMBEDDING_CACHE_ENABLED:
                cache_db = SessionLocal()
                try:
                    new_cache = EmbeddingCache(
                        text_hash=text_hash,
                        provider=settings.EMBEDDING_PROVIDER,
                        model=settings.EMBEDDING_MODEL,
                        embedding=vector
                    )
                    cache_db.add(new_cache)
                    cache_db.commit()
                except Exception as cache_err:
                    cache_db.rollback()
                    logger.warning(f"Failed to save embedding to SQL cache (non-blocking): {str(cache_err)}")
                finally:
                    cache_db.close()

            return vector

        except Exception as e:
            logger.error(f"Failed to generate API embedding: {str(e)}")
            raise e

    def _check_sql_cache(
        self,
        texts: List[str],
        results: List[Optional[List[float]]],
        hashes: List[str],
        remainders_indices: List[int],
        miss_indices: List[int],
        miss_texts: List[str],
        miss_hashes: List[str]
    ):
        if remainders_indices and settings.EMBEDDING_CACHE_ENABLED:
            cache_db = SessionLocal()
            try:
                remainder_hashes = [hashes[i] for i in remainders_indices]
                stmt = select(EmbeddingCache).where(EmbeddingCache.text_hash.in_(remainder_hashes))
                cached_records = cache_db.scalars(stmt).all()

                cache_map = {rec.text_hash: rec.embedding for rec in cached_records}

                for idx in remainders_indices:
                    text_hash = hashes[idx]
                    text_clean = texts[idx].strip()
                    if text_hash in cache_map:
                        vector = cache_map[text_hash]
                        results[idx] = vector
                        self._query_cache[text_clean] = vector
                    else:
                        miss_indices.append(idx)
                        miss_texts.append(texts[idx])
                        miss_hashes.append(text_hash)

                logger.info(f"Batch cache lookup complete. hits: {len(cached_records)}, misses: {len(miss_indices)}")
            except Exception as cache_err:
                logger.warning(f"SQL batch cache read failed (non-blocking): {str(cache_err)}")
                for idx in remainders_indices:
                    miss_indices.append(idx)
                    miss_texts.append(texts[idx])
                    miss_hashes.append(hashes[idx])
            finally:
                cache_db.close()
        else:
            for idx in remainders_indices:
                miss_indices.append(idx)
                miss_texts.append(texts[idx])
                miss_hashes.append(hashes[idx])

    async def _fetch_and_cache_misses(
        self,
        results: List[Optional[List[float]]],
        input_type: str,
        miss_indices: List[int],
        miss_texts: List[str],
        miss_hashes: List[str]
    ):
        if not miss_texts:
            return

        try:
            api_vectors = await self.provider.embed(miss_texts, input_type=input_type)
            new_cache_rows = []
            for idx, vector in enumerate(api_vectors):
                orig_idx = miss_indices[idx]
                results[orig_idx] = vector
                text_clean = miss_texts[idx].strip()

                self._query_cache[text_clean] = vector

                if settings.EMBEDDING_CACHE_ENABLED:
                    new_cache_rows.append(
                        EmbeddingCache(
                            text_hash=miss_hashes[idx],
                            provider=settings.EMBEDDING_PROVIDER,
                            model=settings.EMBEDDING_MODEL,
                            embedding=vector
                        )
                    )

            if settings.EMBEDDING_CACHE_ENABLED and new_cache_rows:
                cache_db = SessionLocal()
                try:
                    cache_db.add_all(new_cache_rows)
                    cache_db.commit()
                    logger.info(f"Bulk saved {len(new_cache_rows)} new vectors to SQL cache.")
                except Exception as cache_err:
                    cache_db.rollback()
                    logger.warning(f"Bulk cache save failed (non-blocking): {str(cache_err)}")
                finally:
                    cache_db.close()
        except Exception as e:
            logger.error(f"Batch API embedding request failed: {str(e)}")
            raise e

    async def generate_embeddings_batch(self, texts: List[str], db: Optional[Session] = None, input_type: str = "passage") -> List[List[float]]:
        """
        Generate vectors in an optimized batch API sweep.
        Uses short-lived database sessions internally for caching reads and writes.
        """
        if not texts:
            return []

        results: List[Optional[List[float]]] = [None] * len(texts)
        hashes = [self.compute_hash(t.strip()) for t in texts]

        miss_indices: List[int] = []
        miss_texts: List[str] = []
        miss_hashes: List[str] = []

        # Check in-memory query cache first
        for idx, text in enumerate(texts):
            text_clean = text.strip()
            if text_clean in self._query_cache:
                results[idx] = self._query_cache[text_clean]

        remainders_indices = [i for i, v in enumerate(results) if v is None]
        self._check_sql_cache(texts, results, hashes, remainders_indices, miss_indices, miss_texts, miss_hashes)
        await self._fetch_and_cache_misses(results, input_type, miss_indices, miss_texts, miss_hashes)

        # Final check & fallback mapping
        final_vectors: List[List[float]] = []
        for vec in results:
            if vec is None:
                final_vectors.append([0.0] * settings.EMBEDDING_DIM)
            else:
                final_vectors.append(vec)

        return final_vectors

# Expose global service instance
embedder = EmbedderService()

