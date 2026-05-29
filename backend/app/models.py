from sqlalchemy import Column, Integer, String, Text, Boolean, Float, DateTime, ForeignKey, ARRAY, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from app.database import Base
from app.config import settings

class Channel(Base):
    __tablename__ = "channels"

    id = Column(String(255), primary_key=True)  # YouTube channel ID
    title = Column(String(255), nullable=False)
    description = Column(Text)
    custom_name = Column(String(255))
    rss_url = Column(String(512))
    provider = Column(String(50), default="rss")  # 'rss', 'invidious', 'piped'
    thumbnail_url = Column(String(512))
    
    # Core Classification Weights
    is_trusted = Column(Boolean, default=True)
    quality_score = Column(Float, default=1.0)
    preference_score = Column(Float, default=1.0)
    is_subscribed = Column(Boolean, default=True, nullable=False)
    
    # Sync Configuration
    polling_interval_minutes = Column(Integer, default=360)
    last_fetched_at = Column(DateTime(timezone=True))
    etag = Column(String(255))
    last_modified = Column(String(255))
    
    category = Column(String(100))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    videos = relationship("Video", back_populates="channel", cascade="all, delete-orphan")


class Video(Base):
    __tablename__ = "videos"

    id = Column(String(255), primary_key=True)  # YouTube video ID
    channel_id = Column(String(255), ForeignKey("channels.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    normalized_text = Column(Text)  # Pre-cleaned concatenated title + description
    thumbnail_url = Column(String(512))
    publish_date = Column(DateTime(timezone=True), nullable=False)
    url = Column(String(512), nullable=False)
    
    # Processing state-machine
    processing_status = Column(String(50), default="pending")  # 'pending', 'ingested', 'chunked', 'embedded', 'summarized', 'failed'
    processing_error = Column(Text)
    retry_count = Column(Integer, default=0)
    
    # Heuristic ratings
    clickbait_score = Column(Float, default=0.0)
    clickbait_reasons = Column(ARRAY(Text), default=[])
    
    # Extendable payload caching
    raw_metadata = Column(JSONB, default={})
    
    # Dynamic vector mappings (Bound tosettings.EMBEDDING_DIM config)
    embedding_model = Column(String(100))
    embedding_version = Column(String(50))
    embedding = Column(Vector(settings.EMBEDDING_DIM))
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    channel = relationship("Channel", back_populates="videos")
    chunks = relationship("VideoChunk", back_populates="video", cascade="all, delete-orphan")
    queue_items = relationship("QueueItem", back_populates="video", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="video", cascade="all, delete-orphan")


class VideoChunk(Base):
    __tablename__ = "video_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String(255), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    normalized_text = Column(Text)
    language_code = Column(String(10), default="en")
    transcript_source = Column(String(50))  # 'youtube_api', 'subtitles_fallback'
    
    # Model tracking & vector binding
    embedding_model = Column(String(100))
    embedding_version = Column(String(50))
    embedding = Column(Vector(settings.EMBEDDING_DIM))
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    video = relationship("Video", back_populates="chunks")


class Interest(Base):
    __tablename__ = "interests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, default=1)
    topic = Column(String(255), nullable=False)
    weight = Column(Float, default=1.0)
    
    embedding_model = Column(String(100))
    embedding_version = Column(String(50))
    embedding = Column(Vector(settings.EMBEDDING_DIM))
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint('user_id', 'topic', name='_user_topic_uc'),)


class EmbeddingCache(Base):
    __tablename__ = "embedding_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    text_hash = Column(String(64), unique=True, index=True, nullable=False)  # SHA-256 hash of normalized text
    provider = Column(String(100), nullable=False)
    model = Column(String(255), nullable=False)
    embedding = Column(Vector(settings.EMBEDDING_DIM), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class QueueItem(Base):
    __tablename__ = "queue_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, default=1)
    video_id = Column(String(255), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False)
    priority = Column(Integer, default=0)
    added_at = Column(DateTime(timezone=True), server_default=func.now())
    consumed_at = Column(DateTime(timezone=True))
    is_completed = Column(Boolean, default=False)

    video = relationship("Video", back_populates="queue_items")

    __table_args__ = (UniqueConstraint('user_id', 'video_id', name='_user_video_uc'),)


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, default=1)
    video_id = Column(String(255), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(50), nullable=False)  # 'watch', 'like', 'skip', 'queue_add', 'queue_consume', 'dismiss'
    watch_time_pct = Column(Float, default=0.0)
    rating = Column(Integer)
    event_metadata = Column(JSONB, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    video = relationship("Video", back_populates="events")


class LikedVideo(Base):
    __tablename__ = "liked_videos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, default=1, nullable=False)
    video_id = Column(String(255), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False)
    channel_id = Column(String(255), ForeignKey("channels.id", ondelete="CASCADE"), nullable=False)
    liked_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    semantic_score = Column(Float, default=0.0)
    source_bucket = Column(String(255))
    watch_duration_seconds = Column(Float, default=0.0)
    embedding = Column(Vector(settings.EMBEDDING_DIM))
    metadata_json = Column(JSONB, default={})

    video = relationship("Video")
    channel = relationship("Channel")

    __table_args__ = (UniqueConstraint('user_id', 'video_id', name='_user_liked_video_uc'),)


class UserInteraction(Base):
    __tablename__ = "user_interactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, default=1, nullable=False)
    video_id = Column(String(255), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False)
    interaction_type = Column(String(50), nullable=False)  # 'impression', 'click', 'like', 'dislike', 'subscribe', 'skip'
    watch_duration_seconds = Column(Float, default=0.0)
    rerank_score = Column(Float, default=0.0)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    event_metadata = Column(JSONB, default={})

    video = relationship("Video")

