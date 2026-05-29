import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, and_, delete

from app.database import SessionLocal
from app.models import Event, Channel, Video, QueueItem, Interest, LikedVideo

logger = logging.getLogger("jobs.cleanup")

def process_interaction_telemetry(db: Session):
    """
    Sweeps logged interaction events and dynamically updates:
    1. Channel preference scores (in-network boost / demotion mapped to standard bounds)
    2. Interest Topic & Training Seed weights (semantic vector tuning loop with passive decay)
    """
    logger.info("Processing recent telemetry events to tune recommendation weights...")
    
    # Query events created in the last 24 hours, preloading video objects
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    stmt = select(Event).options(joinedload(Event.video)).where(Event.created_at >= cutoff)
    events = db.scalars(stmt).all()
    
    interests = db.scalars(select(Interest)).all()

    # Dynamic Channel Preference updates
    channels_boost = {}
    
    # 1. Active Vector Weight Tuning: Semantic reinforcement learning loop
    if events:
        interest_weight_changes = {interest.id: 0.0 for interest in interests}
        
        for event in events:
            video = event.video
            if not video:
                continue
                
            # A. Channel preference tuning based on standard interaction delta tuning
            c_id = video.channel_id
            if c_id:
                if c_id not in channels_boost:
                    channels_boost[c_id] = 0.0
                
                delta_c = 0.0
                if event.event_type == "impression":
                    delta_c = 0.0
                elif event.event_type == "click":
                    delta_c = 0.01
                elif event.event_type == "watch":
                    if event.watch_time_pct is not None:
                        if event.watch_time_pct >= 0.7:
                            delta_c = 0.04
                        elif event.watch_time_pct <= 0.2:
                            delta_c = -0.05
                        else:
                            delta_c = 0.02
                    else:
                        delta_c = 0.02
                elif event.event_type == "like" or event.rating == 1:
                    delta_c = 0.06
                elif event.event_type == "subscribe":
                    delta_c = 0.15
                elif event.event_type in ["dislike", "disliked"] or event.rating == -1:
                    delta_c = -0.10
                elif event.event_type in ["skip", "dismiss"]:
                    delta_c = -0.05
                
                channels_boost[c_id] += delta_c
                    
            # B. Semantic vector weight tuning (followed topics & training seeds)
            if video.embedding is not None and interests:
                v_emb = video.embedding
                for interest in interests:
                    if interest.embedding is None:
                        continue
                    
                    # Compute cosine similarity in memory (dot product of normalized vectors)
                    dot_product = sum(a * b for a, b in zip(v_emb, interest.embedding))
                    similarity = max(float(dot_product), 0.0)
                    
                    # If video is semantically related to this vector (similarity >= 0.45)
                    if similarity >= 0.45:
                        delta_w = 0.0
                        
                        if event.event_type == "like" or event.rating == 1:
                            delta_w = 0.06 * similarity
                        elif event.event_type == "subscribe":
                            delta_w = 0.15 * similarity
                        elif event.event_type == "watch":
                            watch_pct = event.watch_time_pct or 0.5
                            if watch_pct >= 0.7:
                                delta_w = 0.04 * similarity
                            elif watch_pct <= 0.2:
                                delta_w = -0.05 * similarity  # quick skip penalty
                        elif event.event_type == "queue_add":
                            delta_w = 0.02 * similarity
                        elif event.event_type in ["dislike", "disliked"] or event.rating == -1:
                            delta_w = -0.10 * similarity
                        elif event.event_type in ["skip", "dismiss"]:
                            delta_w = -0.05 * similarity
                            
                        interest_weight_changes[interest.id] += delta_w

        # Apply active interest updates to database
        for interest in interests:
            delta = interest_weight_changes.get(interest.id, 0.0)
            if delta != 0.0:
                old_w = interest.weight
                # Bound vector weights between 0.1x and 5.0x
                interest.weight = max(0.1, min(5.0, old_w + delta))
                logger.info(f"Active Telemetry Tuned curation vector '{interest.topic}' weight: {old_w:.2f}x -> {interest.weight:.2f}x (delta: {delta:+.2f})")

        # Update channel preference modifiers in database
        for c_id, delta in channels_boost.items():
            if delta == 0.0:
                continue
                
            channel = db.scalar(select(Channel).where(Channel.id == c_id))
            if channel:
                old_pref = channel.preference_score if channel.preference_score is not None else 1.0
                # Bound preference scale between 0.25x and 1.50x
                new_pref = max(0.25, min(1.50, old_pref + delta))
                channel.preference_score = new_pref
                logger.info(f"Active Telemetry Tuned channel '{channel.title}' preference weight: {old_pref:.2f}x -> {new_pref:.2f}x (delta: {delta:+.2f})")

    # 2. Passive Curation Vector Decay (forgetting factor):
    # Slowly decay all interest/seed weights by 1% towards baseline (1.0x) to ensure feed stays dynamic over time
    if interests:
        for interest in interests:
            old_w = interest.weight
            if old_w > 1.0:
                interest.weight = max(1.0, old_w * 0.99)
                logger.debug(f"Passive decay applied to vector '{interest.topic}': {old_w:.2f}x -> {interest.weight:.2f}x")
            elif old_w < 1.0:
                interest.weight = min(1.0, old_w * 1.01)
                logger.debug(f"Passive reinforcement applied to vector '{interest.topic}': {old_w:.2f}x -> {interest.weight:.2f}x")

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

def run_cleanup_and_tuning():
    """Main maintenance execution wrapper."""
    db = SessionLocal()
    try:
        # Tune preference weights from interactions
        process_interaction_telemetry(db)
        # Purge old data
        purge_expired_unseen_videos(db)
    finally:
        db.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    logger.info("Running standalone cleanup and active-learning job...")
    run_cleanup_and_tuning()
