from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import Dict, Any

from app.database import get_db
from app.models import Video, Channel, Interest, Event
from app.pipeline.ranking.reranker import Stage2Reranker
from app.jobs.coordinator import run_pipeline_sweep

router = APIRouter(prefix="/debug", tags=["Diagnostics"])

@router.get("/explain/{video_id}")
def explain_video_scoring(video_id: str, db: Session = Depends(get_db)):
    """
    Detailed explanation sandbox.
    Returns point-by-point scoring components for a specific video id.
    """
    video = db.scalar(select(Video).where(Video.id == video_id))
    if not video:
        raise HTTPException(status_code=404, detail="Video not found.")

    channel = video.channel
    
    # Get user interests to compute similarity
    interests = db.scalars(
        select(Interest).where(Interest.user_id == 1)
    ).all()

    # Instantiate Stage 2 reranker and run evaluation
    reranker = Stage2Reranker(user_interests=interests)
    scored_data = reranker.score_video(video, channel)
    
    return {
        "video_title": video.title,
        "channel_title": channel.title if channel else "Unknown Channel",
        "is_trusted": channel.is_trusted if channel else False,
        "quality_score": channel.quality_score if channel else 1.0,
        "preference_score": channel.preference_score if channel else 1.0,
        "clickbait_score": video.clickbait_score,
        "clickbait_reasons": video.clickbait_reasons,
        "publish_date": video.publish_date,
        
        # Scoring metrics
        "final_calculated_score": scored_data["score"],
        "soft_affinity_badge": scored_data["badge"],
        "best_topic_matched": scored_data["best_topic"],
        "score_breakdown": scored_data["breakdown"]
    }

@router.post("/pipeline/run", status_code=status.HTTP_202_ACCEPTED)
def manual_pipeline_trigger(background_tasks: BackgroundTasks):
    """Triggers an out-of-band sequential sync sweep across all pipeline jobs."""
    background_tasks.add_task(run_pipeline_sweep)
    return {"message": "Coordinated pipeline sweep task queued successfully in background."}

import logging

logger = logging.getLogger("routes.debug")

@router.post("/events", status_code=status.HTTP_201_CREATED)
def log_telemetry_event(
    video_id: str,
    event_type: str,  # 'watch', 'like', 'dislike', 'skip', 'queue_add', 'dismiss'
    watch_time_pct: float = 0.0,
    rating: int = None,
    db: Session = Depends(get_db)
):
    """Log an interaction event for telemetry, vector tuning, and historical replays."""
    # Check if video exists
    video_exists = db.scalar(select(Video).where(Video.id == video_id))
    if not video_exists:
        raise HTTPException(status_code=404, detail="Video not found.")

    # Record the event in DB
    event = Event(
        user_id=1,
        video_id=video_id,
        event_type=event_type,
        watch_time_pct=watch_time_pct,
        rating=rating
    )
    db.add(event)

    # Dynamic preference tuning based on explicit feedback
    channel = video_exists.channel
    if channel:
        if event_type == "like" or rating == 1:
            # Boost channel preference score
            channel.preference_score = min(float(channel.preference_score or 1.0) + 0.15, 2.0)
            logger.info(f"Boosted channel {channel.title} preference_score to {channel.preference_score}")
        elif event_type == "dislike" or rating == -1:
            # Demote channel preference score
            channel.preference_score = max(float(channel.preference_score or 1.0) - 0.25, 0.2)
            logger.info(f"Demoted channel {channel.title} preference_score to {channel.preference_score}")
            
    db.commit()
    
    return {"status": "success", "event_id": event.id}
