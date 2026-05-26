from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from typing import List

from app.database import get_db
from app.models import Interest
from app.schemas import InterestCreate, InterestUpdate, InterestResponse, SeedCreate
from app.pipeline.enrichment.embedder import embedder
from app.config import settings

router = APIRouter(prefix="/interests", tags=["Interests"])

@router.get("", response_model=List[InterestResponse])
def list_interests(db: Session = Depends(get_db)):
    """Fetch all explicit followed semantic topics."""
    return db.scalars(select(Interest).order_by(Interest.topic.asc())).all()

@router.post("", response_model=InterestResponse, status_code=status.HTTP_201_CREATED)
async def follow_topic(interest_in: InterestCreate, db: Session = Depends(get_db)):
    """
    Follow a new topic keyword.
    Asynchronously queries API embeddings with SQL caching enabled.
    """
    topic_clean = interest_in.topic.strip().lower()
    
    existing = db.scalar(
        select(Interest).where(
            and_(
                Interest.user_id == 1,
                Interest.topic == topic_clean
            )
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Already following topic: '{topic_clean}'"
        )

    try:
        # Await the async generator, passing the active db session for cache lookups
        topic_vector = await embedder.generate_embedding(topic_clean, db=db, input_type="query")
        
        interest = Interest(
            user_id=1,
            topic=topic_clean,
            weight=interest_in.weight,
            embedding_model=settings.EMBEDDING_MODEL,
            embedding_version=settings.EMBEDDING_VERSION,
            embedding=topic_vector
        )
        
        db.add(interest)
        db.commit()
        db.refresh(interest)
        return interest
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate embedding for topic: {str(e)}"
        )

@router.delete("/{interest_id}", status_code=status.HTTP_204_NO_CONTENT)
def unfollow_topic(interest_id: int, db: Session = Depends(get_db)):
    """Unfollow a topic and delete it from the interest profile."""
    interest = db.scalar(select(Interest).where(Interest.id == interest_id))
    if not interest:
        raise HTTPException(status_code=404, detail="Topic not found.")
        
    db.delete(interest)
    db.commit()
    return

@router.patch("/{interest_id}", response_model=InterestResponse)
def update_interest_weight(interest_id: int, body: InterestUpdate, db: Session = Depends(get_db)):
    """Update the weight of an existing interest/topic."""
    interest = db.scalar(select(Interest).where(Interest.id == interest_id))
    if not interest:
        raise HTTPException(status_code=404, detail="Interest not found.")
    
    if body.weight is not None:
        interest.weight = max(body.weight, 0.1)  # floor at 0.1 to avoid zeroing out
    
    db.commit()
    db.refresh(interest)
    return interest

import re
import httpx
import logging

logger = logging.getLogger("routes.interests")

def extract_youtube_video_id(url: str) -> str:
    patterns = [
        r"youtu\.be/([^#\&\?]+)",
        r"youtube\.com/watch\?v=([^#\&\?]+)",
        r"youtube\.com/embed/([^#\&\?]+)",
        r"youtube\.com/v/([^#\&\?]+)",
        r"youtube\.com/shorts/([^#\&\?]+)"
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

async def fetch_video_metadata(video_id: str) -> tuple[str, str]:
    """
    Fetch video title and description.
    First tries public Invidious instances with failover routing.
    Falls back to the standard, unthrottled YouTube oEmbed API for the title.
    """
    # Failover Invidious routing
    invidious_instances = [
        "https://yt.chocolatemoo53.com",
        "https://invidious.privacydev.net",
        "https://invidious.nerdvpn.de",
        "https://yewtu.be"
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
    }
    
    for instance_url in invidious_instances:
        api_url = f"{instance_url.rstrip('/')}/api/v1/videos/{video_id}"
        try:
            async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
                response = await client.get(api_url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    title = data.get("title")
                    description = data.get("description", "")
                    if title:
                        logger.info(f"Successfully fetched video metadata from {instance_url}")
                        return title, description
        except Exception as e:
            logger.warning(f"Failed to fetch metadata from {instance_url}: {e}")
            
    # Fallback to standard YouTube oEmbed (highly reliable, returns title)
    oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            response = await client.get(oembed_url)
            if response.status_code == 200:
                data = response.json()
                title = data.get("title")
                if title:
                    logger.info("Successfully fetched video title from YouTube oEmbed")
                    return title, "No description available (oEmbed fallback)"
    except Exception as e:
        logger.error(f"oEmbed fallback failed: {e}")
        
    return None, None

@router.post("/seed", response_model=InterestResponse, status_code=status.HTTP_201_CREATED)
async def add_manual_seed(seed_in: SeedCreate, db: Session = Depends(get_db)):
    """
    Seed a video liked in the past manually.
    Extracts the video metadata (title, description) from its URL,
    generates its semantic vector embedding, and adds it under topic Seed: [Title].
    """
    url = seed_in.url.strip()
    video_id = extract_youtube_video_id(url)
    if not video_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid YouTube video URL."
        )
        
    title, description = await fetch_video_metadata(video_id)
    if not title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to retrieve video metadata. Make sure the video is public and valid."
        )

    topic_name = f"Seed: {title.strip()}"
    # Truncate topic_name to 100 characters to prevent database column constraints
    if len(topic_name) > 100:
        topic_name = topic_name[:97] + "..."

    # Check for existing duplicate seeds or followed interests
    existing = db.scalar(
        select(Interest).where(
            and_(
                Interest.user_id == 1,
                Interest.topic == topic_name
            )
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Already seeding video: '{title}'"
        )

    # Context to embed is combined title and description
    embed_text = f"{title.strip()}. {description.strip()}" if description else title.strip()

    try:
        # Await embedding queries
        topic_vector = await embedder.generate_embedding(embed_text, db=db, input_type="query")

        interest = Interest(
            user_id=1,
            topic=topic_name,
            weight=seed_in.weight,
            embedding_model=settings.EMBEDDING_MODEL,
            embedding_version=settings.EMBEDDING_VERSION,
            embedding=topic_vector
        )

        db.add(interest)
        db.commit()
        db.refresh(interest)
        return interest

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate vector embedding for manual seed: {str(e)}"
        )
