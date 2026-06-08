import asyncio
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Channel, Interest, Video

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
        except Exception:
            pass
    return None

async def run_discovery():
    """
    Sweeps the web for channels and videos matching followed topics,
    discovers out-of-network channels/videos, and inserts them in a pending state.
    """
    # 1. Fetch interest topics in a short-lived session
    db = SessionLocal()
    try:
        interests = db.scalars(select(Interest).where(Interest.user_id == 1)).all()
        # Extract fields to avoid lazy-loading issues once the session is closed
        topic_queries = [(i.id, i.topic) for i in interests]
    except Exception as e:
        logger.error(f"Error fetching interests for discovery: {str(e)}")
        return
    finally:
        db.close()

    if not topic_queries:
        logger.info("No active interest topics registered. Discovery job idle.")
        return

    logger.info(f"Starting discovery sweep across {len(topic_queries)} followed interest tracks...")
    total_discovered_videos = 0
    total_discovered_channels = 0

    for _interest_id, topic in topic_queries:
        topic_query = topic
        if topic_query.startswith("Seed:"):
            topic_query = topic_query.replace("Seed:", "").strip()

        logger.info(f"Discovering adjacent content for interest topic: '{topic_query}'")
        try:
            discovered_items = await search_invidious_videos(topic_query, limit=5)
        except Exception as e:
            logger.error(f"Failed to search videos for topic '{topic_query}': {str(e)}")
            continue

        for item in discovered_items:
            video_id = item.get("videoId")
            if not video_id:
                continue

            channel_id = item.get("authorId")
            channel_title = item.get("author", "Discovered Channel")
            if not channel_id:
                continue

            # 2. Check channel existence and get details without open transaction
            channel_exists = False
            db = SessionLocal()
            try:
                existing_channel = db.scalar(select(Channel).where(Channel.id == channel_id))
                if existing_channel:
                    channel_exists = True
            except Exception as e:
                logger.error(f"Error checking channel existence: {str(e)}")
            finally:
                db.close()

            avatar_url = None
            if not channel_exists:
                # Fetch avatar url over network without any DB connection held
                try:
                    avatar_url = await fetch_channel_avatar(channel_id)
                except Exception as e:
                    logger.warning(f"Failed to fetch avatar for {channel_id}: {str(e)}")

            # 3. Short-lived session to insert channel and video safely
            db = SessionLocal()
            try:
                existing_channel = db.scalar(select(Channel).where(Channel.id == channel_id))
                if not existing_channel:
                    logger.info(f"Discovered new out-of-network channel: '{channel_title}' ({channel_id})")
                    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
                    new_channel = Channel(
                        id=channel_id,
                        title=channel_title,
                        description=f"Auto-discovered channel related to: '{topic}'",
                        rss_url=rss_url,
                        provider="rss",
                        is_trusted=False,
                        is_subscribed=False,
                        thumbnail_url=avatar_url,
                        quality_score=0.8,
                        preference_score=1.0,
                        polling_interval_minutes=360
                    )
                    db.add(new_channel)
                    total_discovered_channels += 1
                    db.flush()

                existing_video = db.scalar(select(Video).where(Video.id == video_id))
                if not existing_video:
                    title = item.get("title", "Untitled Discovered Video")
                    description = item.get("description", "")

                    published_timestamp = item.get("published")
                    try:
                        publish_date = datetime.fromtimestamp(published_timestamp, tz=timezone.utc)
                    except Exception:
                        publish_date = datetime.now(timezone.utc)

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
                        processing_status="pending",
                        raw_metadata={
                            "view_count": item.get("viewCount", 0),
                            "author": channel_title,
                            "length_seconds": item.get("lengthSeconds", 0),
                            "discovery_seed_topic": topic
                        }
                    )
                    db.add(new_video)
                    total_discovered_videos += 1

                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"Error inserting discovered items: {str(e)}")
            finally:
                db.close()

        # Play nice with external api limits
        await asyncio.sleep(1.0)

    logger.info(f"Discovery sweep completed. Created {total_discovered_channels} new channels and {total_discovered_videos} discovery videos in a pending state.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    logger.info("Manually triggering discovery job...")
    asyncio.run(run_discovery())
