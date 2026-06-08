from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.jobs.ingest import sync_channel
from app.models import Channel
from app.schemas import ChannelCreate, ChannelResponse, ChannelUpdate

router = APIRouter(prefix="/channels", tags=["Channels"])

@router.get("", response_model=List[ChannelResponse])
def list_channels(db: Session = Depends(get_db)):
    """Fetch all registered channel subscriptions."""
    return db.scalars(
        select(Channel)
        .where(Channel.is_subscribed == True)
        .order_by(Channel.title.asc())
    ).all()

import httpx


async def fetch_channel_avatar(channel_id: str) -> str:
    """
    Fetch the YouTube channel avatar/profile icon URL from public Invidious instances.
    """
    invidious_instances = [
        "https://inv.thepixora.com",
        "https://yt.chocolatemoo53.com",
        "https://invidious.privacydev.net",
        "https://invidious.nerdvpn.de",
        "https://yewtu.be"
    ]
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
                    if uri and uri not in invidious_instances:
                        invidious_instances.append(uri)
    except Exception:
        pass

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    for instance in invidious_instances:
        api_url = f"{instance.rstrip('/')}/api/v1/channels/{channel_id}"
        try:
            async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
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
                                return f"{instance.rstrip('/')}{url}"
                            return url
        except Exception:
            pass
    return None

import re


async def resolve_youtube_channel(user_input: str) -> tuple[str, str]:
    """
    Resolves a YouTube channel ID and Title from a URL, handle, or plain ID.
    Returns: (channel_id, channel_title)
    Raises: ValueError if the channel cannot be resolved.
    """
    user_input = user_input.strip()

    # Check if user_input is a plain 24-character channel ID starting with UC
    is_plain_id = re.match(r"^UC[a-zA-Z0-9_-]{22}$", user_input)

    # Construct target scraping URL
    if is_plain_id:
        target_url = f"https://www.youtube.com/channel/{user_input}"
    elif "youtube.com" in user_input or "youtu.be" in user_input:
        target_url = user_input
        if not target_url.startswith("http"):
            target_url = f"https://{target_url}"
    else:
        # It's a handle or name. Ensure it starts with @ for handle lookup
        handle = user_input if user_input.startswith("@") else f"@{user_input}"
        target_url = f"https://www.youtube.com/{handle}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(target_url, headers=headers)
            if response.status_code != 200:
                raise ValueError(f"YouTube page returned status code {response.status_code}")

            html = response.text

            # Extract canonical link containing channel ID
            canonical_match = re.search(r'<link rel=\"canonical\" href=\"(.*?)\"', html)
            channel_id = None
            if canonical_match:
                url = canonical_match.group(1)
                id_match = re.search(r'UC[a-zA-Z0-9_-]{22}', url)
                if id_match:
                    channel_id = id_match.group(0)

            # Fallback to direct search of UC ID patterns
            if not channel_id:
                id_match = re.search(r'UC[a-zA-Z0-9_-]{22}', html)
                if id_match:
                    channel_id = id_match.group(0)

            if not channel_id:
                raise ValueError("Could not extract YouTube Channel ID from page content.")

            # Extract channel title
            title = None
            meta_name_match = re.search(r'itemprop=\"name\" content=\"(.*?)\"', html) or re.search(r'meta itemprop=\"name\" content=\"(.*?)\"', html)
            if meta_name_match:
                title = meta_name_match.group(1)

            if not title:
                title_match = re.search(r'<title>(.*?)</title>', html)
                if title_match:
                    title = title_match.group(1).replace(" - YouTube", "").strip()

            if not title:
                title = f"YouTube Channel {channel_id}"

            return channel_id, title

    except Exception as e:
        # Fallback to Invidious search
        invidious_instances = [
            "https://inv.thepixora.com",
            "https://yt.chocolatemoo53.com",
            "https://invidious.privacydev.net",
            "https://invidious.nerdvpn.de",
            "https://yewtu.be"
        ]

        if is_plain_id:
            for instance in invidious_instances:
                api_url = f"{instance.rstrip('/')}/api/v1/channels/{user_input}"
                try:
                    async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
                        r = await client.get(api_url, headers=headers)
                        if r.status_code == 200:
                            data = r.json()
                            return user_input, data.get("author", f"YouTube Channel {user_input}")
                except Exception:
                    pass
        else:
            query = user_input
            if "youtube.com" in query:
                if "/@" in query:
                    query = "@" + query.split("/@")[-1].split("/")[0].split("?")[0]
                elif "/channel/" in query:
                    query = query.split("/channel/")[-1].split("/")[0].split("?")[0]
                elif "/c/" in query:
                    query = query.split("/c/")[-1].split("/")[0].split("?")[0]
                elif "/user/" in query:
                    query = query.split("/user/")[-1].split("/")[0].split("?")[0]

            for instance in invidious_instances:
                api_url = f"{instance.rstrip('/')}/api/v1/search"
                params = {"q": query, "type": "channel"}
                try:
                    async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
                        r = await client.get(api_url, params=params, headers=headers)
                        if r.status_code == 200:
                            data = r.json()
                            if isinstance(data, list) and len(data) > 0:
                                ch = data[0]
                                return ch.get("authorId"), ch.get("author")
                except Exception:
                    pass

        raise ValueError(f"Failed to resolve YouTube channel: {str(e)}")

@router.post("", response_model=ChannelResponse, status_code=status.HTTP_201_CREATED)
async def create_channel(channel_in: ChannelCreate, db: Session = Depends(get_db)):
    """Subscribe to a new channel."""
    try:
        resolved_id, resolved_title = await resolve_youtube_channel(channel_in.id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to resolve YouTube channel: {str(e)}"
        )

    existing = db.scalar(select(Channel).where(Channel.id == resolved_id))
    if existing:
        if not existing.is_subscribed:
            # Upgrade auto-discovered channel to full manual subscription
            existing.is_subscribed = True
            existing.is_trusted = True
            existing.title = resolved_title
            if not existing.thumbnail_url:
                existing.thumbnail_url = await fetch_channel_avatar(resolved_id)
            db.commit()
            db.refresh(existing)
            return existing
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Channel is already registered."
            )

    # Clean custom RSS link construction
    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={resolved_id}"

    # Fetch avatar in background
    avatar_url = await fetch_channel_avatar(resolved_id)

    channel = Channel(
        id=resolved_id,
        title=resolved_title,
        description=channel_in.description or f"Channel resolved from: '{channel_in.id}'",
        custom_name=channel_in.custom_name,
        rss_url=rss_url,
        provider=channel_in.provider,
        is_trusted=channel_in.is_trusted,
        is_subscribed=True,  # Explicitly subscribed
        thumbnail_url=avatar_url,
        quality_score=channel_in.quality_score,
        preference_score=channel_in.preference_score,
        polling_interval_minutes=channel_in.polling_interval_minutes,
        category=channel_in.category
    )

    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel

@router.patch("/{channel_id}", response_model=ChannelResponse)
def update_channel(channel_id: str, channel_update: ChannelUpdate, db: Session = Depends(get_db)):
    """Update channel classification settings (trust, quality, or preference adjustments)."""
    channel = db.scalar(select(Channel).where(Channel.id == channel_id))
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found.")

    update_data = channel_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(channel, field, value)

    db.commit()
    db.refresh(channel)
    return channel

@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_channel(channel_id: str, db: Session = Depends(get_db)):
    """Unsubscribe from a channel and clean up all cascade video records."""
    channel = db.scalar(select(Channel).where(Channel.id == channel_id))
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found.")

    db.delete(channel)
    db.commit()
    return

@router.post("/{channel_id}/sync", status_code=status.HTTP_202_ACCEPTED)
async def force_sync_channel(
    channel_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Triggers an out-of-band manual synchronization sweep for a channel in background."""
    channel = db.scalar(select(Channel).where(Channel.id == channel_id))
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found.")

    # Queue background task to preserve API responsiveness
    background_tasks.add_task(sync_channel, db, channel, force=True)
    return {"message": f"Sync task triggered in background for channel {channel.title}."}
