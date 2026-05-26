import logging
from typing import List, Dict, Any, Set, Tuple
from datetime import datetime, timezone
import math

from app.models import Video, Channel, Interest
from app.config import settings

logger = logging.getLogger("pipeline.ranking.reranker")

class Stage2Reranker:
    def __init__(
        self,
        user_interests: List[Interest],
        w_trust: float = 25.0,
        w_pref: float = 15.0,
        w_semantic: float = 45.0,
        w_clickbait: float = 30.0,
        decay_alpha: float = 10.0,
        decay_beta: float = 2.0,
        neg_centroid: List[float] = None,
        serendipity: float = 0.2
    ):
        self.user_interests = user_interests
        self.w_trust = w_trust
        self.w_pref = w_pref
        self.w_semantic = w_semantic
        self.w_clickbait = w_clickbait
        self.decay_alpha = decay_alpha
        self.decay_beta = decay_beta
        self.neg_centroid = neg_centroid
        self.serendipity = serendipity

    def calculate_freshness_decay(self, publish_date: datetime) -> float:
        """
        Calculate standard gravity time decay: alpha / (dt_hours + beta).
        """
        now = datetime.now(timezone.utc)
        if publish_date.tzinfo is None:
            publish_date = publish_date.replace(tzinfo=timezone.utc)
            
        dt = now - publish_date
        dt_hours = max(dt.total_seconds() / 3600.0, 0.0)
        
        return self.decay_alpha / (dt_hours + self.decay_beta)

    def calculate_semantic_similarity(self, video: Video) -> Tuple[float, str]:
        """
        Python Fallback: Calculates cosine similarity in memory.
        Only executed during debug / explain single-item requests.
        """
        if video.embedding is None or not self.user_interests:
            return 0.0, "None"

        max_sim = 0.0
        best_topic = "None"
        v_vec = video.embedding

        for interest in self.user_interests:
            if interest.embedding is None:
                continue
            
            i_vec = interest.embedding
            # sentence-transformers & external APIs return normalized vectors,
            # so dot product is mathematically equal to cosine similarity
            dot_product = sum(a * b for a, b in zip(v_vec, i_vec))
            # Apply interest weight so a 3.0x interest boosts similarity 3x
            weighted_sim = dot_product * max(interest.weight, 0.1)
            
            if weighted_sim > max_sim:
                max_sim = weighted_sim
                best_topic = interest.topic

        return max_sim, best_topic

    def score_video(
        self, 
        video: Video, 
        channel: Channel, 
        s_sem: float = None, 
        best_topic: str = None
    ) -> Dict[str, Any]:
        """
        Evaluates a single video candidate based on linear scoring,
        using pre-calculated SQL vector similarity values. Falls back to in-memory 
        calculations if s_sem is None (e.g. debug inspectors).
        """
        # 1. Trusted Score (0.0 to 1.0)
        trust_val = 1.0 if (channel and channel.is_trusted) else 0.0
        quality_score = channel.quality_score if channel else 1.0
        s_trust = trust_val * quality_score
        
        # 2. Preference Score (default 1.0)
        s_pref = channel.preference_score if channel else 1.0
        
        # 3. Semantic Similarity Score (Fallback to in-memory if None)
        if s_sem is None:
            s_sem, best_topic = self.calculate_semantic_similarity(video)
        
        # 4. Clickbait Score (0.0 to 1.0)
        s_click = video.clickbait_score
        
        # 4.5. Negative Feedback Curation Demotion (if neg_centroid exists)
        s_neg = 0.0
        if self.neg_centroid is not None and video.embedding is not None:
            # Cosine similarity is simple dot product as embeddings are normalized
            dot_prod = sum(a * b for a, b in zip(video.embedding, self.neg_centroid))
            s_neg = max(float(dot_prod), 0.0)
        
        # 5. Freshness Decay
        s_fresh = self.calculate_freshness_decay(video.publish_date)

        # Run linear scoring calculation
        score = (
            (self.w_trust * s_trust) + 
            (self.w_pref * s_pref) + 
            (self.w_semantic * s_sem) - 
            (self.w_clickbait * s_click) -
            (25.0 * s_neg) +  # Negative vector demotion weight
            s_fresh
        )
        
        final_score = max(score, 0.0)

        # Generate qualitative soft label badge
        if final_score >= 65.0:
            soft_badge = "High Affinity"
        elif final_score >= 45.0:
            soft_badge = "High Signal"
        elif final_score >= 25.0:
            soft_badge = "Discovery Seed"
        else:
            soft_badge = "Topic Exploration"

        return {
            "score": final_score,
            "badge": soft_badge,
            "breakdown": {
                "trusted_boost": round(self.w_trust * s_trust, 2),
                "preference_boost": round(self.w_pref * s_pref, 2),
                "semantic_affinity": round(self.w_semantic * s_sem, 2),
                "clickbait_penalty": round(self.w_clickbait * s_click, 2),
                "negative_demotion": round(25.0 * s_neg, 2),
                "freshness_decay": round(s_fresh, 2)
            },
            "best_topic": best_topic
        }

    def rerank_and_diversify(
        self,
        candidates: Dict[str, Dict[str, Any]],
        subscribed_channel_ids: Set[str],
        limit: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Stage 2 entry: Scores candidates, suppresses duplicate titles, 
        dampens channel monopolization, and balances rolling discovery.
        """
        scored_candidates: List[Dict[str, Any]] = []

        # 1. First Pass: Score candidate items using pre-computed similarities
        for video_id, data in candidates.items():
            video = data["video"]
            channel = video.channel
            
            # Read pre-computed SQL similarity directly
            s_sem = data["semantic_similarity"]
            
            # Extract topic matched from retrieval justifications
            best_topic = "None"
            for src in data["sources"]:
                if "semantic_affinity" in src:
                    try:
                        best_topic = src.split("(")[-1].split(")")[0]
                    except Exception:
                        pass
            
            eval_data = self.score_video(video, channel, s_sem=s_sem, best_topic=best_topic)
            is_discovery = (not channel.is_subscribed) if (channel and hasattr(channel, "is_subscribed")) else (channel.id not in subscribed_channel_ids if channel else True)
            
            scored_candidates.append({
                "video": video,
                "score": eval_data["score"],
                "badge": eval_data["badge"],
                "breakdown": eval_data["breakdown"],
                "best_topic": eval_data["best_topic"],
                "sources": list(data["sources"]),
                "is_discovery": is_discovery
            })

        # Sort candidates descending by raw score
        scored_candidates.sort(key=lambda x: x["score"], reverse=True)

        final_feed: List[Dict[str, Any]] = []
        seen_titles = set()
        channel_counts = {}

        # 2. Second Pass: Apply Title Deduplication & Channel Diversity Dampening
        for item in scored_candidates:
            video = item["video"]
            channel_id = video.channel_id
            
            # Simple Title Deduplication check (normalized comparisons)
            norm_title = "".join(c for c in video.title.lower() if c.isalnum())
            if norm_title in seen_titles:
                continue
            
            # Channel Diversity check: dampen multiple items from same channel
            c_count = channel_counts.get(channel_id, 0)
            if c_count > 0:
                penalty = 0.5 ** c_count
                item["score"] = item["score"] * penalty
                
                # Recalculate soft badge after penalty
                if item["score"] >= 65.0:
                    item["badge"] = "High Affinity"
                elif item["score"] >= 45.0:
                    item["badge"] = "High Signal"
                elif item["score"] >= 25.0:
                    item["badge"] = "Discovery Seed"
                else:
                    item["badge"] = "Topic Exploration"

            seen_titles.add(norm_title)
            channel_counts[channel_id] = c_count + 1
            final_feed.append(item)

        # Sort again after applying diversity penalty modifiers
        final_feed.sort(key=lambda x: x["score"], reverse=True)

        # 3. Third Pass: Balance rolling discovery window targeting serendipity level using cumulative ratio interleave
        diversified_feed: List[Dict[str, Any]] = []
        
        discovery_pool = [x for x in final_feed if x["is_discovery"]]
        network_pool = [x for x in final_feed if not x["is_discovery"]]

        n_idx = 0
        d_idx = 0
        d_count = 0
        
        target_d_ratio = self.serendipity
        
        while len(diversified_feed) < limit and (n_idx < len(network_pool) or d_idx < len(discovery_pool)):
            total_len = len(diversified_feed)
            
            # Decide whether we want a discovery item to satisfy the cumulative target ratio
            want_discovery = False
            if target_d_ratio > 0:
                if total_len == 0:
                    want_discovery = False  # Start with high-affinity network content
                else:
                    current_ratio = d_count / total_len
                    want_discovery = current_ratio < target_d_ratio
            
            if want_discovery and d_idx < len(discovery_pool):
                diversified_feed.append(discovery_pool[d_idx])
                d_idx += 1
                d_count += 1
            elif n_idx < len(network_pool):
                diversified_feed.append(network_pool[n_idx])
                n_idx += 1
            elif d_idx < len(discovery_pool):
                # Fallback if we want network content but pool is exhausted
                diversified_feed.append(discovery_pool[d_idx])
                d_idx += 1
                d_count += 1
            else:
                break

        return diversified_feed[:limit]
