import asyncio
import logging

from sqlalchemy import and_, select

from app.config import settings
from app.database import SessionLocal
from app.models import Video, VideoChunk
from app.pipeline.enrichment.classifier import analyze_clickbait
from app.pipeline.enrichment.embedder import embedder

logger = logging.getLogger("jobs.process_vectors")

async def vectorize_video(video_id: str) -> bool:
    """
    Batch generates embeddings for all of a video's chunks and the parent video itself
    using the asynchronous external API provider with short-lived database sessions.
    """
    # 1. Fetch video and chunk texts in a quick session
    db = SessionLocal()
    try:
        video = db.scalar(select(Video).where(Video.id == video_id))
        if not video:
            logger.error(f"Video {video_id} not found in DB.")
            return False
        video_title = video.title
        video_description = video.description

        stmt = select(VideoChunk).where(VideoChunk.video_id == video_id).order_by(VideoChunk.chunk_index)
        chunks = db.scalars(stmt).all()
        chunk_infos = [(c.id, c.normalized_text) for c in chunks]
    finally:
        db.close()

    logger.info(f"Generating API vectors and classifying video: {video_title} ({video_id})")

    try:
        # 2. Vectorize chunks over network WITHOUT open DB transaction
        embeddings = []
        if chunk_infos:
            chunk_texts = [info[1] for info in chunk_infos]
            embeddings = await embedder.generate_embeddings_batch(chunk_texts)
            logger.info(f"Vectorized {len(chunk_infos)} transcript chunks for video {video_id} via API.")

        # 3. Vectorize parent video title + description over network
        parent_text = f"{video_title} {video_description or ''}"
        parent_embedding = await embedder.generate_embedding(parent_text)

        # 4. Perform clickbait analysis
        click_score, click_reasons = analyze_clickbait(video_title)

        # 5. Persist all vectors and clickbait scores in a short-lived DB session
        db = SessionLocal()
        try:
            video = db.scalar(select(Video).where(Video.id == video_id))
            if not video:
                logger.error(f"Video {video_id} disappeared during vectorization.")
                return False

            stmt = select(VideoChunk).where(VideoChunk.video_id == video_id).order_by(VideoChunk.chunk_index)
            db_chunks = db.scalars(stmt).all()

            if embeddings and len(embeddings) == len(db_chunks):
                for idx, chunk in enumerate(db_chunks):
                    chunk.embedding = embeddings[idx]
                    chunk.embedding_model = settings.EMBEDDING_MODEL
                    chunk.embedding_version = settings.EMBEDDING_VERSION

            video.embedding = parent_embedding
            video.embedding_model = settings.EMBEDDING_MODEL
            video.embedding_version = settings.EMBEDDING_VERSION

            video.clickbait_score = click_score
            video.clickbait_reasons = click_reasons

            if click_score > 0.0:
                logger.info(f"Clickbait detected on {video_id}: Score {click_score} (Reasons: {click_reasons})")

            # Transition completed lifecycle state
            video.processing_status = "embedded"
            video.processing_error = None
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    except Exception as e:
        logger.warning(f"Failed to vectorize video {video_id}: {str(e)}")
        # 6. Update error status in a quick session
        db = SessionLocal()
        try:
            video = db.scalar(select(Video).where(Video.id == video_id))
            if video:
                video.retry_count += 1
                video.processing_error = f"API Vectorization error: {str(e)}"

                if video.retry_count >= settings.MAX_PROCESSING_RETRIES:
                    video.processing_status = "failed"
                    logger.error(f"Video {video_id} vectorization failed permanently: {str(e)}")
                else:
                    video.processing_status = "chunked"  # Keep in chunked to retry next sweep
                db.commit()
        except Exception as ex:
            db.rollback()
            logger.error(f"Failed to update retry status for video {video_id}: {str(ex)}")
        finally:
            db.close()
        return False

async def run_vector_processing():
    """Sweeps chunked videos to vectorize text and calculate clickbait scores using short-lived transactions."""
    db = SessionLocal()
    try:
        stmt = (
            select(Video.id)
            .where(
                and_(
                    Video.processing_status == "chunked",
                    Video.retry_count < settings.MAX_PROCESSING_RETRIES
                )
            )
            .limit(10)  # Rate control batch sweeps
        )
        chunked_video_ids = db.scalars(stmt).all()
    except Exception as e:
        logger.error(f"Error loading chunked videos for vectorization: {str(e)}")
        return
    finally:
        db.close()

    if not chunked_video_ids:
        logger.debug("No chunked videos for vectorization.")
        return

    logger.info(f"Starting vector processing sweep for {len(chunked_video_ids)} videos...")
    for video_id in chunked_video_ids:
        await vectorize_video(video_id)
        # Yield to execution loop briefly to be network friendly
        await asyncio.sleep(0.5)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    logger.info("Starting manual vectorization sweep...")
    asyncio.run(run_vector_processing())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    logger.info("Starting manual vectorization sweep...")
    asyncio.run(run_vector_processing())
