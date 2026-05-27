import React, { useState, useEffect } from 'react';
import { api } from '../utils/api';

const LikeIcon = ({ filled }) => (
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="action-svg">
    <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"></path>
  </svg>
);

const DislikeIcon = ({ filled }) => (
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="action-svg">
    <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm8-13h3a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-3"></path>
  </svg>
);

export default function FocusPlayer({ video, onClose }) {
  const [liked, setLiked] = useState(false);
  const [disliked, setDisliked] = useState(false);

  const isVisible = !!video;
  const displayVideo = video || { id: '', title: '', channel: null };

  // Reset feedback interaction states when video changes
  useEffect(() => {
    setLiked(false);
    setDisliked(false);
  }, [video?.id]);

  useEffect(() => {
    if (!video) {
      document.body.style.overflow = 'unset';
      return;
    }

    // Log watch start telemetry event
    api.logEvent(video.id, "watch", 10.0);
    
    // Lock body scrolling when overlay player is active
    document.body.style.overflow = 'hidden';
    
    return () => {
      // Restore scrolling upon closing
      document.body.style.overflow = 'unset';
    };
  }, [video]);

  const handleClose = () => {
    if (video) {
      // Log completed watch session upon modal close
      api.logEvent(video.id, "watch", 100.0);
    }
    onClose();
  };

  const handleLike = async () => {
    if (!video || liked) return;
    try {
      await api.likeVideo(video.id);
      setLiked(true);
      setDisliked(false);
    } catch (err) {
      console.error(err);
    }
  };

  const handleDislike = async () => {
    if (!video || disliked) return;
    try {
      await api.dislikeVideo(video.id);
      setDisliked(true);
      setLiked(false);
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div 
      className="focus-player-overlay" 
      onClick={handleClose}
      style={{
        display: isVisible ? 'flex' : 'none',
        pointerEvents: isVisible ? 'auto' : 'none'
      }}
    >
      <button 
        className="focus-player-close" 
        onClick={handleClose}
        style={{
          cursor: 'pointer',
          color: 'var(--text-primary)',
          backgroundColor: 'var(--bg-surface)',
          border: '1px solid var(--border-subtle)',
          padding: '8px 16px',
          borderRadius: '4px',
          fontWeight: 'bold',
          transition: 'background-color var(--transition-fast)'
        }}
      >
        Close Focus Player
      </button>

      {/* Stop click propagation on player container to prevent accidental closing */}
      <div 
        className="focus-player-container" 
        onClick={(e) => e.stopPropagation()}
        style={{
          boxShadow: '0 10px 40px rgba(0,0,0,0.8)',
          display: 'flex',
          flexDirection: 'column',
          aspectRatio: 'unset',
          height: 'auto'
        }}
      >
        <div style={{ width: '100%', aspectRatio: '16/9' }}>
          <iframe
            width="100%"
            height="100%"
            src={video ? `https://www.youtube.com/embed/${video.id}?autoplay=1&rel=0&showinfo=0&iv_load_policy=3&modestbranding=1` : "about:blank"}
            title={displayVideo.title}
            frameBorder="0"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
            allowFullScreen
            style={{ width: '100%', height: '100%', border: 'none' }}
          ></iframe>
        </div>

        {/* Video metadata and premium feedback controls */}
        <div className="player-control-bar">
          <div className="player-meta">
            <h2 className="player-title" title={displayVideo.title}>{displayVideo.title}</h2>
            <div className="player-channel" title={displayVideo.channel ? displayVideo.channel.title : "Channel"}>
              {displayVideo.channel ? displayVideo.channel.custom_name || displayVideo.channel.title : "Unknown Channel"}
            </div>
          </div>

          <div className="player-feedback-wrapper">
            <div className="player-feedback-pill">
              <button 
                onClick={handleLike} 
                className={`player-feedback-btn like-btn ${liked ? 'active' : ''}`}
                disabled={liked}
                title="Like this video"
              >
                <LikeIcon filled={liked} />
                <span>{liked ? "Liked" : "Like"}</span>
              </button>
              <span className="player-feedback-divider"></span>
              <button 
                onClick={handleDislike} 
                className={`player-feedback-btn dislike-btn ${disliked ? 'active' : ''}`}
                disabled={disliked}
                title="Dislike this video"
              >
                <DislikeIcon filled={disliked} />
                <span>{disliked ? "Disliked" : "Dislike"}</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
