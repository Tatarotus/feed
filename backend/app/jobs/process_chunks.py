import logging
import asyncio
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from app.database import SessionLocal
from app.models import Video, VideoChunk
from app.pipeline.ingestion.transcripts import fetch_transcript
from app.pipeline.processing.cleaning import clean_and_normalize_text
from app.pipeline.processing.chunker import chunk_text
from app.config import settings

logger = logging.getLogger("jobs.process_chunks")

async def process_video_transcript(db: Session, video: Video) -> bool:
    """
    Crawls the transcript for a video, cleanses and normalizes the text,
    splits it into overlapping sliding-window chunks, and inserts chunk records.
    """
    logger.info(f"Processing transcript for video: {video.title} ({video.id})")
    
    try:
        # Crawl transcript via youtube-transcript-api and fallback Captions
        transcript_text, lang_code, source = await fetch_transcript(video.id)
        
        # Concat title + description + transcript for rich deep-search normalized text
        rich_raw_text = f"Title: {video.title}. Description: {video.description or ''}."
        if transcript_text:
            rich_raw_text += f" Transcript: {transcript_text}"
            
        # Standardize and sanitize text (stripping HTML, normalizing spaces)
        normalized_text = clean_and_normalize_text(rich_raw_text)
        
        # Save standard cleaned text on video record
        video.normalized_text = normalized_text
        
        # Generate token chunks
        chunks = chunk_text(normalized_text, chunk_size=500, overlap=50)
        
        if chunks:
            # Delete any prior chunks if we are reprocessing
            db.query(VideoChunk).filter(VideoChunk.video_id == video.id).delete()
            
            # Bulk create chunks to prevent database roundtrips
            db_chunks = []
            for idx, text in enumerate(chunks):
                chunk = VideoChunk(
                    video_id=video.id,
                    chunk_index=idx,
                    text=text,
                    normalized_text=clean_and_normalize_text(text),
                    language_code=lang_code,
                    transcript_source=source,
                )
                db_chunks.append(chunk)
            db.add_all(db_chunks)
            logger.info(f"Generated {len(chunks)} chunks for video {video.id} (Source: {source})")
        else:
            logger.warning(f"No text chunks generated for video {video.id}")

        # Transition state
        video.processing_status = "chunked"
        video.processing_error = None
        db.commit()
        return True

    except Exception as e:
        db.rollback()
        video.retry_count += 1
        video.processing_error = str(e)
        
        if video.retry_count >= settings.MAX_PROCESSING_RETRIES:
            video.processing_status = "failed"
            logger.error(f"Video {video.id} processing failed permanently after {video.retry_count} retries: {str(e)}")
        else:
            # Retain in pending for retry next sweep
            video.processing_status = "pending"
            logger.warning(f"Failed to process video {video.id} (attempt {video.retry_count}): {str(e)}")
            
        db.commit()
        return False

async def run_chunk_processing():
    """Sweeps pending videos to process transcripts and chunk text."""
    db = SessionLocal()
    try:
        # Fetch pending videos requiring transcription/chunking
        stmt = (
            select(Video)
            .where(
                and_(
                    Video.processing_status == "pending",
                    Video.retry_count < settings.MAX_PROCESSING_RETRIES
                )
            )
            .limit(10)  # Rate control batch sweeps
        )
        pending_videos = db.scalars(stmt).all()
        
        if not pending_videos:
            logger.debug("No pending videos for transcript chunking.")
            return

        logger.info(f"Starting chunk processing sweep for {len(pending_videos)} videos...")
        for video in pending_videos:
            await process_video_transcript(db, video)
            # Sleep briefly to be respectful to Google rate throttling
            await asyncio.sleep(2.0)
            
    finally:
        db.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    logger.info("Starting manual chunking sweep...")
    asyncio.run(run_chunk_processing())
