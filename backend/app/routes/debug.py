
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.jobs.coordinator import run_pipeline_sweep
from app.models import Event, FeedImpression, Interest, LikedVideo, UserInteraction, Video
from app.pipeline.ranking.reranker import Stage2Reranker

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
    event_type: str,  # 'watch', 'like', 'dislike', 'skip', 'queue_add', 'dismiss', 'subscribe', 'click', 'impression'
    watch_time_pct: float = 0.0,
    rating: int = None,
    watch_duration_seconds: float = 0.0,
    rerank_score: float = 0.0,
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

    # 1. Update user_interactions table
    interaction = UserInteraction(
        user_id=1,
        video_id=video_id,
        interaction_type=event_type,
        watch_duration_seconds=watch_duration_seconds,
        rerank_score=rerank_score,
        event_metadata={"watch_time_pct": watch_time_pct, "rating": rating}
    )
    db.add(interaction)

    # 1.5. Update FeedImpression table to record interaction
    if event_type == "click":
        recent_imp = db.scalar(
            select(FeedImpression)
            .where(
                and_(
                    FeedImpression.user_id == 1,
                    FeedImpression.video_id == video_id
                )
            )
            .order_by(FeedImpression.shown_at.desc())
            .limit(1)
        )
        if recent_imp:
            recent_imp.clicked = True
    elif event_type == "watch":
        recent_imp = db.scalar(
            select(FeedImpression)
            .where(
                and_(
                    FeedImpression.user_id == 1,
                    FeedImpression.video_id == video_id
                )
            )
            .order_by(FeedImpression.shown_at.desc())
            .limit(1)
        )
        if recent_imp:
            recent_imp.clicked = True
            recent_imp.watch_duration = max(recent_imp.watch_duration, watch_duration_seconds)


    # 2. Update liked_videos table if event_type == "like"
    if event_type == "like" or rating == 1:
        # Calculate semantic score
        interests = db.scalars(select(Interest).where(Interest.user_id == 1)).all()
        semantic_score = 0.0
        best_topic = "None"
        if video_exists.embedding is not None and interests:
            for interest in interests:
                if interest.embedding is not None:
                    sim = sum(a * b for a, b in zip(video_exists.embedding, interest.embedding))
                    if sim > semantic_score:
                        semantic_score = max(float(sim), 0.0)
                        best_topic = interest.topic

        # Persist liked video permanently
        existing_like = db.scalar(
            select(LikedVideo).where(
                and_(
                    LikedVideo.user_id == 1,
                    LikedVideo.video_id == video_id
                )
            )
        )
        if not existing_like:
            liked_video = LikedVideo(
                user_id=1,
                video_id=video_id,
                channel_id=video_exists.channel_id,
                semantic_score=semantic_score,
                source_bucket=best_topic,
                watch_duration_seconds=watch_duration_seconds,
                embedding=video_exists.embedding,
                metadata_json={
                    "title": video_exists.title,
                    "description": video_exists.description,
                    "best_topic": best_topic
                }
            )
            db.add(liked_video)

    # 3. Dynamic preference tuning based on explicit feedback mapped to standard caps
    channel = video_exists.channel
    if channel:
        old_pref = channel.preference_score if channel.preference_score is not None else 1.0

        if event_type == "like" or rating == 1:
            # Boost channel preference score moderately (+0.06)
            channel.preference_score = max(0.25, min(1.50, old_pref + 0.06))
            logger.info(f"Boosted channel {channel.title} preference_score to {channel.preference_score}")
        elif event_type in ["dislike", "disliked"] or rating == -1:
            # Demote channel preference score (-0.10)
            channel.preference_score = max(0.25, min(1.50, old_pref - 0.10))
            logger.info(f"Demoted channel {channel.title} preference_score to {channel.preference_score}")
        elif event_type == "subscribe":
            # Set internal subscription relationship & boost preference score (+0.15)
            channel.is_subscribed = True
            channel.preference_score = max(0.25, min(1.50, old_pref + 0.15))
            logger.info(f"Subscribed to channel {channel.title} and boosted preference_score to {channel.preference_score}")

            # Increase semantic topic affinity
            interests = db.scalars(select(Interest).where(Interest.user_id == 1)).all()
            if video_exists.embedding is not None and interests:
                best_interest = None
                max_sim = 0.0
                for interest in interests:
                    if interest.embedding is not None:
                        sim = sum(a * b for a, b in zip(video_exists.embedding, interest.embedding))
                        if sim > max_sim:
                            max_sim = sim
                            best_interest = interest

                if best_interest and max_sim >= 0.35:
                    best_interest.weight = max(0.1, min(5.0, best_interest.weight + 0.15))
                    logger.info(f"Boosted interest topic '{best_interest.topic}' weight to {best_interest.weight} due to channel subscription")

    db.commit()

    return {"status": "success", "event_id": event.id}
