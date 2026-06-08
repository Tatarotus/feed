import uuid
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import and_, select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Channel, Event, FeedImpression, Interest, LikedVideo, SemanticMutation, Video
from app.pipeline.ranking.candidate import CandidateRetriever
from app.pipeline.ranking.reranker import Stage2Reranker
from app.schemas import FeedItemResponse, LikedVideoResponse

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

    # --- Freshness, Impression Tracking, and Soft Exclusion Window ---
    # Query feed impressions within the last 30 days to build user interaction history
    cutoff_impressions = datetime.now(timezone.utc) - timedelta(days=30)
    impressions_stmt = (
        select(FeedImpression)
        .where(
            and_(
                FeedImpression.user_id == 1,
                FeedImpression.shown_at >= cutoff_impressions
            )
        )
        .order_by(FeedImpression.shown_at.asc())
    )
    user_impressions = db.scalars(impressions_stmt).all()

    # Group impressions by video_id
    video_imp_history = {}
    for imp in user_impressions:
        vid = imp.video_id
        if vid not in video_imp_history:
            video_imp_history[vid] = []
        video_imp_history[vid].append(imp)

    # Perform soft feed exclusion logic
    excluded_stale_video_ids = set()
    now_utc = datetime.now(timezone.utc)
    for vid, imps in video_imp_history.items():
        has_click = any(imp.clicked for imp in imps)
        if not has_click:
            imp_count = len(imps)
            last_shown = imps[-1].shown_at
            if last_shown.tzinfo is None:
                last_shown = last_shown.replace(tzinfo=timezone.utc)

            elapsed = now_utc - last_shown
            if imp_count >= 8:
                if elapsed < timedelta(days=7):
                    excluded_stale_video_ids.add(vid)
            elif imp_count >= 5:
                if elapsed < timedelta(hours=72):
                    excluded_stale_video_ids.add(vid)
            elif imp_count >= 3:
                if elapsed < timedelta(hours=24):
                    excluded_stale_video_ids.add(vid)

    # Prepare impression counts for repeat penalty
    impression_counts = {vid: len(imps) for vid, imps in video_imp_history.items()}

    # 4. Trigger Stage 1: Fast Multi-Bucket Candidate Retrieval
    retriever = CandidateRetriever(db, user_id=1, serendipity=serendipity, media_type="video")
    # Reload videos joined with their channel models to avoid N+1 query execution
    # during in-memory Stage 2 reranking
    candidates = retriever.get_all_candidates()

    # Exclude candidates that the user has already dismissed, disliked, or soft excluded
    filtered_candidates = {}
    for vid_id, cand in candidates.items():
        if vid_id not in excluded_video_ids and vid_id not in excluded_stale_video_ids:
            filtered_candidates[vid_id] = cand

    # Edge-case protection: If soft exclusion leaves us with too few candidates (< 10),
    # bypass the soft exclusion filter to prevent an empty/collapsed feed
    if len(filtered_candidates) < 10:
        filtered_candidates = {}
        for vid_id, cand in candidates.items():
            if vid_id not in excluded_video_ids:
                filtered_candidates[vid_id] = cand

    candidates = filtered_candidates

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

    # Fetch active semantic mutations
    mutations = db.scalars(
        select(SemanticMutation).where(SemanticMutation.status.in_(["experimental", "promoted"]))
    ).all()

    # 6. Trigger Stage 2: In-memory Reranking, Deduplication & Rolling Discovery Injection
    reranker = Stage2Reranker(
        user_interests=interests,
        neg_centroid=neg_centroid,
        serendipity=serendipity,
        semantic_mutations=mutations
    )
    feed = reranker.rerank_and_diversify(
        candidates=candidates,
        subscribed_channel_ids=subscribed_channel_ids,
        limit=limit,
        impression_counts=impression_counts
    )

    # Log an impression row for each candidate shown in the returned feed
    refresh_cycle_id = uuid.uuid4().hex
    for item in feed:
        video = item["video"]
        db_imp = FeedImpression(
            user_id=1,
            video_id=video.id,
            refresh_cycle_id=refresh_cycle_id,
            clicked=False,
            watch_duration=0.0
        )
        db.add(db_imp)
    db.commit()

    return feed


@router.get("/liked", response_model=List[LikedVideoResponse])
def get_liked_videos(
    sort_by: str = "newest",  # "newest", "oldest", "most_watched", "semantic_similarity"
    search: str = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """
    Fetch user's permanently liked videos library with robust sorting,
    instant search filtering, and pagination support.
    """
    stmt = select(LikedVideo).options(
        joinedload(LikedVideo.video).joinedload(Video.channel),
        joinedload(LikedVideo.channel)
    ).where(LikedVideo.user_id == 1)

    # Search filter (joins Video)
    if search:
        search_pattern = f"%{search}%"
        stmt = stmt.join(Video).where(
            Video.title.ilike(search_pattern) | Video.description.ilike(search_pattern)
        )

    # Sorting
    if sort_by == "newest":
        stmt = stmt.order_by(LikedVideo.liked_at.desc())
    elif sort_by == "oldest":
        stmt = stmt.order_by(LikedVideo.liked_at.asc())
    elif sort_by == "most_watched":
        stmt = stmt.order_by(LikedVideo.watch_duration_seconds.desc())
    elif sort_by == "semantic_similarity":
        stmt = stmt.order_by(LikedVideo.semantic_score.desc())
    else:
        stmt = stmt.order_by(LikedVideo.liked_at.desc())

    # Pagination
    stmt = stmt.limit(limit).offset(offset)

    results = db.scalars(stmt).all()
    return results


@router.get("/shorts", response_model=List[FeedItemResponse])
def get_shorts_feed(limit: int = 30, serendipity: float = 0.2, db: Session = Depends(get_db)):
    """
    Shorts Feed generation.
    Orchestrates: Stage 1 (Multi-Bucket Retrieval) + Stage 2 (Diversity Reranking) for Shorts.
    """
    interests = db.scalars(
        select(Interest).where(Interest.user_id == 1)
    ).all()

    if not interests:
        fallback_videos = db.scalars(
            select(Video)
            .options(joinedload(Video.channel))
            .where(
                and_(
                    Video.processing_status == "embedded",
                    Video.url.like("%/shorts/%")
                )
            )
            .order_by(Video.publish_date.desc())
            .limit(limit)
        ).all()

        fallback_feed = []
        for v in fallback_videos:
            fallback_feed.append({
                "video": v,
                "score": 50.0,
                "badge": "Onboarding Seed",
                "breakdown": {
                    "trusted_boost": 0.0,
                    "preference_boost": 0.0,
                    "subscription_boost": 0.0,
                    "semantic_affinity": 0.0,
                    "clickbait_penalty": 0.0,
                    "negative_demotion": 0.0,
                    "freshness_decay": 50.0,
                    "repeat_penalty": 0.0
                },
                "best_topic": "General Ingestion",
                "is_discovery": False,
                "sources": ["chronological_fallback"]
            })
        return fallback_feed

    channels = db.scalars(select(Channel).where(Channel.is_subscribed == True)).all()
    subscribed_channel_ids = {c.id for c in channels}

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

    # Query feed impressions within the last 30 days
    cutoff_impressions = datetime.now(timezone.utc) - timedelta(days=30)
    impressions_stmt = (
        select(FeedImpression)
        .where(
            and_(
                FeedImpression.user_id == 1,
                FeedImpression.shown_at >= cutoff_impressions
            )
        )
        .order_by(FeedImpression.shown_at.asc())
    )
    user_impressions = db.scalars(impressions_stmt).all()

    video_imp_history = {}
    for imp in user_impressions:
        vid = imp.video_id
        if vid not in video_imp_history:
            video_imp_history[vid] = []
        video_imp_history[vid].append(imp)

    excluded_stale_video_ids = set()
    now_utc = datetime.now(timezone.utc)
    for vid, imps in video_imp_history.items():
        has_click = any(imp.clicked for imp in imps)
        if not has_click:
            imp_count = len(imps)
            last_shown = imps[-1].shown_at
            if last_shown.tzinfo is None:
                last_shown = last_shown.replace(tzinfo=timezone.utc)

            elapsed = now_utc - last_shown
            if imp_count >= 8:
                if elapsed < timedelta(days=7):
                    excluded_stale_video_ids.add(vid)
            elif imp_count >= 5:
                if elapsed < timedelta(hours=72):
                    excluded_stale_video_ids.add(vid)
            elif imp_count >= 3:
                if elapsed < timedelta(hours=24):
                    excluded_stale_video_ids.add(vid)

    impression_counts = {vid: len(imps) for vid, imps in video_imp_history.items()}

    retriever = CandidateRetriever(db, user_id=1, serendipity=serendipity, media_type="shorts")
    candidates = retriever.get_all_candidates()

    filtered_candidates = {}
    for vid_id, cand in candidates.items():
        if vid_id not in excluded_video_ids and vid_id not in excluded_stale_video_ids:
            filtered_candidates[vid_id] = cand

    if len(filtered_candidates) < 10:
        filtered_candidates = {}
        for vid_id, cand in candidates.items():
            if vid_id not in excluded_video_ids:
                filtered_candidates[vid_id] = cand

    candidates = filtered_candidates

    if not candidates:
        return []

    # Fetch recent negative event vectors
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

    neg_centroid = None
    if neg_embeddings:
        dim = len(neg_embeddings[0])
        neg_centroid = [0.0] * dim
        for emb in neg_embeddings:
            for i in range(dim):
                neg_centroid[i] += emb[i]
        for i in range(dim):
            neg_centroid[i] /= len(neg_embeddings)

    mutations = db.scalars(
        select(SemanticMutation).where(SemanticMutation.status.in_(["experimental", "promoted"]))
    ).all()

    reranker = Stage2Reranker(
        user_interests=interests,
        neg_centroid=neg_centroid,
        serendipity=serendipity,
        semantic_mutations=mutations
    )
    feed = reranker.rerank_and_diversify(
        candidates=candidates,
        subscribed_channel_ids=subscribed_channel_ids,
        limit=limit,
        impression_counts=impression_counts
    )

    refresh_cycle_id = uuid.uuid4().hex
    for item in feed:
        video = item["video"]
        db_imp = FeedImpression(
            user_id=1,
            video_id=video.id,
            refresh_cycle_id=refresh_cycle_id,
            clicked=False,
            watch_duration=0.0
        )
        db.add(db_imp)
    db.commit()

    return feed

