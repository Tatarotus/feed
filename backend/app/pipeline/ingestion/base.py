from typing import Protocol, List, Dict, Any
from datetime import datetime

class VideoMetadata:
    def __init__(
        self,
        video_id: str,
        channel_id: str,
        title: str,
        description: str,
        publish_date: datetime,
        thumbnail_url: str,
        url: str,
        raw_metadata: Dict[str, Any]
    ):
        self.video_id = video_id
        self.channel_id = channel_id
        self.title = title
        self.description = description
        self.publish_date = publish_date
        self.thumbnail_url = thumbnail_url
        self.url = url
        self.raw_metadata = raw_metadata

    def __repr__(self) -> str:
        return f"<VideoMetadata id={self.video_id} title={self.title[:30]}>"


class VideoSource(Protocol):
    async def fetch_channel_videos(
        self,
        channel_id: str,
        rss_url: str,
        etag: str = None,
        last_modified: str = None
    ) -> tuple[List[VideoMetadata], str, str]:
        """
        Fetch the latest videos from a channel.
        
        Returns:
            Tuple of (List of VideoMetadata parsed, new_etag, new_last_modified)
        """
        ...
