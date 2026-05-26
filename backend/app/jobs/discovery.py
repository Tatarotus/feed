import logging
import asyncio
import httpx
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Interest, Channel, Video

logger = logging.getLogger("jobs.discovery")

# Robust list of public Invidious instances for failover routing
INVIDIOUS_INSTANCES = [
    "https://inv.thepixora.com",
    "https://yt.chocolatemoo53.com",
    "https://invidious.privacydev.net",
    "https://invidious.nerdvpn.de",
    "https://iv.melmac.space",
    "https://invidious.flokinet.to",
    "https://yewtu.be"
]

async def search_invidious_videos(query: str, limit: int = 5) -> list:
    """
    Search Invidious for videos matching a given topic, with automatic failover
    across multiple active public instances to circumvent Cloudflare/403 blocks.
    """
    params = {
        "q": query,
        "type": "video"
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    
    for instance_url in INVIDIOUS_INSTANCES:
        api_url = f"{instance_url.rstrip('/')}/api/v1/search"
        logger.info(f"Attempting search on Invidious instance: {instance_url}...")
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.get(api_url, params=params, headers=headers)
                if response.status_code == 200:
                    results = response.json()
                    if isinstance(results, list):
                        logger.info(f"Successfully retrieved {len(results)} results from {instance_url} for query '{query}'")
                        return results[:limit]
                    else:
                        logger.warning(f"Invidious instance {instance_url} returned unexpected structure: {type(results)}")
                else:
                    logger.warning(f"Instance {instance_url} returned HTTP {response.status_code} for query '{query}'")
        except Exception as e:
            logger.warning(f"Search request to Invidious instance {instance_url} failed: {str(e)}")
            
    logger.error(f"All Invidious search instances failed for query '{query}'")
    return []

async def fetch_channel_avatar(channel_id: str) -> str:
    """
    Fetch the YouTube channel avatar/profile icon URL from public Invidious instances.
    """
    instances = list(INVIDIOUS_INSTANCES)
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get("https://api.invidious.io/instances.json")
            if r.status_code == 200:
                data = r.json()
                fetched = [
                    inst[1].get("uri") for inst in data 
                    if inst[1].get("type") == "https" 
                    and inst[1].get("monitor") 
                    and inst[1].get("monitor", {}).get("last_status") == 200 
                    and not inst[1].get("monitor", {}).get("down")
                ]
                for uri in fetched:
                    if uri and uri not in instances:
                        instances.append(uri)
    except Exception:
        pass

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    
    for instance_url in instances:
        api_url = f"{instance_url.rstrip('/')}/api/v1/channels/{channel_id}"
        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                response = await client.get(api_url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    thumbs = data.get("authorThumbnails", [])
                    if thumbs:
                        url = thumbs[0].get("url")
                        if url:
                            if url.startswith("//"):
                                return f"https:{url}"
                            elif url.startswith("/"):
                                return f"{instance_url.rstrip('/')}{url}"
                            return url
        except Exception as e:
            pass
    return None

async def run_discovery():
    """
    Background job that automatically queries Invidious search for user interest topics,
    discovers out-of-network channels/videos, and inserts them in a pending state.
    """
    db = SessionLocal()
    try:
        # Fetch active interest topics
        interests = db.scalars(select(Interest).where(Interest.user_id == 1)).all()
        if not interests:
            logger.info("No active interest topics registered. Discovery job idle.")
            return

        logger.info(f"Starting discovery sweep across {len(interests)} followed interest tracks...")
        total_discovered_videos = 0
        total_discovered_channels = 0

        for interest in interests:
            # Skip manual video seeds (which start with 'Seed:') for raw keyword searches
            topic_query = interest.topic
            if topic_query.startswith("Seed:"):
                # Use title without the 'Seed:' prefix
                topic_query = topic_query.replace("Seed:", "").strip()

            logger.info(f"Discovering adjacent content for interest topic: '{topic_query}'")
            # Fetch top 5 videos for this interest
            discovered_items = await search_invidious_videos(topic_query, limit=5)
            
            for item in discovered_items:
                video_id = item.get("videoId")
                if not video_id:
                    continue

                channel_id = item.get("authorId")
                channel_title = item.get("author", "Discovered Channel")
                if not channel_id:
                    continue

                # 1. Channel Discovery: Add channel if not already in system
                existing_channel = db.scalar(select(Channel).where(Channel.id == channel_id))
                if not existing_channel:
                    logger.info(f"Discovered new out-of-network channel: '{channel_title}' ({channel_id})")
                    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
                    
                    # Fetch channel icon avatar in background
                    avatar_url = await fetch_channel_avatar(channel_id)
                    
                    new_channel = Channel(
                        id=channel_id,
                        title=channel_title,
                        description=f"Auto-discovered channel related to: '{interest.topic}'",
                        rss_url=rss_url,
                        provider="rss",
                        is_trusted=False,  # Discovery channels are not trusted by default
                        is_subscribed=False,  # Out-of-network flag!
                        thumbnail_url=avatar_url,  # Store the channel icon avatar URL!
                        quality_score=0.8,
                        preference_score=1.0,
                        polling_interval_minutes=360
                    )
                    db.add(new_channel)
                    total_discovered_channels += 1
                    # Flush to get channel bound before video insert
                    db.flush()

                # 2. Video Discovery: Add video if not already in system
                existing_video = db.scalar(select(Video).where(Video.id == video_id))
                if not existing_video:
                    title = item.get("title", "Untitled Discovered Video")
                    description = item.get("description", "")
                    
                    # Parse published timestamp or use current time
                    published_timestamp = item.get("published")
                    try:
                        publish_date = datetime.fromtimestamp(published_timestamp, tz=timezone.utc)
                    except Exception:
                        publish_date = datetime.now(timezone.utc)

                    # Always use robust, direct YouTube CDN thumbnail url to guarantee 100% loading reliability in user browser
                    thumbnail_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

                    video_url = f"https://www.youtube.com/watch?v={video_id}"

                    new_video = Video(
                        id=video_id,
                        channel_id=channel_id,
                        title=title,
                        description=description,
                        thumbnail_url=thumbnail_url,
                        publish_date=publish_date,
                        url=video_url,
                        processing_status="pending",  # Processed asynchronously by pipeline
                        raw_metadata={
                            "view_count": item.get("viewCount", 0),
                            "author": channel_title,
                            "length_seconds": item.get("lengthSeconds", 0),
                            "discovery_seed_topic": interest.topic
                        }
                    )
                    db.add(new_video)
                    total_discovered_videos += 1
            
            # Commit after each interest to persist progress
            db.commit()
            # Play nice with external api limits
            await asyncio.sleep(1.0)

        logger.info(f"Discovery sweep completed. Created {total_discovered_channels} new channels and {total_discovered_videos} discovery videos in a pending state.")

    except Exception as e:
        logger.error(f"Error running discovery pipeline: {str(e)}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    logger.info("Manually triggering discovery job...")
    asyncio.run(run_discovery())
