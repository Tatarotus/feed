import logging
from typing import List, Dict, Any, Tuple
import httpx
from datetime import datetime

from app.pipeline.ingestion.base import VideoSource, VideoMetadata

logger = logging.getLogger(__name__)

class InvidiousProvider(VideoSource):
    def __init__(self, instance_url: str = "https://yewtu.be"):
        # Default instance can be overridden in configuration
        self.instance_url = instance_url.rstrip("/")

    async def fetch_channel_videos(
        self,
        channel_id: str,
        rss_url: str = None,
        etag: str = None,
        last_modified: str = None
    ) -> Tuple[List[VideoMetadata], str, str]:
        """
        Fetch channel videos using Invidious JSON API endpoint.
        """
        api_url = f"{self.instance_url}/api/v1/channels/videos/{channel_id}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json"
        }
        
        if etag:
            headers["If-None-Match"] = etag

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(api_url, headers=headers)
                
                if response.status_code == 304:
                    logger.info(f"Invidious channel {channel_id} feed unchanged (304).")
                    return [], etag, last_modified

                response.raise_for_status()
                
                new_etag = response.headers.get("ETag")
                new_last_modified = response.headers.get("Last-Modified")
                
                videos_json = response.json()
                if not isinstance(videos_json, list):
                    logger.warning(f"Invidious API returned unexpected structure for {channel_id}")
                    return [], new_etag, new_last_modified

                videos: List[VideoMetadata] = []
                for item in videos_json:
                    video_id = item.get("videoId")
                    if not video_id:
                        continue

                    title = item.get("title", "Untitled Invidious Video")
                    description = item.get("description", "")
                    
                    # Date parsing
                    published_timestamp = item.get("published")
                    try:
                        publish_date = datetime.fromtimestamp(published_timestamp).astimezone()
                    except Exception:
                        publish_date = datetime.now().astimezone()

                    # Always use robust, direct YouTube CDN thumbnail url to guarantee 100% loading reliability in user browser
                    thumbnail_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

                    video_url = f"{self.instance_url}/watch?v={video_id}"

                    # Clean metadata
                    raw_metadata = {
                        "view_count": item.get("viewCount", 0),
                        "author": item.get("author", ""),
                        "length_seconds": item.get("lengthSeconds", 0)
                    }

                    video_meta = VideoMetadata(
                        video_id=video_id,
                        channel_id=channel_id,
                        title=title,
                        description=description,
                        publish_date=publish_date,
                        thumbnail_url=thumbnail_url,
                        url=video_url,
                        raw_metadata=raw_metadata
                    )
                    videos.append(video_meta)

                logger.info(f"Successfully parsed {len(videos)} videos from Invidious API for {channel_id}")
                return videos, new_etag, new_last_modified

        except Exception as e:
            logger.error(f"Failed to fetch videos from Invidious API for channel {channel_id}: {str(e)}")
            raise e
