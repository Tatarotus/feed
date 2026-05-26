import logging
import asyncio
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Channel, Video
from app.pipeline.ingestion.rss import RSSProvider
from app.pipeline.ingestion.invidious import InvidiousProvider

logger = logging.getLogger("jobs.ingest")

# Instantiate providers once
rss_provider = RSSProvider()
invidious_provider = InvidiousProvider()

def get_provider(provider_name: str):
    """Factory helper to fetch configured client instance."""
    if provider_name == "invidious":
        return invidious_provider
    # Fallback to standard RSS
    return rss_provider

async def sync_channel(db: Session, channel: Channel, force: bool = False) -> int:
    """Sync a single channel. Returns number of new videos ingested."""
    now = datetime.now(timezone.utc)
    
    # Frequency check: skip if not enough minutes have passed since last fetch
    if not force and channel.last_fetched_at:
        elapsed = (now - channel.last_fetched_at).total_seconds() / 60.0
        if elapsed < channel.polling_interval_minutes:
            logger.debug(f"Skipping channel {channel.title} (last fetched {elapsed:.1f} mins ago)")
            return 0

    logger.info(f"Syncing channel: {channel.title} ({channel.id}) using provider: {channel.provider}")
    provider = get_provider(channel.provider)
    
    try:
        # Fetch metadata using protocol method
        videos_metadata, new_etag, new_last_modified = await provider.fetch_channel_videos(
            channel_id=channel.id,
            rss_url=channel.rss_url,
            etag=channel.etag,
            last_modified=channel.last_modified
        )
        
        new_count = 0
        for meta in videos_metadata:
            # Check if video already exists to suppress duplicates
            existing_video = db.scalar(select(Video).where(Video.id == meta.video_id))
            if existing_video:
                continue

            # Create video record in 'pending' state to feed processing tasks
            video = Video(
                id=meta.video_id,
                channel_id=channel.id,
                title=meta.title,
                description=meta.description,
                thumbnail_url=meta.thumbnail_url,
                publish_date=meta.publish_date,
                url=meta.url,
                processing_status="pending", # FEEDS PIPELINE
                raw_metadata=meta.raw_metadata
            )
            db.add(video)
            new_count += 1

        # Update channel tracking metrics
        channel.last_fetched_at = now
        if new_etag:
            channel.etag = new_etag
        if new_last_modified:
            channel.last_modified = new_last_modified
        
        db.commit()
        logger.info(f"Channel {channel.title} sync complete. Ingested {new_count} new videos.")
        return new_count

    except Exception as e:
        logger.error(f"Error syncing channel {channel.title} ({channel.id}): {str(e)}")
        db.rollback()
        return 0

async def run_ingestion(force: bool = False):
    """Main ingestion coordinator function that polls all channels."""
    db = SessionLocal()
    try:
        # Get all channels
        channels = db.scalars(select(Channel)).all()
        if not channels:
            logger.info("No channels registered. Ingestion job idle.")
            return

        total_new_videos = 0
        for channel in channels:
            new_videos = await sync_channel(db, channel, force=force)
            total_new_videos += new_videos
            # Play nice with network rate limiting
            await asyncio.sleep(1.0)
            
        logger.info(f"Ingestion sweep completed. Total new items: {total_new_videos}")
    finally:
        db.close()

if __name__ == "__main__":
    # Setup clean output formatting for manual CLI testing
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    logger.info("Starting manual ingestion sweep...")
    asyncio.run(run_ingestion(force=True))
