import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Set, Tuple

from app.models import Channel, Interest, Video

logger = logging.getLogger("pipeline.ranking.reranker")

class Stage2Reranker:
    def __init__(
        self,
        user_interests: List[Interest],
        w_sub: float = 20.0,      # Subscription affinity weight
        w_trust: float = 25.0,
        w_pref: float = 15.0,
        w_semantic: float = 45.0,
        w_clickbait: float = 30.0,
        decay_alpha: float = 10.0,
        decay_beta: float = 2.0,
        neg_centroid: List[float] = None,
        serendipity: float = 0.2,
        semantic_mutations: List[Any] = None
    ):
        self.user_interests = user_interests
        self.w_sub = w_sub
        self.w_trust = w_trust
        self.w_pref = w_pref
        self.w_semantic = w_semantic
        self.w_clickbait = w_clickbait
        self.decay_alpha = decay_alpha
        self.decay_beta = decay_beta
        self.neg_centroid = neg_centroid
        self.serendipity = serendipity
        self.semantic_mutations = semantic_mutations

    def calculate_freshness_decay(self, publish_date: datetime) -> float:
        """
        Calculate aggressive exponential freshness decay: exp(-age_hours / half_life).
        """
        now = datetime.now(timezone.utc)
        if publish_date.tzinfo is None:
            publish_date = publish_date.replace(tzinfo=timezone.utc)

        dt = now - publish_date
        age_hours = max(dt.total_seconds() / 3600.0, 0.0)

        if age_hours < 24.0:
            return 1.0
        else:
            # Using half-life of 144 hours (6 days) for aggressive decay on older content
            half_life = 144.0
            return math.exp(-(age_hours - 24.0) / half_life)

    def calculate_semantic_similarity(self, video: Video) -> Tuple[float, str]:
        """
        Python Fallback: Calculates cosine similarity in memory.
        Only executed during debug / explain single-item requests.
        """
        if video.embedding is None:
            return 0.0, "None"

        max_sim = 0.0
        best_topic = "None"
        v_vec = video.embedding

        if self.user_interests:
            for interest in self.user_interests:
                if interest.embedding is None:
                    continue

                i_vec = interest.embedding
                dot_product = sum(a * b for a, b in zip(v_vec, i_vec))
                weighted_sim = dot_product * max(0.25, min(1.50, interest.weight))

                if weighted_sim > max_sim:
                    max_sim = weighted_sim
                    best_topic = interest.topic

        if self.semantic_mutations:
            for m in self.semantic_mutations:
                if m.mutation_embedding is None:
                    continue
                m_vec = m.mutation_embedding
                dot_product = sum(a * b for a, b in zip(v_vec, m_vec))

                # Semantic Energy Economy visibility formula
                energy_val = getattr(m, "energy", 1.0) or 1.0
                telemetry_health = max(0.1, 1.0 + (getattr(m, "telemetry_score", 0.0) or 0.0))
                fatigue_val = getattr(m, "fatigue_multiplier", 1.0) or 1.0
                effective_visibility = m.confidence_score * energy_val * telemetry_health * fatigue_val

                weighted_sim = dot_product * max(0.05, effective_visibility)

                if weighted_sim > max_sim:
                    max_sim = weighted_sim
                    best_topic = m.mutation_topic

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

        # 2. Preference Score (default 1.0, dynamically capped between 0.25 and 1.50)
        s_pref = channel.preference_score if channel else 1.0
        if s_pref is not None:
            s_pref = max(0.25, min(1.50, s_pref))
        else:
            s_pref = 1.0

        # 2.5 Subscription Affinity Score (1.0 if channel is subscribed, 0.0 otherwise)
        s_sub = 1.0 if (channel and getattr(channel, "is_subscribed", False)) else 0.0

        # 3. Semantic Similarity Score (Fallback to in-memory if None)
        if s_sem is None:
            s_sem, best_topic = self.calculate_semantic_similarity(video)

        # 4. Clickbait Score (0.0 to 1.0)
        s_click = video.clickbait_score

        # 4.5. Negative Feedback Curation Demotion (if neg_centroid exists)
        s_neg = 0.0
        if self.neg_centroid is not None and video.embedding is not None:
            dot_prod = sum(a * b for a, b in zip(video.embedding, self.neg_centroid))
            s_neg = max(float(dot_prod), 0.0)

        # 5. Freshness Decay
        s_fresh = self.calculate_freshness_decay(video.publish_date)

        # Run linear scoring calculation
        score = (
            (self.w_trust * s_trust) +
            (self.w_pref * s_pref) +
            (self.w_sub * s_sub) +
            (self.w_semantic * s_sem) -
            (self.w_clickbait * s_click) -
            (25.0 * s_neg)
        )

        # Multiply score by freshness decay factor
        final_score = max(score, 0.0) * s_fresh

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
                "subscription_boost": round(self.w_sub * s_sub, 2),
                "semantic_affinity": round(self.w_semantic * s_sem, 2),
                "clickbait_penalty": round(self.w_clickbait * s_click, 2),
                "negative_demotion": round(25.0 * s_neg, 2),
                "freshness_decay": round(s_fresh, 4),
                "repeat_penalty": 0.0
            },
            "best_topic": best_topic
        }


    def _get_soft_badge(self, score: float) -> str:
        if score >= 65.0:
            return "High Affinity"
        elif score >= 45.0:
            return "High Signal"
        elif score >= 25.0:
            return "Discovery Seed"
        else:
            return "Topic Exploration"

    def _first_pass_score_candidates(
        self,
        candidates: Dict[str, Dict[str, Any]],
        subscribed_channel_ids: Set[str],
        impression_counts: Dict[str, int]
    ) -> List[Dict[str, Any]]:
        scored_candidates: List[Dict[str, Any]] = []

        for _video_id, data in candidates.items():
            video = data["video"]
            channel = video.channel
            s_sem = data["semantic_similarity"]

            best_topic = "None"
            for src in data["sources"]:
                if "semantic_affinity" in src or "semantic_mutation" in src:
                    try:
                        best_topic = src.split("(")[-1].split(")")[0]
                    except Exception:
                        pass

            eval_data = self.score_video(video, channel, s_sem=s_sem, best_topic=best_topic)
            score = eval_data["score"]
            if impression_counts and video.id in impression_counts:
                imp_count = impression_counts[video.id]
                if imp_count > 0:
                    rep_pen_factor = min(imp_count * 0.08, 0.50)
                    score_delta = score * rep_pen_factor
                    score = max(score - score_delta, 0.0)
                    eval_data["score"] = score
                    eval_data["breakdown"]["repeat_penalty"] = round(-score_delta, 2)

            eval_data["badge"] = self._get_soft_badge(score)
            is_discovery = (not channel.is_subscribed) if (channel and hasattr(channel, "is_subscribed")) else (channel.id not in subscribed_channel_ids if channel else True)
            if "semantic_mutation" in "".join(data["sources"]):
                is_discovery = True

            scored_candidates.append({
                "video": video,
                "score": eval_data["score"],
                "badge": eval_data["badge"],
                "breakdown": eval_data["breakdown"],
                "best_topic": eval_data["best_topic"],
                "sources": list(data["sources"]),
                "is_discovery": is_discovery
            })

        scored_candidates.sort(key=lambda x: x["score"], reverse=True)
        return scored_candidates

    def _second_pass_deduplicate_and_dampen(self, scored_candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        final_feed: List[Dict[str, Any]] = []
        seen_titles = set()
        channel_counts = {}

        for item in scored_candidates:
            video = item["video"]
            channel_id = video.channel_id

            norm_title = "".join(c for c in video.title.lower() if c.isalnum())
            if norm_title in seen_titles:
                continue

            c_count = channel_counts.get(channel_id, 0)
            if c_count > 0:
                penalty = 0.5 ** c_count
                item["score"] = item["score"] * penalty
                item["badge"] = self._get_soft_badge(item["score"])

            seen_titles.add(norm_title)
            channel_counts[channel_id] = c_count + 1
            final_feed.append(item)

        final_feed.sort(key=lambda x: x["score"], reverse=True)
        return final_feed

    def _third_pass_interleave(self, final_feed: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
        diversified_feed: List[Dict[str, Any]] = []
        discovery_pool = [x for x in final_feed if x["is_discovery"]]
        network_pool = [x for x in final_feed if not x["is_discovery"]]

        n_idx = 0
        d_idx = 0
        d_count = 0
        target_d_ratio = self.serendipity

        max_channel_occupancy = max(1, int(0.20 * limit))
        final_channel_counts = {}
        max_mutation_cluster_occupancy = max(1, int(0.20 * limit))
        final_mutation_cluster_counts = {}

        mutation_to_parent = {}
        if self.semantic_mutations:
            mutation_to_parent = {m.mutation_topic: m.parent_topic for m in self.semantic_mutations}

        def allowed_by_mutation_cluster(cand) -> bool:
            topic = cand["best_topic"]
            if topic in mutation_to_parent:
                parent = mutation_to_parent[topic]
                current_count = final_mutation_cluster_counts.get(parent, 0)
                if current_count >= max_mutation_cluster_occupancy:
                    return False
            return True

        def increment_mutation_cluster(cand):
            topic = cand["best_topic"]
            if topic in mutation_to_parent:
                parent = mutation_to_parent[topic]
                final_mutation_cluster_counts[parent] = final_mutation_cluster_counts.get(parent, 0) + 1

        def try_add_candidate(cand) -> bool:
            c_id = cand["video"].channel_id
            if final_channel_counts.get(c_id, 0) < max_channel_occupancy and allowed_by_mutation_cluster(cand):
                diversified_feed.append(cand)
                final_channel_counts[c_id] = final_channel_counts.get(c_id, 0) + 1
                increment_mutation_cluster(cand)
                return True
            return False

        while len(diversified_feed) < limit and (n_idx < len(network_pool) or d_idx < len(discovery_pool)):
            total_len = len(diversified_feed)
            want_discovery = False
            if target_d_ratio > 0 and total_len > 0:
                want_discovery = (d_count / total_len) < target_d_ratio

            if want_discovery and d_idx < len(discovery_pool):
                candidate = discovery_pool[d_idx]
                d_idx += 1
                if try_add_candidate(candidate):
                    d_count += 1
            elif n_idx < len(network_pool):
                candidate = network_pool[n_idx]
                n_idx += 1
                try_add_candidate(candidate)
            elif d_idx < len(discovery_pool):
                candidate = discovery_pool[d_idx]
                d_idx += 1
                if try_add_candidate(candidate):
                    d_count += 1
            else:
                break

        return diversified_feed[:limit]

    def rerank_and_diversify(
        self,
        candidates: Dict[str, Dict[str, Any]],
        subscribed_channel_ids: Set[str],
        limit: int = 30,
        impression_counts: Dict[str, int] = None
    ) -> List[Dict[str, Any]]:
        """
        Stage 2 entry: Scores candidates, suppresses duplicate titles,
        dampens channel monopolization, and balances rolling discovery.
        """
        scored = self._first_pass_score_candidates(candidates, subscribed_channel_ids, impression_counts)
        filtered = self._second_pass_deduplicate_and_dampen(scored)
        return self._third_pass_interleave(filtered, limit)
