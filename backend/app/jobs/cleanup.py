import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, delete, select
from sqlalchemy.orm import Session, joinedload

from app.database import SessionLocal
from app.models import Channel, Event, Interest, LikedVideo, QueueItem, Video

logger = logging.getLogger("jobs.cleanup")

def _get_channel_delta(event) -> float:
    et = event.event_type
    rating = getattr(event, "rating", None)
    if et == "impression":
        return 0.0
    if et == "click":
        return 0.01
    if et == "watch":
        pct = getattr(event, "watch_time_pct", None)
        if pct is not None:
            if pct >= 0.7:
                return 0.04
            if pct <= 0.2:
                return -0.05
            return 0.02
        return 0.02
    if et == "like" or rating == 1:
        return 0.06
    if et == "subscribe":
        return 0.15
    if et in ("dislike", "disliked") or rating == -1:
        return -0.10
    if et in ("skip", "dismiss"):
        return -0.05
    return 0.0

def _get_interest_delta(event, similarity: float) -> float:
    et = event.event_type
    rating = getattr(event, "rating", None)
    if et == "like" or rating == 1:
        return 0.06 * similarity
    if et == "subscribe":
        return 0.15 * similarity
    if et == "watch":
        pct = getattr(event, "watch_time_pct", None) or 0.5
        if pct >= 0.7:
            return 0.04 * similarity
        if pct <= 0.2:
            return -0.05 * similarity
        return 0.0
    if et == "queue_add":
        return 0.02 * similarity
    if et in ("dislike", "disliked") or rating == -1:
        return -0.10 * similarity
    if et in ("skip", "dismiss"):
        return -0.05 * similarity
    return 0.0

def _process_active_learning(db: Session, events, interests, channels_boost):
    interest_weight_changes = {interest.id: 0.0 for interest in interests}

    for event in events:
        video = event.video
        if not video:
            continue

        c_id = video.channel_id
        if c_id:
            if c_id not in channels_boost:
                channels_boost[c_id] = 0.0
            channels_boost[c_id] += _get_channel_delta(event)

        if video.embedding is not None and interests:
            v_emb = video.embedding
            for interest in interests:
                if interest.embedding is None:
                    continue

                dot_product = sum(a * b for a, b in zip(v_emb, interest.embedding))
                similarity = max(float(dot_product), 0.0)

                if similarity >= 0.45:
                    interest_weight_changes[interest.id] += _get_interest_delta(event, similarity)

    for interest in interests:
        delta = interest_weight_changes.get(interest.id, 0.0)
        if delta != 0.0:
            old_w = interest.weight
            interest.weight = max(0.25, min(1.50, old_w + delta))
            logger.info(f"Active Telemetry Tuned curation vector '{interest.topic}' weight: {old_w:.2f}x -> {interest.weight:.2f}x (delta: {delta:+.2f})")

    for c_id, delta in channels_boost.items():
        if delta == 0.0:
            continue

        channel = db.scalar(select(Channel).where(Channel.id == c_id))
        if channel:
            old_pref = channel.preference_score if channel.preference_score is not None else 1.0
            new_pref = max(0.25, min(1.50, old_pref + delta))
            channel.preference_score = new_pref
            logger.info(f"Active Telemetry Tuned channel '{channel.title}' preference weight: {old_pref:.2f}x -> {new_pref:.2f}x (delta: {delta:+.2f})")

def _apply_passive_decay(interests):
    for interest in interests:
        old_w = interest.weight
        if old_w > 1.0:
            interest.weight = max(1.0, old_w * 0.99)
            logger.debug(f"Passive decay applied to vector '{interest.topic}': {old_w:.2f}x -> {interest.weight:.2f}x")
        elif old_w < 1.0:
            interest.weight = min(1.0, old_w * 1.01)
            logger.debug(f"Passive reinforcement applied to vector '{interest.topic}': {old_w:.2f}x -> {interest.weight:.2f}x")

def process_interaction_telemetry(db: Session):
    """
    Sweeps logged interaction events and dynamically updates:
    1. Channel preference scores (in-network boost / demotion mapped to standard bounds)
    2. Interest Topic & Training Seed weights (semantic vector tuning loop with passive decay)
    """
    logger.info("Processing recent telemetry events to tune recommendation weights...")

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    stmt = select(Event).options(joinedload(Event.video)).where(Event.created_at >= cutoff)
    events = db.scalars(stmt).all()

    interests = db.scalars(select(Interest)).all()
    channels_boost = {}

    if events:
        _process_active_learning(db, events, interests, channels_boost)

    if interests:
        _apply_passive_decay(interests)

    db.commit()

def purge_expired_unseen_videos(db: Session):
    """
    Deletes un-queued, un-liked, and unseen videos older than 30 days.
    Keeps the database lightweight and performant.
    """
    logger.info("Pruning expired unseen videos from catalog database...")
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    try:
        # Fetch video subquery to check against active queue items and liked videos
        subq_queue = select(QueueItem.video_id)
        subq_liked = select(LikedVideo.video_id)

        # Query and delete videos older than 30 days, not saved in queue, and not liked
        delete_stmt = (
            delete(Video)
            .where(
                and_(
                    Video.publish_date <= cutoff,
                    Video.id.not_in(subq_queue),
                    Video.id.not_in(subq_liked)
                )
            )
        )

        result = db.execute(delete_stmt)
        db.commit()
        logger.info(f"Successfully pruned {result.rowcount} expired unseen videos from database.")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to prune expired videos: {str(e)}")

def purge_old_impressions(db: Session):
    """
    Deletes feed impressions older than 30 days to keep the database lightweight.
    """
    logger.info("Pruning old feed impressions from database...")
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    try:
        from app.models import FeedImpression
        delete_stmt = delete(FeedImpression).where(FeedImpression.shown_at <= cutoff)
        result = db.execute(delete_stmt)
        db.commit()
        logger.info(f"Successfully pruned {result.rowcount} old feed impressions from database.")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to prune old impressions: {str(e)}")

def run_cleanup_and_tuning():
    """Main maintenance execution wrapper."""
    db = SessionLocal()
    try:
        # Tune preference weights from interactions
        process_interaction_telemetry(db)
        # Purge old data
        purge_expired_unseen_videos(db)
        # Purge old impressions
        purge_old_impressions(db)
    finally:
        db.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    logger.info("Running standalone cleanup and active-learning job...")
    run_cleanup_and_tuning()

