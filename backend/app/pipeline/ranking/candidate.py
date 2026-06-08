import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models import Channel, Interest, LikedVideo, QueueItem, SemanticMutation, Video

logger = logging.getLogger("pipeline.ranking.candidate")

class CandidateRetriever:
    def __init__(self, db: Session, user_id: int = 1, serendipity: float = 0.2, media_type: str = "video"):
        self.db = db
        self.user_id = user_id
        self.serendipity = serendipity
        self.media_type = media_type

    def _apply_media_filter(self, stmt):
        if self.media_type == "video":
            return stmt.where(Video.url.notlike("%/shorts/%"))
        elif self.media_type == "shorts":
            return stmt.where(Video.url.like("%/shorts/%"))
        return stmt

    def retrieve_recency_bucket(self, limit: int = 80) -> List[Tuple[Video, float, str]]:
        """
        Bucket 1 (40% - ~80 items): Fresh videos published by trusted/subscribed channels.
        Prioritizes subscribed channels over standard trusted channels, ordered by publish date.
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=14)
        stmt = (
            select(Video)
            .join(Channel, Video.channel_id == Channel.id)
            .where(
                and_(
                    Channel.is_trusted,
                    Video.publish_date >= cutoff_date
                )
            )
            .order_by(Channel.is_subscribed.desc(), Video.publish_date.desc())
            .limit(limit)
        )
        stmt = self._apply_media_filter(stmt)
        videos = self.db.scalars(stmt).all()
        return [(v, 0.0, "trusted_recency") for v in videos]

    def retrieve_semantic_bucket(self, limit: int = 60) -> List[Tuple[Video, float, str]]:
        """
        Bucket 2 (30% - ~60 items): Videos closest in cosine distance
        to any of the user's explicit followed interest vectors.
        Calculates pgvector cosine similarity directly in SQL.
        """
        interests = self.db.scalars(
            select(Interest).where(Interest.user_id == self.user_id)
        ).all()

        if not interests:
            return []

        candidates = []
        total_weight = sum(max(i.weight, 0.1) for i in interests)

        for interest in interests:
            # Allocate candidates proportionally to interest weight
            limit_per_interest = max(int((max(interest.weight, 0.1) / total_weight) * limit), 5)
            # SQL similarity calculation: 1 - cosine_distance
            similarity_col = (1 - Video.embedding.cosine_distance(interest.embedding)).label("similarity")
            stmt = (
                select(Video, similarity_col)
                .where(Video.processing_status == "embedded")
                .order_by(Video.embedding.cosine_distance(interest.embedding))
                .limit(limit_per_interest)
            )
            stmt = self._apply_media_filter(stmt)

            rows = self.db.execute(stmt).all()
            for video, similarity in rows:
                # Ensure similarity is not negative or NaN
                raw_sim = max(float(similarity), 0.0) if similarity is not None else 0.0
                # Apply interest weight multiplier so higher-weighted interests boost scores
                weighted_sim = raw_sim * max(interest.weight, 0.1)
                candidates.append((video, weighted_sim, f"semantic_affinity ({interest.topic})"))

        return candidates[:limit]

    def retrieve_queue_adjacent_bucket(self, limit: int = 30) -> List[Tuple[Video, float, str]]:
        """
        Bucket 3 (15% - ~30 items): Videos semantically adjacent to the
        user's uncompleted Queue Items.
        Calculates similarity directly in SQL.
        """
        # Fetch active queue items joined with their videos
        active_items = self.db.scalars(
            select(Video)
            .join(QueueItem, Video.id == QueueItem.video_id)
            .where(
                and_(
                    QueueItem.user_id == self.user_id,
                    not QueueItem.is_completed
                )
            )
            .limit(5)
        ).all()

        if not active_items:
            return []

        candidates = []
        limit_per_item = max(int(limit / len(active_items)), 5)

        for q_video in active_items:
            if q_video.embedding is None:
                continue

            similarity_col = (1 - Video.embedding.cosine_distance(q_video.embedding)).label("similarity")
            stmt = (
                select(Video, similarity_col)
                .where(
                    and_(
                        Video.id != q_video.id,
                        Video.processing_status == "embedded",
                        1 - Video.embedding.cosine_distance(q_video.embedding) >= 0.35
                    )
                )
                .order_by(Video.embedding.cosine_distance(q_video.embedding))
                .limit(limit_per_item)
            )
            stmt = self._apply_media_filter(stmt)

            rows = self.db.execute(stmt).all()
            for video, similarity in rows:
                sim_score = max(float(similarity), 0.0) if similarity is not None else 0.0
                candidates.append((video, sim_score, "queue_adjacent"))

        return candidates[:limit]

    def retrieve_rediscovery_bucket(self, limit: int = 20) -> List[Tuple[Video, float, str]]:
        """
        Bucket 4 (10% - ~20 items): Rediscovering old saved/completed videos.
        No immediate semantic calculation, defaults to 0.0.
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)
        stmt = (
            select(Video)
            .join(QueueItem, Video.id == QueueItem.video_id)
            .where(
                and_(
                    QueueItem.user_id == self.user_id,
                    QueueItem.is_completed,
                    QueueItem.consumed_at <= cutoff_date
                )
            )
            .order_by(func.random())
            .limit(limit)
        )
        stmt = self._apply_media_filter(stmt)
        videos = self.db.scalars(stmt).all()
        return [(v, 0.0, "rediscovery") for v in videos]

    def retrieve_exploration_bucket(self, limit: int = 10) -> List[Tuple[Video, float, str]]:
        """
        Bucket 5: Random exploration seeds.
        """
        if limit <= 0:
            return []
        stmt = (
            select(Video)
            .where(Video.processing_status == "embedded")
            .order_by(func.random())
            .limit(limit)
        )
        stmt = self._apply_media_filter(stmt)
        videos = self.db.scalars(stmt).all()
        return [(v, 0.0, "exploration_seed") for v in videos]

    def retrieve_adjacent_bucket(self, limit: int = 30) -> List[Tuple[Video, float, str]]:
        """
        Bucket 6: Adjacent interest domains.
        Retrieves videos that are moderately similar (cosine similarity between 0.35 and 0.65)
        to the user's interests, representing adjacent domains.
        """
        if limit <= 0:
            return []
        interests = self.db.scalars(
            select(Interest).where(Interest.user_id == self.user_id)
        ).all()

        if not interests:
            return []

        candidates = []
        limit_per_interest = max(int(limit / len(interests)), 5)

        for interest in interests:
            # SQL cosine similarity calculation: 1 - cosine_distance
            similarity_col = (1 - Video.embedding.cosine_distance(interest.embedding)).label("similarity")
            stmt = (
                select(Video, similarity_col)
                .where(
                    and_(
                        Video.processing_status == "embedded",
                        1 - Video.embedding.cosine_distance(interest.embedding) >= 0.35,
                        1 - Video.embedding.cosine_distance(interest.embedding) <= 0.65
                    )
                )
                .order_by(Video.embedding.cosine_distance(interest.embedding).desc())
                .limit(limit_per_interest)
            )
            stmt = self._apply_media_filter(stmt)

            rows = self.db.execute(stmt).all()
            for video, similarity in rows:
                sim_score = max(float(similarity), 0.0) if similarity is not None else 0.0
                candidates.append((video, sim_score, f"adjacent_domain ({interest.topic})"))

        return candidates[:limit]

    def retrieve_liked_adjacent_bucket(self, limit: int = 30) -> List[Tuple[Video, float, str]]:
        """
        Retrieves videos semantically adjacent to the user's Liked Videos.
        Uses liked videos as long-term semantic anchors and vector affinity seeds.
        """
        # Fetch up to 5 most recent liked videos
        liked_items = self.db.scalars(
            select(Video)
            .join(LikedVideo, Video.id == LikedVideo.video_id)
            .where(LikedVideo.user_id == self.user_id)
            .order_by(LikedVideo.liked_at.desc())
            .limit(5)
        ).all()

        if not liked_items:
            return []

        candidates = []
        limit_per_item = max(int(limit / len(liked_items)), 5)

        for l_video in liked_items:
            if l_video.embedding is None:
                continue

            similarity_col = (1 - Video.embedding.cosine_distance(l_video.embedding)).label("similarity")
            stmt = (
                select(Video, similarity_col)
                .where(
                    and_(
                        Video.id != l_video.id,
                        Video.processing_status == "embedded",
                        1 - Video.embedding.cosine_distance(l_video.embedding) >= 0.35
                    )
                )
                .order_by(Video.embedding.cosine_distance(l_video.embedding))
                .limit(limit_per_item)
            )
            stmt = self._apply_media_filter(stmt)

            rows = self.db.execute(stmt).all()
            for video, similarity in rows:
                sim_score = max(float(similarity), 0.0) if similarity is not None else 0.0
                candidates.append((video, sim_score, "liked_adjacent"))

        return candidates[:limit]

    def retrieve_mutation_bucket(self, limit: int = 30) -> List[Tuple[Video, float, str]]:
        """
        Bucket 8: Semantically mutated adjacent interests.
        Retrieves videos closest to active experimental or promoted mutations.
        Controls injection pressure dynamically using the Serendipity Dial.
        """
        if limit <= 0:
            return []

        # Determine mutation injection pressure based on serendipity level
        if self.serendipity <= 0.05:
            # Conservative (5%): Only highly validated promoted mutations
            stmt_mut = select(SemanticMutation).where(SemanticMutation.status == "promoted")
        elif self.serendipity <= 0.20:
            # Balanced (20%): Promoted/Safe mutations + low experimental exposure (confidence >= 0.10 to allow fresh mutations)
            stmt_mut = select(SemanticMutation).where(
                and_(
                    SemanticMutation.status.in_(["experimental", "promoted"]),
                    (SemanticMutation.status == "promoted") | (SemanticMutation.confidence_score >= 0.10)
                )
            )
        elif self.serendipity <= 0.40:
            # Discovery (40%): Increased mutation diversity (confidence >= 0.06 to allow moderate decayed exposure)
            stmt_mut = select(SemanticMutation).where(
                and_(
                    SemanticMutation.status.in_(["experimental", "promoted"]),
                    (SemanticMutation.status == "promoted") | (SemanticMutation.confidence_score >= 0.06)
                )
            )
        else:
            # Serendipitous (60%): Higher experimental mutation exploration (all active mutations)
            stmt_mut = select(SemanticMutation).where(
                SemanticMutation.status.in_(["experimental", "promoted"])
            )

        mutations = self.db.scalars(stmt_mut).all()

        if not mutations:
            return []

        candidates = []

        # Calculate effective visibility for each mutation organism
        mutation_visibilities = {}
        for m in mutations:
            energy_val = getattr(m, "energy", 1.0) or 1.0
            telemetry_health = max(0.1, 1.0 + (getattr(m, "telemetry_score", 0.0) or 0.0))
            fatigue_val = getattr(m, "fatigue_multiplier", 1.0) or 1.0
            effective_vis = m.confidence_score * energy_val * telemetry_health * fatigue_val
            mutation_visibilities[m.id] = max(0.05, effective_vis)

        total_visibility = sum(mutation_visibilities.values())

        for m in mutations:
            m_vis = mutation_visibilities[m.id]
            limit_per_mutation = max(int((m_vis / total_visibility) * limit), 5)
            similarity_col = (1 - Video.embedding.cosine_distance(m.mutation_embedding)).label("similarity")
            stmt = (
                select(Video, similarity_col)
                .where(Video.processing_status == "embedded")
                .order_by(Video.embedding.cosine_distance(m.mutation_embedding))
                .limit(limit_per_mutation)
            )
            stmt = self._apply_media_filter(stmt)

            rows = self.db.execute(stmt).all()
            for video, similarity in rows:
                raw_sim = max(float(similarity), 0.0) if similarity is not None else 0.0
                weighted_sim = raw_sim * m_vis
                candidates.append((video, weighted_sim, f"semantic_mutation ({m.mutation_topic})"))

        return candidates[:limit]

    def get_all_candidates(self) -> Dict[str, Dict[str, Any]]:
        """
        Executes multi-bucket retrieval and returns consolidated candidate dictionary
        with pre-computed pgvector similarity metrics.
        """
        logger.debug(f"Executing Stage 1 SQL-based Candidate Retrieval sweep with serendipity={self.serendipity}...")

        # Calculate dynamic limits based on serendipity level (with both mutations and legacy exploration/adjacent buckets active)
        if self.serendipity <= 0.05:
            recency_limit = 100
            semantic_limit = 80
            queue_limit = 40
            rediscovery_limit = 30
            exploration_limit = 15
            adjacent_limit = 15
            liked_limit = 20
            mutation_limit = 20
        elif self.serendipity <= 0.20:
            recency_limit = 80
            semantic_limit = 70
            queue_limit = 35
            rediscovery_limit = 30
            exploration_limit = 40
            adjacent_limit = 40
            liked_limit = 25
            mutation_limit = 60
        elif self.serendipity <= 0.40:
            recency_limit = 60
            semantic_limit = 60
            queue_limit = 30
            rediscovery_limit = 25
            exploration_limit = 70
            adjacent_limit = 70
            liked_limit = 30
            mutation_limit = 90
        else:
            recency_limit = 40
            semantic_limit = 50
            queue_limit = 20
            rediscovery_limit = 20
            exploration_limit = 100
            adjacent_limit = 100
            liked_limit = 30
            mutation_limit = 150

        # Query buckets sequentially with dynamic limits
        recency = self.retrieve_recency_bucket(limit=recency_limit)
        semantic = self.retrieve_semantic_bucket(limit=semantic_limit)
        queue = self.retrieve_queue_adjacent_bucket(limit=queue_limit)
        rediscovery = self.retrieve_rediscovery_bucket(limit=rediscovery_limit)
        exploration = self.retrieve_exploration_bucket(limit=exploration_limit)
        adjacent = self.retrieve_adjacent_bucket(limit=adjacent_limit)
        liked_adjacent = self.retrieve_liked_adjacent_bucket(limit=liked_limit)
        mutation = self.retrieve_mutation_bucket(limit=mutation_limit)

        consolidated: Dict[str, Dict[str, Any]] = {}

        # Merge buckets to eliminate duplicates while aggregating retrieval justifications
        for items in [recency, semantic, queue, rediscovery, exploration, adjacent, liked_adjacent, mutation]:
            for video, similarity, source_name in items:
                if video.id not in consolidated:
                    consolidated[video.id] = {
                        "video": video,
                        "semantic_similarity": similarity,
                        "sources": {source_name}
                    }
                else:
                    consolidated[video.id]["sources"].add(source_name)
                    # Retain the maximum similarity calculated
                    consolidated[video.id]["semantic_similarity"] = max(
                        consolidated[video.id]["semantic_similarity"],
                        similarity
                    )

        logger.info(f"Stage 1 complete. Retrieved {len(consolidated)} unique candidates with pre-computed similarities.")
        return consolidated

