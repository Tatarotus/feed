from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Video, VideoChunk
from app.pipeline.enrichment.embedder import embedder
from app.schemas import VideoResponse

router = APIRouter(prefix="/search", tags=["Search"])

@router.get("", response_model=List[VideoResponse])
async def search_videos(q: str, limit: int = 25, db: Session = Depends(get_db)):
    """
    Hybrid Search Engine.
    Executes a dual lexical (keyword match) and semantic pgvector search.
    Awaits async embedding queries with caching enabled.
    """
    if not q or not q.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Search query cannot be empty."
        )

    clean_query = q.strip()

    try:
        # 1. Await query embedding, passing db for caching checks
        query_vector = await embedder.generate_embedding(clean_query, db=db, input_type="query")

        # 2. Semantic Search on Parent Videos
        stmt_video = (
            select(Video)
            .options(joinedload(Video.channel))
            .where(Video.processing_status == "embedded")
            .order_by(Video.embedding.cosine_distance(query_vector))
            .limit(limit)
        )
        semantic_videos = db.scalars(stmt_video).all()

        # 3. Deep Semantic Search on Transcript Chunks
        stmt_chunk = (
            select(VideoChunk)
            .options(joinedload(VideoChunk.video).joinedload(Video.channel))
            .order_by(VideoChunk.embedding.cosine_distance(query_vector))
            .limit(limit)
        )
        semantic_chunks = db.scalars(stmt_chunk).all()

        # 4. Lexical (Keyword) Match on Title and Description
        stmt_lexical = (
            select(Video)
            .options(joinedload(Video.channel))
            .where(
                and_(
                    Video.processing_status == "embedded",
                    or_(
                        Video.title.ilike(f"%{clean_query}%"),
                        Video.description.ilike(f"%{clean_query}%")
                    )
                )
            )
            .limit(limit)
        )
        lexical_videos = db.scalars(stmt_lexical).all()

        # 5. Merge all candidates, eliminating duplicates in memory
        merged_videos: Dict[str, Video] = {}

        # Add parent semantic hits
        for v in semantic_videos:
            merged_videos[v.id] = v

        # Add chunk transcript hits (mapping to parent video)
        for chunk in semantic_chunks:
            if chunk.video and chunk.video.processing_status == "embedded":
                merged_videos[chunk.video_id] = chunk.video

        # Add keyword lexical hits
        for v in lexical_videos:
            merged_videos[v.id] = v

        results = list(merged_videos.values())
        return results[:limit]

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )
