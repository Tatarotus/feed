import logging
import asyncio
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from app.database import SessionLocal
from app.models import Video, VideoChunk
from app.pipeline.enrichment.embedder import embedder
from app.pipeline.enrichment.classifier import analyze_clickbait
from app.config import settings

logger = logging.getLogger("jobs.process_vectors")

async def vectorize_video(db: Session, video: Video) -> bool:
    """
    Batch generates embeddings for all of a video's chunks and the parent video itself
    using the asynchronous external API provider, utilizing SQL caching.
    """
    logger.info(f"Generating API vectors and classifying video: {video.title} ({video.id})")
    
    try:
        # 1. Fetch chunks needing vectorization
        stmt = select(VideoChunk).where(VideoChunk.video_id == video.id).order_by(VideoChunk.chunk_index)
        chunks = db.scalars(stmt).all()
        
        if chunks:
            chunk_texts = [c.normalized_text for c in chunks]
            # Await the async batch API generator with DB session enabled
            embeddings = await embedder.generate_embeddings_batch(chunk_texts, db=db)
            
            for idx, chunk in enumerate(chunks):
                chunk.embedding = embeddings[idx]
                chunk.embedding_model = settings.EMBEDDING_MODEL
                chunk.embedding_version = settings.EMBEDDING_VERSION
            
            logger.info(f"Vectorized {len(chunks)} transcript chunks for video {video.id} via API.")

        # 2. Vectorize parent video title + description
        parent_text = f"{video.title} {video.description or ''}"
        video.embedding = await embedder.generate_embedding(parent_text, db=db)
        video.embedding_model = settings.EMBEDDING_MODEL
        video.embedding_version = settings.EMBEDDING_VERSION

        # 3. Perform clickbait analysis
        click_score, click_reasons = analyze_clickbait(video.title)
        video.clickbait_score = click_score
        video.clickbait_reasons = click_reasons
        
        if click_score > 0.0:
            logger.info(f"Clickbait detected on {video.id}: Score {click_score} (Reasons: {click_reasons})")

        # 4. Transition completed lifecycle state
        video.processing_status = "embedded"
        video.processing_error = None
        db.commit()
        return True

    except Exception as e:
        db.rollback()
        video.retry_count += 1
        video.processing_error = f"API Vectorization error: {str(e)}"
        
        if video.retry_count >= settings.MAX_PROCESSING_RETRIES:
            video.processing_status = "failed"
            logger.error(f"Video {video.id} vectorization failed permanently: {str(e)}")
        else:
            video.processing_status = "chunked"  # Keep in chunked to retry next sweep
            logger.warning(f"Vectorization failed (attempt {video.retry_count}): {str(e)}")
            
        db.commit()
        return False

async def run_vector_processing():
    """Sweeps chunked videos to vectorize text and calculate clickbait scores."""
    db = SessionLocal()
    try:
        stmt = (
            select(Video)
            .where(
                and_(
                    Video.processing_status == "chunked",
                    Video.retry_count < settings.MAX_PROCESSING_RETRIES
                )
            )
            .limit(10)  # Rate control batch sweeps
        )
        chunked_videos = db.scalars(stmt).all()
        
        if not chunked_videos:
            logger.debug("No chunked videos for vectorization.")
            return

        logger.info(f"Starting vector processing sweep for {len(chunked_videos)} videos...")
        for video in chunked_videos:
            await vectorize_video(db, video)
            # Yield to execution loop briefly to be network friendly
            await asyncio.sleep(0.5)
            
    finally:
        db.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    logger.info("Starting manual vectorization sweep...")
    asyncio.run(run_vector_processing())
