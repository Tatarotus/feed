from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Event, QueueItem, Video
from app.schemas import QueueItemCreate, QueueItemResponse

router = APIRouter(prefix="/queue", tags=["Queue"])

@router.get("", response_model=List[QueueItemResponse])
def get_queue(db: Session = Depends(get_db)):
    """Fetch all active (uncompleted) items in the Read Later Queue."""
    stmt = (
        select(QueueItem)
        .options(joinedload(QueueItem.video).joinedload(Video.channel))
        .where(
            and_(
                QueueItem.user_id == 1,
                QueueItem.is_completed == False
            )
        )
        .order_by(QueueItem.priority.desc(), QueueItem.added_at.desc())
    )
    return db.scalars(stmt).all()

@router.post("", response_model=QueueItemResponse, status_code=status.HTTP_201_CREATED)
def add_to_queue(item_in: QueueItemCreate, db: Session = Depends(get_db)):
    """Bookmark a video into the queue."""
    # Check if video exists
    video = db.scalar(select(Video).where(Video.id == item_in.video_id))
    if not video:
        raise HTTPException(status_code=404, detail="Video not found.")

    # Check if already in queue
    existing = db.scalar(
        select(QueueItem).where(
            and_(
                QueueItem.user_id == 1,
                QueueItem.video_id == item_in.video_id
            )
        )
    )

    if existing:
        if not existing.is_completed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Video is already in your active queue."
            )
        # Reactivate completed item
        existing.is_completed = False
        existing.consumed_at = None
        existing.priority = item_in.priority
        db.commit()
        db.refresh(existing)
        return existing

    queue_item = QueueItem(
        user_id=1,
        video_id=item_in.video_id,
        priority=item_in.priority
    )

    # Log telemetry event
    event = Event(
        user_id=1,
        video_id=item_in.video_id,
        event_type="queue_add"
    )
    db.add(event)

    db.add(queue_item)
    db.commit()
    db.refresh(queue_item)

    # Reload with joined relationships
    stmt = (
        select(QueueItem)
        .options(joinedload(QueueItem.video).joinedload(Video.channel))
        .where(QueueItem.id == queue_item.id)
    )
    return db.scalar(stmt)

@router.post("/{video_id}/consume", response_model=QueueItemResponse)
def consume_queue_item(video_id: str, db: Session = Depends(get_db)):
    """Mark a queue video as fully consumed (completed)."""
    item = db.scalar(
        select(QueueItem)
        .options(joinedload(QueueItem.video).joinedload(Video.channel))
        .where(
            and_(
                QueueItem.user_id == 1,
                QueueItem.video_id == video_id
            )
        )
    )

    if not item:
        raise HTTPException(status_code=404, detail="Active queue item not found for this video.")

    item.is_completed = True
    item.consumed_at = datetime.now(timezone.utc)

    # Log telemetry event
    event = Event(
        user_id=1,
        video_id=video_id,
        event_type="queue_consume"
    )
    db.add(event)

    db.commit()
    db.refresh(item)
    return item

@router.patch("/{item_id}", response_model=QueueItemResponse)
def update_priority(item_id: int, priority: int, db: Session = Depends(get_db)):
    """Update priority weighting of a queue item (supports user manual drag-sorting)."""
    item = db.scalar(
        select(QueueItem)
        .options(joinedload(QueueItem.video).joinedload(Video.channel))
        .where(QueueItem.id == item_id)
    )
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found.")

    item.priority = priority
    db.commit()
    db.refresh(item)
    return item

@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def dequeue_video(video_id: str, db: Session = Depends(get_db)):
    """Remove video entirely from the queue."""
    item = db.scalar(
        select(QueueItem).where(
            and_(
                QueueItem.user_id == 1,
                QueueItem.video_id == video_id
            )
        )
    )
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found.")

    db.delete(item)
    db.commit()
    return
