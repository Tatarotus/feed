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

async def sync_channel(channel_id: str, force: bool = False) -> int:
    """Sync a single channel using short-lived transactions. Returns number of new videos ingested."""
    now = datetime.now(timezone.utc)
    
    # 1. Fetch channel config in a quick session
    db = SessionLocal()
    try:
        channel = db.scalar(select(Channel).where(Channel.id == channel_id))
        if not channel:
            logger.error(f"Channel not found in DB: {channel_id}")
            return 0
        
        # Frequency check: skip if not enough minutes have passed since last fetch
        if not force and channel.last_fetched_at:
            elapsed = (now - channel.last_fetched_at).total_seconds() / 60.0
            if elapsed < channel.polling_interval_minutes:
                logger.debug(f"Skipping channel {channel.title} (last fetched {elapsed:.1f} mins ago)")
                return 0

        logger.info(f"Syncing channel: {channel.title} ({channel.id}) using provider: {channel.provider}")
        provider_name = channel.provider
        rss_url = channel.rss_url
        etag = channel.etag
        last_modified = channel.last_modified
        channel_title = channel.title
    finally:
        db.close()

    provider = get_provider(provider_name)
    
    try:
        # 2. Fetch metadata over network WITHOUT any active database session
        videos_metadata, new_etag, new_last_modified = await provider.fetch_channel_videos(
            channel_id=channel_id,
            rss_url=rss_url,
            etag=etag,
            last_modified=last_modified
        )
        
        if not videos_metadata:
            # Still update the last fetched timestamp to avoid rapid retries
            db = SessionLocal()
            try:
                channel = db.scalar(select(Channel).where(Channel.id == channel_id))
                if channel:
                    channel.last_fetched_at = now
                    db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to update last_fetched_at for empty sync: {str(e)}")
            finally:
                db.close()
            return 0
        
        new_count = 0
        db = SessionLocal()
        try:
            # Re-fetch channel in this session to bind updates
            channel = db.scalar(select(Channel).where(Channel.id == channel_id))
            if not channel:
                logger.error(f"Channel {channel_id} vanished during network call.")
                return 0

            for meta in videos_metadata:
                # Check if video already exists to suppress duplicates
                existing_video = db.scalar(select(Video).where(Video.id == meta.video_id))
                if existing_video:
                    continue

                # Create video record in 'pending' state to feed processing tasks
                video = Video(
                    id=meta.video_id,
                    channel_id=channel_id,
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
            logger.info(f"Channel {channel_title} sync complete. Ingested {new_count} new videos.")
            return new_count

        except Exception as e:
            db.rollback()
            logger.error(f"Error persisting ingested videos for channel {channel_title}: {str(e)}")
            return 0
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error syncing channel {channel_id} over network: {str(e)}")
        return 0

async def run_ingestion(force: bool = False):
    """Main ingestion coordinator function that polls all channels."""
    db = SessionLocal()
    try:
        # Get all channel IDs in a short-lived query
        channels = db.scalars(select(Channel)).all()
        channel_ids = [c.id for c in channels]
    except Exception as e:
        logger.error(f"Error loading channels for ingestion: {str(e)}")
        return
    finally:
        db.close()

    if not channel_ids:
        logger.info("No channels registered. Ingestion job idle.")
        return

    total_new_videos = 0
    for channel_id in channel_ids:
        new_videos = await sync_channel(channel_id, force=force)
        total_new_videos += new_videos
        # Play nice with network rate limiting
        await asyncio.sleep(1.0)

if __name__ == "__main__":
    # Setup clean output formatting for manual CLI testing
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    logger.info("Starting manual ingestion sweep...")
    asyncio.run(run_ingestion(force=True))
