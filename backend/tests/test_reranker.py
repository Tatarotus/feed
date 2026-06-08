import pytest
from datetime import datetime, timedelta, timezone
from app.pipeline.ranking.reranker import Stage2Reranker
from app.models import Video, Channel, Interest, SemanticMutation

def test_calculate_freshness_decay():
    reranker = Stage2Reranker(user_interests=[])
    
    # Under 24 hours should be 1.0
    now = datetime.now(timezone.utc)
    recent_date = now - timedelta(hours=10)
    assert reranker.calculate_freshness_decay(recent_date) == 1.0

    # Older content should decay exponentially
    old_date = now - timedelta(hours=24 + 144) # 1 half-life older than 24h
    decay = reranker.calculate_freshness_decay(old_date)
    # e^-1 is approximately 0.3678
    assert 0.35 < decay < 0.38

def test_score_video_basic():
    channel = Channel(is_trusted=True, quality_score=1.0, preference_score=1.0, is_subscribed=False)
    video = Video(id="v1", title="Test Video", clickbait_score=0.0, publish_date=datetime.now(timezone.utc))
    
    reranker = Stage2Reranker(user_interests=[], w_trust=10.0, w_pref=10.0, w_sub=10.0, w_semantic=10.0, w_clickbait=10.0)
    score_data = reranker.score_video(video, channel, s_sem=0.0)
    
    assert score_data["score"] == 20.0
    assert score_data["breakdown"]["repeat_penalty"] == 0.0

def test_score_video_complex():
    channel = Channel(is_trusted=False, quality_score=0.5, preference_score=0.5, is_subscribed=True)
    video = Video(id="v1", title="Test Video", clickbait_score=0.8, publish_date=datetime.now(timezone.utc), embedding=[0.5, 0.5])
    
    interest = Interest(topic="tech", weight=1.2, embedding=[0.5, 0.5])
    mutation = SemanticMutation(mutation_topic="ai", parent_topic="tech", confidence_score=0.5, mutation_embedding=[0.5, 0.5], status="promoted")
    
    reranker = Stage2Reranker(
        user_interests=[interest],
        semantic_mutations=[mutation],
        w_trust=10.0,
        w_pref=10.0,
        w_sub=10.0,
        w_semantic=10.0,
        w_clickbait=10.0,
        neg_centroid=[0.5, 0.5]
    )
    
    # Run inline score
    score_data = reranker.score_video(video, channel, s_sem=None)
    assert "score" in score_data
    assert score_data["breakdown"]["negative_demotion"] > 0

def test_score_video_badge_ranges():
    channel = Channel(is_trusted=True, quality_score=1.0, preference_score=1.0, is_subscribed=True)
    video = Video(id="v1", title="High", clickbait_score=0.0, publish_date=datetime.now(timezone.utc))
    
    # High Affinity badge: score >= 65
    r1 = Stage2Reranker(user_interests=[], w_trust=50.0, w_pref=20.0, w_sub=10.0)
    assert r1.score_video(video, channel, s_sem=0.0)["badge"] == "High Affinity"
    
    # High Signal badge: 45 <= score < 65
    r2 = Stage2Reranker(user_interests=[], w_trust=30.0, w_pref=20.0, w_sub=0.0)
    assert r2.score_video(video, channel, s_sem=0.0)["badge"] == "High Signal"

    # Discovery Seed badge: 25 <= score < 45
    r3 = Stage2Reranker(user_interests=[], w_trust=20.0, w_pref=10.0, w_sub=0.0)
    assert r3.score_video(video, channel, s_sem=0.0)["badge"] == "Discovery Signal" or r3.score_video(video, channel, s_sem=0.0)["badge"] == "Discovery Seed"

    # Topic Exploration badge: score < 25
    r4 = Stage2Reranker(user_interests=[], w_trust=10.0, w_pref=5.0, w_sub=0.0)
    assert r4.score_video(video, channel, s_sem=0.0)["badge"] == "Topic Exploration"

def test_rerank_and_diversify_basic():
    channel1 = Channel(id="c1", is_trusted=True, quality_score=1.0, preference_score=1.0, is_subscribed=True)
    channel2 = Channel(id="c2", is_trusted=True, quality_score=1.0, preference_score=1.0, is_subscribed=True)
    
    v1 = Video(id="v1", channel_id="c1", title="Title One", clickbait_score=0.0, publish_date=datetime.now(timezone.utc), channel=channel1)
    v2 = Video(id="v2", channel_id="c2", title="Title Two", clickbait_score=0.0, publish_date=datetime.now(timezone.utc), channel=channel2)
    
    candidates = {
        "v1": {
            "video": v1,
            "semantic_similarity": 0.8,
            "sources": {"semantic_affinity"}
        },
        "v2": {
            "video": v2,
            "semantic_similarity": 0.7,
            "sources": {"semantic_affinity"}
        }
    }
    
    reranker = Stage2Reranker(user_interests=[])
    feed = reranker.rerank_and_diversify(
        candidates=candidates,
        subscribed_channel_ids={"c1", "c2"},
        limit=10,
        impression_counts={"v1": 2}
    )
    
    assert len(feed) == 2
    assert feed[0]["breakdown"]["repeat_penalty"] < 0.0 or feed[1]["breakdown"]["repeat_penalty"] < 0.0

def test_rerank_and_diversify_complex():
    channel = Channel(id="c1", is_trusted=True, quality_score=1.0, preference_score=1.0, is_subscribed=True)
    channel2 = Channel(id="c2", is_trusted=False, quality_score=1.0, preference_score=1.0, is_subscribed=False)
    
    # 1. Test duplicate titles filtering
    v1 = Video(id="v1", channel_id="c1", title="Duplicate Title!", clickbait_score=0.0, publish_date=datetime.now(timezone.utc), channel=channel)
    v2 = Video(id="v2", channel_id="c1", title="duplicate title", clickbait_score=0.0, publish_date=datetime.now(timezone.utc), channel=channel)
    
    # 2. Test channel counts penalty
    v3 = Video(id="v3", channel_id="c1", title="Title Three", clickbait_score=0.0, publish_date=datetime.now(timezone.utc), channel=channel)
    v4 = Video(id="v4", channel_id="c1", title="Title Four", clickbait_score=0.0, publish_date=datetime.now(timezone.utc), channel=channel)
    
    # 3. Test mutation best_topic parsing and cluster quotas
    v5 = Video(id="v5", channel_id="c2", title="Mutation Video", clickbait_score=0.0, publish_date=datetime.now(timezone.utc), channel=channel2)
    
    candidates = {
        "v1": {"video": v1, "semantic_similarity": 0.9, "sources": {"semantic_affinity"}},
        "v2": {"video": v2, "semantic_similarity": 0.8, "sources": {"semantic_affinity"}},
        "v3": {"video": v3, "semantic_similarity": 0.85, "sources": {"semantic_affinity"}},
        "v4": {"video": v4, "semantic_similarity": 0.8, "sources": {"semantic_affinity"}},
        "v5": {"video": v5, "semantic_similarity": 0.8, "sources": {"semantic_mutation (ai)"}}
    }
    
    mutation = SemanticMutation(mutation_topic="ai", parent_topic="tech", confidence_score=0.5, mutation_embedding=[0.5, 0.5])
    
    reranker = Stage2Reranker(user_interests=[], semantic_mutations=[mutation], serendipity=0.4)
    feed = reranker.rerank_and_diversify(
        candidates=candidates,
        subscribed_channel_ids={"c1"},
        limit=10
    )
    
    # duplicate title v2 should be filtered
    titles = [x["video"].title.lower() for x in feed]
    assert "duplicate title" not in titles
    
    # Mutation parsing works
    mutation_items = [x for x in feed if x["best_topic"] == "ai"]
    assert len(mutation_items) > 0
