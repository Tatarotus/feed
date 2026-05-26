from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, and_
from typing import List

from app.database import get_db
from app.models import Interest, Channel, Video, Event
from app.schemas import FeedItemResponse
from app.pipeline.ranking.candidate import CandidateRetriever
from app.pipeline.ranking.reranker import Stage2Reranker

router = APIRouter(prefix="/feed", tags=["Feed"])

@router.get("", response_model=List[FeedItemResponse])
def get_recommendation_feed(limit: int = 30, serendipity: float = 0.2, db: Session = Depends(get_db)):
    """
    Core Recommendation Feed generation.
    Orchestrates: Stage 1 (Multi-Bucket Retrieval) + Stage 2 (Diversity Reranking).
    """
    # 1. Fetch active followed interests (Topic Vector seeds)
    interests = db.scalars(
        select(Interest).where(Interest.user_id == 1)
    ).all()
    
    # 2. Cold Start Guard: If no interests or channels registered, 
    # return simple fallback chronological feed of all processed items to avoid a blank screen
    if not interests:
        logger_fallback = select(Video).options(joinedload(Video.channel)).where(Video.processing_status == "embedded").order_by(Video.publish_date.desc()).limit(limit)
        fallback_videos = db.scalars(logger_fallback).all()
        
        fallback_feed = []
        for v in fallback_videos:
            # Clean fallback representation
            fallback_feed.append({
                "video": v,
                "score": 50.0,
                "badge": "Onboarding Seed",
                "breakdown": {
                    "trusted_boost": 0.0,
                    "preference_boost": 0.0,
                    "semantic_affinity": 0.0,
                    "clickbait_penalty": 0.0,
                    "negative_demotion": 0.0,
                    "freshness_decay": 50.0
                },
                "best_topic": "General Ingestion",
                "is_discovery": False,
                "sources": ["chronological_fallback"]
            })
        return fallback_feed

    # 3. Retrieve subscribed channels to identify in-network vs. out-of-network (discovery)
    channels = db.scalars(select(Channel).where(Channel.is_subscribed == True)).all()
    subscribed_channel_ids = {c.id for c in channels}

    # Fetch all video IDs that the user has already disliked or dismissed
    excluded_stmt = (
        select(Event.video_id)
        .where(
            and_(
                Event.user_id == 1,
                Event.event_type.in_(["dislike", "dismiss"])
            )
        )
    )
    excluded_video_ids = set(db.scalars(excluded_stmt).all())

    # 4. Trigger Stage 1: Fast Multi-Bucket Candidate Retrieval
    retriever = CandidateRetriever(db, user_id=1, serendipity=serendipity)
    # Reload videos joined with their channel models to avoid N+1 query execution
    # during in-memory Stage 2 reranking
    candidates = retriever.get_all_candidates()

    # Exclude candidates that the user has already dismissed or disliked
    for vid_id in list(candidates.keys()):
        if vid_id in excluded_video_ids:
            del candidates[vid_id]
    
    if not candidates:
        return []

    # Ensure channels are pre-fetched on candidates to optimize memory runs
    for vid_id in list(candidates.keys()):
        # Quick relationship binding check
        video = candidates[vid_id]["video"]
        if not video.channel:
            # Bind manually if needed (SQLAlchemy usually pre-caches)
            pass

    # 5. Fetch recent negative event vectors (last 10 dislikes or dismisses)
    negative_events_stmt = (
        select(Video.embedding)
        .join(Event, Video.id == Event.video_id)
        .where(
            and_(
                Event.user_id == 1,
                Event.event_type.in_(["dislike", "dismiss"]),
                Video.embedding != None
            )
        )
        .order_by(Event.created_at.desc())
        .limit(10)
    )
    neg_embeddings = db.scalars(negative_events_stmt).all()
    
    # Compute negative centroid vector in Python
    neg_centroid = None
    if neg_embeddings:
        dim = len(neg_embeddings[0])
        neg_centroid = [0.0] * dim
        for emb in neg_embeddings:
            for i in range(dim):
                neg_centroid[i] += emb[i]
        for i in range(dim):
            neg_centroid[i] /= len(neg_embeddings)

    # 6. Trigger Stage 2: In-memory Reranking, Deduplication & Rolling Discovery Injection
    reranker = Stage2Reranker(
        user_interests=interests, 
        neg_centroid=neg_centroid, 
        serendipity=serendipity
    )
    feed = reranker.rerank_and_diversify(
        candidates=candidates,
        subscribed_channel_ids=subscribed_channel_ids,
        limit=limit
    )

    return feed
