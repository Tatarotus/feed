from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# --- Channels ---
class ChannelBase(BaseModel):
    id: str = Field(..., description="YouTube channel ID, URL or handle")
    title: Optional[str] = ""
    description: Optional[str] = None
    custom_name: Optional[str] = None
    rss_url: Optional[str] = None
    provider: str = "rss"
    is_trusted: bool = True
    quality_score: float = 1.0
    preference_score: float = 1.0
    polling_interval_minutes: int = 360
    category: Optional[str] = None
    is_subscribed: bool = True
    thumbnail_url: Optional[str] = None

class ChannelCreate(ChannelBase):
    pass

class ChannelUpdate(BaseModel):
    custom_name: Optional[str] = None
    is_trusted: Optional[bool] = None
    quality_score: Optional[float] = None
    preference_score: Optional[float] = None
    polling_interval_minutes: Optional[int] = None
    category: Optional[str] = None
    is_subscribed: Optional[bool] = None
    thumbnail_url: Optional[str] = None

class ChannelResponse(ChannelBase):
    last_fetched_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True

# --- Videos ---
class VideoResponse(BaseModel):
    id: str
    channel_id: str
    title: str
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    publish_date: datetime
    url: str
    processing_status: str
    clickbait_score: float
    clickbait_reasons: List[str]
    raw_metadata: Dict[str, Any]
    channel: ChannelResponse

    class Config:
        from_attributes = True

# --- Queue Items ---
class QueueItemCreate(BaseModel):
    video_id: str
    priority: int = 0

class QueueItemResponse(BaseModel):
    id: int
    user_id: int
    video_id: str
    priority: int
    added_at: datetime
    consumed_at: Optional[datetime] = None
    is_completed: bool
    video: VideoResponse

    class Config:
        from_attributes = True

# --- Interests (Followed Topics) ---
class InterestCreate(BaseModel):
    topic: str = Field(..., min_length=2, max_length=100)
    weight: float = 1.0

class InterestUpdate(BaseModel):
    weight: Optional[float] = None

class SeedCreate(BaseModel):
    url: str = Field(..., description="YouTube video URL")
    weight: float = 2.0

class InterestResponse(BaseModel):
    id: int
    user_id: int
    topic: str
    weight: float
    created_at: datetime

    class Config:
        from_attributes = True

# --- Feed Recommendations ---
class ScoreBreakdown(BaseModel):
    trusted_boost: float
    preference_boost: float
    subscription_boost: float
    semantic_affinity: float
    clickbait_penalty: float
    negative_demotion: float
    freshness_decay: float
    repeat_penalty: float = 0.0


class FeedItemResponse(BaseModel):
    video: VideoResponse
    score: float
    badge: str
    breakdown: ScoreBreakdown
    best_topic: str
    is_discovery: bool
    sources: List[str]

# --- Onboarding Cold Start ---
class OnboardingSetup(BaseModel):
    channels: List[ChannelCreate]
    interests: List[str]

# --- Liked Videos ---
class LikedVideoResponse(BaseModel):
    id: int
    user_id: int
    video_id: str
    channel_id: str
    liked_at: datetime
    semantic_score: float
    source_bucket: Optional[str] = None
    watch_duration_seconds: float
    metadata_json: Dict[str, Any]
    video: VideoResponse
    channel: ChannelResponse

    class Config:
        from_attributes = True


class SemanticMutationResponse(BaseModel):
    id: int
    parent_topic: str
    mutation_topic: str
    similarity_score: float
    confidence_score: float
    telemetry_score: float
    survival_score: float
    generation_depth: int
    status: str

    # Semantic Energy Economy fields
    energy: float
    attention_share: float
    competition_score: float
    fatigue_multiplier: float

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

