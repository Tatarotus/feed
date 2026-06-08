import asyncio
import logging

from sqlalchemy import and_, select

from app.config import settings
from app.database import SessionLocal
from app.models import Video, VideoChunk
from app.pipeline.ingestion.transcripts import fetch_transcript
from app.pipeline.processing.chunker import chunk_text
from app.pipeline.processing.cleaning import clean_and_normalize_text

logger = logging.getLogger("jobs.process_chunks")

async def process_video_transcript(video_id: str) -> bool:
    """
    Crawls the transcript for a video, cleanses and normalizes the text,
    splits it into overlapping sliding-window chunks, and inserts chunk records using short-lived transactions.
    """
    # 1. Fetch video details in a quick session
    db = SessionLocal()
    try:
        video = db.scalar(select(Video).where(Video.id == video_id))
        if not video:
            logger.error(f"Video {video_id} not found in DB.")
            return False
        video_title = video.title
        video_description = video.description
    finally:
        db.close()

    logger.info(f"Processing transcript for video: {video_title} ({video_id})")

    try:
        # 2. Crawl transcript over network WITHOUT any open DB transaction
        transcript_text, lang_code, source = await fetch_transcript(video_id)

        # Concat title + description + transcript for rich deep-search normalized text
        rich_raw_text = f"Title: {video_title}. Description: {video_description or ''}."
        if transcript_text:
            rich_raw_text += f" Transcript: {transcript_text}"

        # Standardize and sanitize text (stripping HTML, normalizing spaces)
        normalized_text = clean_and_normalize_text(rich_raw_text)

        # Generate token chunks
        chunks = chunk_text(normalized_text, chunk_size=500, overlap=50)

        # 3. Write updates and chunks in a quick DB session
        db = SessionLocal()
        try:
            video = db.scalar(select(Video).where(Video.id == video_id))
            if not video:
                logger.error(f"Video {video_id} disappeared during transcript fetch.")
                return False

            video.normalized_text = normalized_text

            if chunks:
                # Delete any prior chunks if we are reprocessing
                db.query(VideoChunk).filter(VideoChunk.video_id == video_id).delete()

                # Bulk create chunks to prevent database roundtrips
                db_chunks = []
                for idx, text in enumerate(chunks):
                    chunk = VideoChunk(
                        video_id=video_id,
                        chunk_index=idx,
                        text=text,
                        normalized_text=clean_and_normalize_text(text),
                        language_code=lang_code,
                        transcript_source=source,
                    )
                    db_chunks.append(chunk)
                db.add_all(db_chunks)
                logger.info(f"Generated {len(chunks)} chunks for video {video_id} (Source: {source})")
            else:
                logger.warning(f"No text chunks generated for video {video_id}")

            # Transition state
            video.processing_status = "chunked"
            video.processing_error = None
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    except Exception as e:
        logger.warning(f"Failed to process video {video_id} transcript: {str(e)}")
        # 4. Handle error state in a quick DB session
        db = SessionLocal()
        try:
            video = db.scalar(select(Video).where(Video.id == video_id))
            if video:
                video.retry_count += 1
                video.processing_error = str(e)

                if video.retry_count >= settings.MAX_PROCESSING_RETRIES:
                    video.processing_status = "failed"
                    logger.error(f"Video {video_id} processing failed permanently after {video.retry_count} retries: {str(e)}")
                else:
                    video.processing_status = "pending"
                db.commit()
        except Exception as ex:
            db.rollback()
            logger.error(f"Failed to update retry status for video {video_id}: {str(ex)}")
        finally:
            db.close()
        return False

async def run_chunk_processing():
    """Sweeps pending videos to process transcripts and chunk text using short-lived transactions."""
    db = SessionLocal()
    try:
        # Fetch pending video IDs in a short-lived query
        stmt = (
            select(Video.id)
            .where(
                and_(
                    Video.processing_status == "pending",
                    Video.retry_count < settings.MAX_PROCESSING_RETRIES
                )
            )
            .limit(10)  # Rate control batch sweeps
        )
        pending_video_ids = db.scalars(stmt).all()
    except Exception as e:
        logger.error(f"Error loading pending videos for chunking: {str(e)}")
        return
    finally:
        db.close()

    if not pending_video_ids:
        logger.debug("No pending videos for transcript chunking.")
        return

    logger.info(f"Starting chunk processing sweep for {len(pending_video_ids)} videos...")
    for video_id in pending_video_ids:
        await process_video_transcript(video_id)
        # Sleep briefly to be respectful to Google rate throttling
        await asyncio.sleep(2.0)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    logger.info("Starting manual chunking sweep...")
    asyncio.run(run_chunk_processing())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    logger.info("Starting manual chunking sweep...")
    asyncio.run(run_chunk_processing())
