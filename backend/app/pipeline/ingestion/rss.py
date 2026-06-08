import logging
from datetime import datetime
from typing import List, Tuple

import feedparser
import httpx
from dateutil import parser as date_parser

from app.pipeline.ingestion.base import VideoMetadata, VideoSource

logger = logging.getLogger(__name__)

class RSSProvider(VideoSource):
    async def fetch_channel_videos(
        self,
        channel_id: str,
        rss_url: str,
        etag: str = None,
        last_modified: str = None
    ) -> Tuple[List[VideoMetadata], str, str]:
        """
        Fetch and parse latest videos for a channel using YouTube RSS.
        Implements HTTP E-tag and Last-Modified caching checks.
        """
        # If no explicit RSS URL is provided, compile the default YouTube channel feed format
        if not rss_url:
            rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

        headers = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        # Follow redirects and support standard browser headers to prevent aggressive blocks
        headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.get(rss_url, headers=headers)

                # Check for 304 Not Modified
                if response.status_code == 304:
                    logger.info(f"Channel {channel_id} feed unchanged (304 Not Modified).")
                    return [], etag, last_modified

                # Raise for standard errors
                response.raise_for_status()

                # Extract new cache headers
                new_etag = response.headers.get("ETag")
                new_last_modified = response.headers.get("Last-Modified")

                # Parse XML content using feedparser
                raw_xml = response.text
                feed_data = feedparser.parse(raw_xml)

                if feed_data.bozo:
                    # Non-fatal parsing issues are logged but still processed if entries exist
                    logger.warning(f"Feed parser bozo exception detected for channel {channel_id}: {feed_data.bozo_exception}")

                videos: List[VideoMetadata] = []
                for entry in feed_data.entries:
                    # YouTube custom namespaces mappings handled cleanly
                    video_id = entry.get("yt_videoid")
                    if not video_id:
                        # Fallback parsing ID string e.g. yt:video:dQw4w9WgXcQ
                        entry_id = entry.get("id", "")
                        if "yt:video:" in entry_id:
                            video_id = entry_id.split(":")[-1]
                        else:
                            continue

                    title = entry.get("title", "Untitled Video")

                    # Capture description from media:description (standard feedparser mapping) or fallback summary
                    description = entry.get("media_description", entry.get("summary", ""))

                    # Date parsing
                    pub_date_str = entry.get("published", "")
                    try:
                        publish_date = date_parser.parse(pub_date_str)
                        # Ensure timezone aware
                        if publish_date.tzinfo is None:
                            publish_date = publish_date.astimezone()
                    except Exception:
                        publish_date = datetime.now().astimezone()

                    # Thumbnail lookup
                    thumbnail_url = ""
                    thumbnails = entry.get("media_thumbnail")
                    if thumbnails and isinstance(thumbnails, list) and len(thumbnails) > 0:
                        thumbnail_url = thumbnails[0].get("url", "")
                    else:
                        # Direct construct fallback
                        thumbnail_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

                    video_url = entry.get("link", f"https://www.youtube.com/watch?v={video_id}")

                    # Raw metadata cache
                    raw_metadata = {
                        "author": entry.get("author", ""),
                        "updated": entry.get("updated", ""),
                        "channel_url": feed_data.feed.get("link", "") if hasattr(feed_data, "feed") else ""
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

                logger.info(f"Successfully parsed {len(videos)} videos from feed for channel {channel_id}")
                return videos, new_etag, new_last_modified

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.error(f"RSS Feed not found for url: {rss_url}")
            else:
                logger.error(f"HTTP status error while fetching RSS for {channel_id}: {str(e)}")
            raise e
        except Exception as e:
            logger.error(f"General failure fetching RSS feed for channel {channel_id}: {str(e)}")
            raise e
