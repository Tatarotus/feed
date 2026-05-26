import React, { useState, useRef, useCallback } from 'react';
import { api } from '../utils/api';

export default function QueuePanel({ queue, onRefreshQueue, onPlayVideo }) {
  const [loading, setLoading] = useState(false);
  // Local ordered copy — updated optimistically on drop
  const [orderedQueue, setOrderedQueue] = useState(queue);
  // Keep in sync when parent refreshes
  React.useEffect(() => { setOrderedQueue(queue); }, [queue]);

  // Drag state refs (no re-render needed mid-drag)
  const dragIndexRef = useRef(null);
  const [dragOverIndex, setDragOverIndex] = useState(null);

  /* ── Drag handlers ── */
  const handleDragStart = useCallback((e, index) => {
    dragIndexRef.current = index;
    e.dataTransfer.effectAllowed = 'move';
    // Use a transparent 1×1 ghost so the row doesn't flicker
    const ghost = document.createElement('div');
    ghost.style.cssText = 'position:fixed;top:-999px;left:-999px;opacity:0;';
    document.body.appendChild(ghost);
    e.dataTransfer.setDragImage(ghost, 0, 0);
    setTimeout(() => document.body.removeChild(ghost), 0);
  }, []);

  const handleDragOver = useCallback((e, index) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOverIndex(index);
  }, []);

  const handleDragLeave = useCallback(() => {
    setDragOverIndex(null);
  }, []);

  const handleDrop = useCallback((e, dropIndex) => {
    e.preventDefault();
    const fromIndex = dragIndexRef.current;
    if (fromIndex === null || fromIndex === dropIndex) {
      setDragOverIndex(null);
      return;
    }
    const next = [...orderedQueue];
    const [moved] = next.splice(fromIndex, 1);
    next.splice(dropIndex, 0, moved);
    setOrderedQueue(next);
    setDragOverIndex(null);
    dragIndexRef.current = null;
  }, [orderedQueue]);

  const handleDragEnd = useCallback(() => {
    setDragOverIndex(null);
    dragIndexRef.current = null;
  }, []);

  /* ── Queue actions ── */
  const handleConsume = async (videoId) => {
    try {
      await api.consumeQueueItem(videoId);
      onRefreshQueue();
    } catch (err) {
      alert(`Failed to complete queue item: ${err.message}`);
    }
  };

  const handleRemove = async (videoId) => {
    try {
      await api.dequeueVideo(videoId);
      onRefreshQueue();
    } catch (err) {
      alert(`Failed to remove queue item: ${err.message}`);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div className="panel-header">
        <span className="panel-title">See Later ({orderedQueue.length})</span>
        <button onClick={onRefreshQueue} style={{ padding: '2px 8px', fontSize: '0.72rem' }}>
          Refresh
        </button>
      </div>

      <div className="scroll-section" style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {orderedQueue.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '30px 10px', color: 'var(--text-muted)', fontSize: '0.78rem', lineHeight: '1.4' }}>
            Queue is empty.<br />Save interesting recommendations for focused viewing sessions.
          </div>
        ) : (
          orderedQueue.map((item, index) => {
            const video = item.video;
            const thumbUrl = video.thumbnail_url || `https://i.ytimg.com/vi/${video.id}/hqdefault.jpg`;
            const isDragOver = dragOverIndex === index;
            const isDragging = dragIndexRef.current === index;

            return (
              <div
                key={item.id}
                className={`playlist-row${isDragOver ? ' drag-over' : ''}${isDragging ? ' dragging' : ''}`}
                draggable
                onDragStart={(e) => handleDragStart(e, index)}
                onDragOver={(e) => handleDragOver(e, index)}
                onDragLeave={handleDragLeave}
                onDrop={(e) => handleDrop(e, index)}
                onDragEnd={handleDragEnd}
              >
                {/* Drag handle */}
                <div className="drag-handle" title="Drag to reorder">
                  <svg width="10" height="16" viewBox="0 0 10 16" fill="currentColor">
                    <circle cx="3" cy="3"  r="1.5"/>
                    <circle cx="3" cy="8"  r="1.5"/>
                    <circle cx="3" cy="13" r="1.5"/>
                    <circle cx="7" cy="3"  r="1.5"/>
                    <circle cx="7" cy="8"  r="1.5"/>
                    <circle cx="7" cy="13" r="1.5"/>
                  </svg>
                </div>

                {/* Thumbnail */}
                <div className="playlist-thumbnail" onClick={() => onPlayVideo(video)}>
                  <img src={thumbUrl} alt={video.title} loading="lazy" />
                </div>

                {/* Info */}
                <div className="playlist-info">
                  <div
                    onClick={() => onPlayVideo(video)}
                    className="playlist-title"
                    title={video.title}
                  >
                    {video.title}
                  </div>

                  <div className="playlist-meta">
                    <span
                      style={{
                        fontSize: '0.66rem',
                        color: 'var(--text-secondary)',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        maxWidth: '100px'
                      }}
                      title={video.channel ? video.channel.title : 'Channel'}
                    >
                      {video.channel ? video.channel.custom_name || video.channel.title : 'Channel'}
                    </span>

                    <div style={{ display: 'flex', gap: '4px' }}>
                      <button
                        onClick={() => handleConsume(video.id)}
                        style={{
                          fontSize: '0.64rem',
                          padding: '1px 5px',
                          backgroundColor: 'rgba(16, 185, 129, 0.08)',
                          color: 'var(--success)',
                          borderColor: 'rgba(16, 185, 129, 0.15)'
                        }}
                        title="Mark as Watch Completed"
                      >
                        ✓ Done
                      </button>

                      <button
                        onClick={() => handleRemove(video.id)}
                        style={{
                          fontSize: '0.64rem',
                          padding: '1px 5px',
                          backgroundColor: 'var(--bg-card)',
                          borderColor: 'var(--border-subtle)'
                        }}
                        title="Remove Bookmark"
                      >
                        ✕
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
