import React, { useState, useEffect } from 'react';
import { api } from '../utils/api';

function CliLoadingDashboard() {
  const [step, setStep] = useState(0);
  const [logs, setLogs] = useState([]);
  
  const stepLogs = [
    { prefix: "SYSTEM", text: "Booting active learning retrieval pipeline...", color: "var(--accent)" },
    { prefix: "DB", text: "Connecting to PostgreSQL pgvector space (127.0.0.1:5432)...", color: "var(--text-muted)" },
    { prefix: "DB", text: "Scanning 2048-dim Llama-Nemotron vector index...", color: "var(--text-muted)" },
    { prefix: "STAGE 1", text: "Querying semantic affinity candidates (threshold >= 0.35)...", color: "var(--accent)" },
    { prefix: "STAGE 1", text: "Fetching serendipity exploration adjacent interest pools...", color: "var(--accent)" },
    { prefix: "STAGE 1", text: "Completed. Retrieved 350 candidate streams.", color: "var(--success)" },
    { prefix: "STAGE 2", text: "Commencing multi-criteria reranking sweep...", color: "var(--accent)" },
    { prefix: "STAGE 2", text: "Checking negative telemetry logs and active dismissals...", color: "var(--text-muted)" },
    { prefix: "STAGE 2", text: "Applying clickbait penalty heuristics & decay functions...", color: "var(--text-muted)" },
    { prefix: "STAGE 2", text: "Interleaving discovery pool via cumulative ratio interleave...", color: "var(--accent)" },
    { prefix: "STAGE 2", text: "Spacing grid layout blocks for premium UX contrast...", color: "var(--text-muted)" },
    { prefix: "SYSTEM", text: "Generating final recommendation matrices...", color: "var(--accent)" },
    { prefix: "SUCCESS", text: "Output compiled! Ready for render.", color: "var(--success)" }
  ];

  useEffect(() => {
    setStep(0);
    setLogs([{
      time: new Date().toLocaleTimeString(),
      prefix: "SYSTEM",
      text: "Booting active learning retrieval pipeline...",
      color: "var(--accent)"
    }]);

    const interval = setInterval(() => {
      setStep(prev => {
        const next = prev + 1;
        if (next < stepLogs.length) {
          setLogs(current => [
            ...current,
            {
              time: new Date().toLocaleTimeString(),
              prefix: stepLogs[next].prefix,
              text: stepLogs[next].text,
              color: stepLogs[next].color
            }
          ]);
          return next;
        } else {
          setLogs([{
            time: new Date().toLocaleTimeString(),
            prefix: "SYSTEM",
            text: "Booting active learning retrieval pipeline...",
            color: "var(--accent)"
          }]);
          return 0;
        }
      });
    }, 450);

    return () => clearInterval(interval);
  }, []);

  const progress = Math.min(Math.round((step / (stepLogs.length - 1)) * 100), 100);
  
  const getProgressBar = (pct) => {
    const totalBlocks = 15;
    const filledBlocks = Math.round((pct / 100) * totalBlocks);
    const emptyBlocks = totalBlocks - filledBlocks;
    return "▰".repeat(filledBlocks) + "▱".repeat(emptyBlocks);
  };

  return (
    <div style={{
      gridColumn: '1 / -1',
      maxWidth: '650px',
      margin: '40px auto',
      width: '100%',
      backgroundColor: '#09090b',
      border: '1px solid var(--border-subtle)',
      borderRadius: '8px',
      overflow: 'hidden',
      boxShadow: '0 8px 30px rgba(0,0,0,0.5)',
      fontFamily: "'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace",
      fontSize: '0.8rem',
      textAlign: 'left'
    }}>
      <div style={{
        backgroundColor: '#18181b',
        padding: '10px 14px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        borderBottom: '1px solid var(--border-subtle)'
      }}>
        <div style={{ display: 'flex', gap: '6px' }}>
          <span style={{ width: '10px', height: '10px', borderRadius: '50%', backgroundColor: '#ef4444', display: 'inline-block' }}></span>
          <span style={{ width: '10px', height: '10px', borderRadius: '50%', backgroundColor: '#eab308', display: 'inline-block' }}></span>
          <span style={{ width: '10px', height: '10px', borderRadius: '50%', backgroundColor: '#22c55e', display: 'inline-block' }}></span>
        </div>
        <div style={{ color: 'var(--text-muted)', fontSize: '0.7rem', fontWeight: 'bold' }}>
          terminal - active_learning_engine
        </div>
        <div style={{ width: '38px' }}></div>
      </div>
      
      <div style={{
        padding: '16px',
        color: '#f4f4f5',
        display: 'flex',
        flexDirection: 'column',
        gap: '6px',
        height: '240px',
        overflowY: 'auto',
        scrollbarWidth: 'none'
      }}>
        {logs.map((log, i) => (
          <div key={i} style={{ display: 'flex', gap: '8px', lineHeight: '1.4' }}>
            <span style={{ color: 'var(--text-muted)' }}>[{log.time}]</span>
            <span style={{ color: log.color, fontWeight: 'bold' }}>[{log.prefix}]</span>
            <span style={{ color: log.prefix === 'SUCCESS' ? 'var(--success)' : '#e4e4e7' }}>{log.text}</span>
          </div>
        ))}
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: 'var(--accent)', fontWeight: 'bold' }}>
          <span>$</span>
          <span style={{
            display: 'inline-block',
            width: '8px',
            height: '14px',
            backgroundColor: 'var(--accent)',
            animation: 'blink 1s step-end infinite'
          }}></span>
        </div>
      </div>

      <div style={{
        backgroundColor: '#18181b',
        padding: '12px 16px',
        borderTop: '1px solid var(--border-subtle)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        color: 'var(--text-secondary)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ color: 'var(--accent)', fontWeight: 'bold' }}>COMPUTING</span>
          <span style={{ color: 'var(--text-muted)' }}>{getProgressBar(progress)}</span>
        </div>
        <div style={{ fontWeight: 'bold', color: 'var(--text-primary)' }}>
          {progress}%
        </div>
      </div>

      <style>{`
        @keyframes blink {
          50% { opacity: 0; }
        }
      `}</style>
    </div>
  );
}

const BookmarkIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="action-svg">
    <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path>
  </svg>
);

const BookmarkFilledIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="action-svg">
    <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path>
  </svg>
);

const TinderCrossIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round" className="action-svg">
    <line x1="18" y1="6" x2="6" y2="18"></line>
    <line x1="6" y1="6" x2="18" y2="18"></line>
  </svg>
);

const LikeIcon = ({ filled }) => (
  <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="action-svg">
    <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"></path>
  </svg>
);

const DislikeIcon = ({ filled }) => (
  <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="action-svg">
    <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm8-13h3a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-3"></path>
  </svg>
);

function ChannelAvatar({ channel, initials }) {
  const [hasError, setHasError] = useState(false);

  if (!channel || !channel.thumbnail_url || hasError) {
    return initials;
  }

  return (
    <img 
      src={channel.thumbnail_url} 
      alt="" 
      className="avatar-img"
      onError={() => setHasError(true)} 
    />
  );
}

export default function FeedList({ 
  feed, 
  loading, 
  onRefresh, 
  onPlayVideo, 
  onQueueUpdate,
  calmMode,
  learningMode,
  setCalmMode,
  setLearningMode,
  serendipity,
  onSerendipityChange
}) {
  const [explainData, setExplainData] = useState(null);
  const [explainLoading, setExplainLoading] = useState(false);
  const [likedVideos, setLikedVideos] = useState(new Set());
  const [dislikedVideos, setDislikedVideos] = useState(new Set());
  const [visibleCount, setVisibleCount] = useState(24); // 24 is a nice multiple for grids (e.g. 2, 3, or 4 cols)
  const [clickedVideos, setClickedVideos] = useState(new Set());

  const handlePlayVideoWrapper = (video) => {
    setClickedVideos(prev => {
      const next = new Set(prev);
      next.add(video.id);
      return next;
    });
    onPlayVideo(video);
  };

  const handleLike = async (videoId) => {
    try {
      if (likedVideos.has(videoId)) return;
      await api.likeVideo(videoId);
      setLikedVideos(prev => {
        const next = new Set(prev);
        next.add(videoId);
        return next;
      });
      // Remove dislike if any
      if (dislikedVideos.has(videoId)) {
        setDislikedVideos(prev => {
          const next = new Set(prev);
          next.delete(videoId);
          return next;
        });
      }
    } catch (err) {
      console.error("Like failed:", err);
    }
  };

  const handleDislike = async (videoId) => {
    try {
      if (dislikedVideos.has(videoId)) return;
      await api.dislikeVideo(videoId);
      setDislikedVideos(prev => {
        const next = new Set(prev);
        next.add(videoId);
        return next;
      });
      // Remove like if any
      if (likedVideos.has(videoId)) {
        setLikedVideos(prev => {
          const next = new Set(prev);
          next.delete(videoId);
          return next;
        });
      }
    } catch (err) {
      console.error("Dislike failed:", err);
    }
  };

  // --- Attach scroll listener to the middle .feed-scroll-container ---
  useEffect(() => {
    const scrollContainer = document.querySelector('.feed-scroll-container');
    if (!scrollContainer) return;

    const handleScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = scrollContainer;
      // Trigger when user scrolls within 300px of the bottom
      if (scrollHeight - scrollTop <= clientHeight + 300) {
        setVisibleCount(prev => Math.min(prev + 12, feed.length));
      }
    };
    
    scrollContainer.addEventListener('scroll', handleScroll);
    return () => scrollContainer.removeEventListener('scroll', handleScroll);
  }, [feed]);

  const handleQueueAction = async (video, inQueue) => {
    try {
      if (inQueue) {
        await api.dequeueVideo(video.id);
      } else {
        await api.addToQueue(video.id);
      }
      onQueueUpdate();
      api.logEvent(video.id, inQueue ? "dismiss" : "queue_add");
    } catch (err) {
      alert(`Queue modification failed: ${err.message}`);
    }
  };

  const handleInspectScore = async (videoId) => {
    setExplainLoading(true);
    setExplainData(null);
    try {
      const data = await api.explainScoring(videoId);
      setExplainData(data);
    } catch (err) {
      console.error("Failed to fetch explainable logs:", err);
    } finally {
      setExplainLoading(false);
    }
  };

  const formatPublishDate = (dateStr) => {
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
    } catch (e) {
      return dateStr;
    }
  };

  const filteredFeed = feed.filter(item => !dislikedVideos.has(item.video.id));

  return (
    <div className={calmMode ? "calm-mode" : ""}>
      {/* 1. YouTube-style horizontal Scrolling Chip Bar */}
      <div className="chips-bar">
        <button 
          onClick={() => setCalmMode(!calmMode)}
          className={`chip-button ${calmMode ? 'active' : ''}`}
        >
          Calm Mode
        </button>
        <button 
          onClick={() => setLearningMode(!learningMode)}
          className={`chip-button ${learningMode ? 'active' : ''}`}
        >
          Focus Mode
        </button>

        <span style={{ borderLeft: '1px solid var(--border-subtle)', margin: '0 4px' }}></span>

        <button onClick={onRefresh} disabled={loading} className="chip-button" style={{ color: 'var(--success)' }}>
          {loading ? "Re-syncing..." : "🔄 Sync Feed"}
        </button>
      </div>

      {/* Focus banner */}
      {learningMode && (
        <div style={{
          backgroundColor: 'rgba(59, 130, 246, 0.04)',
          borderBottom: '1px solid var(--border-subtle)',
          padding: '8px 24px',
          fontSize: '0.78rem',
          color: 'var(--text-secondary)',
          textAlign: 'center'
        }}>
          💡 <strong>Focus mode active:</strong> Scoring metrics and qualitative affinity values are hidden to prevent analysis anxiety.
        </div>
      )}

      {/* 2. YouTube-style Video Card Grid */}
      <div className="video-grid">
        {loading && filteredFeed.length === 0 ? (
          <CliLoadingDashboard />
        ) : filteredFeed.length === 0 ? (
          <div style={{ gridColumn: '1 / -1', textAlign: 'center', padding: '60px', color: 'var(--text-muted)' }}>
            No parsed videos in catalog. Trigger a manual sync or subscribe to channels in the config sidebar.
          </div>
        ) : (
          filteredFeed
            .slice(0, visibleCount)
            .map((item, idx) => {
              const video = item.video;
              const channel = video.channel;
              const scorePercent = Math.round(item.score);
              const inQueue = video.queue_items && video.queue_items.some(q => !q.is_completed);

              // Badge classifications
              let badgeClass = "badge trusted";
              if (item.is_discovery) badgeClass = "badge discovery";
              else if (video.clickbait_score > 0.4) badgeClass = "badge clickbait";

              const chInitials = channel ? (channel.custom_name || channel.title).substring(0, 1).toUpperCase() : "S";

              return (
                <div key={video.id} className="video-card">
                  {/* Card Thumbnail */}
                  <div className="card-thumbnail-wrapper" onClick={() => handlePlayVideoWrapper(video)}>
                    <img 
                      src={video.thumbnail_url || `https://i.ytimg.com/vi/${video.id}/hqdefault.jpg`} 
                      alt={video.title} 
                      loading="lazy"
                    />
                    
                    {/* Embedded overlay score badge */}
                    {!learningMode && (
                      <div 
                        className="thumbnail-score-overlay"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleInspectScore(video.id);
                        }}
                        title="Inspect dynamic scoring details"
                      >
                        {scorePercent}% Signal
                      </div>
                    )}
                    
                    {/* Tinder action buttons & metadata badge aligned side-by-side inside thumbnail */}
                    <div className="thumbnail-bottom-overlay" onClick={(e) => e.stopPropagation()}>
                      <button 
                        onClick={(e) => {
                          e.stopPropagation();
                          api.logEvent(video.id, "dismiss");
                          setDislikedVideos(prev => {
                            const next = new Set(prev);
                            next.add(video.id);
                            return next;
                          });
                        }}
                        className="thumb-action-btn btn-skip"
                        title="Dismiss and hide this recommendation"
                      >
                        <TinderCrossIcon />
                      </button>

                      <button 
                        onClick={(e) => {
                          e.stopPropagation();
                          handleQueueAction(video, inQueue);
                        }}
                        className={`thumb-action-btn btn-queue ${inQueue ? 'active' : ''}`}
                        title="Save Video to Read Later Queue"
                      >
                        {inQueue ? <BookmarkFilledIcon /> : <BookmarkIcon />}
                      </button>

                      <div className="thumbnail-badge-overlay-inner">
                        {item.badge}
                      </div>
                    </div>
                  </div>

                  {/* Card Meta Content details */}
                  <div className="card-details">
                    <div className="card-avatar" title={channel ? channel.title : "SignalFeed"}>
                      <ChannelAvatar channel={channel} initials={chInitials} />
                    </div>

                    <div className="card-info">
                      <h3 
                        className="card-title" 
                        onClick={() => handlePlayVideoWrapper(video)}
                        title={video.title}
                      >
                        {video.title}
                      </h3>

                      <div className="card-channel" title={channel ? channel.title : "Channel"}>
                        {channel ? channel.custom_name || channel.title : "Unknown Channel"}
                      </div>

                      <div className="card-meta">
                        <span>{formatPublishDate(video.publish_date)}</span>
                        {item.best_topic && item.best_topic !== "None" && (
                          <>
                            <span>•</span>
                            <span style={{ color: 'var(--text-secondary)' }}>{item.best_topic}</span>
                          </>
                        )}
                      </div>

                      {!calmMode && video.description && (
                        <p className="card-desc">{video.description}</p>
                      )}
                    </div>
                  </div>
                </div>
              );
            })
        )}
      </div>

      {/* local pagination fallback trigger button if scroll doesn't happen */}
      {filteredFeed.length > visibleCount && (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '24px 0 40px 0' }}>
          <button 
            onClick={() => setVisibleCount(prev => Math.min(prev + 12, feed.length))}
            style={{
              backgroundColor: 'var(--bg-card)',
              borderColor: 'var(--border-subtle)',
              color: 'var(--text-secondary)',
              fontSize: '0.85rem',
              padding: '8px 20px',
              cursor: 'pointer',
              borderRadius: '6px'
            }}
          >
            Show More Recommendations (Showing {visibleCount} of {filteredFeed.length})
          </button>
        </div>
      )}

      {/* Dynamic Scoring Diagnostics Overlay Inspector Drawer */}
      {explainData && (
        <div style={{
          position: 'fixed',
          top: 0,
          right: 0,
          width: '400px',
          height: '100vh',
          backgroundColor: 'var(--bg-surface)',
          borderLeft: '1px solid var(--border-subtle)',
          padding: '24px',
          zIndex: 3000,
          boxShadow: '-4px 0 20px rgba(0,0,0,0.5)',
          overflowY: 'auto'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
            <h3 style={{ fontSize: '0.85rem', textTransform: 'uppercase', color: 'var(--text-secondary)', letterSpacing: '0.04em' }}>Scoring Inspector</h3>
            <button onClick={() => setExplainData(null)} style={{ padding: '2px 8px' }}>✕ Close</button>
          </div>

          <h2 style={{ fontSize: '1.05rem', marginBottom: '8px', lineHeight: '1.3' }}>{explainData.video_title}</h2>
          <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '16px' }}>
            Channel: <strong>{explainData.channel_title}</strong>
          </p>

          <div style={{ 
            backgroundColor: 'var(--bg-main)', 
            border: '1px solid var(--border-subtle)', 
            borderRadius: '6px',
            padding: '16px',
            fontSize: '0.82rem',
            marginBottom: '20px'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 'bold', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '8px', marginBottom: '8px' }}>
              <span>Total Curation Score:</span>
              <span style={{ color: 'var(--success)' }}>{Math.round(explainData.final_calculated_score)} pts</span>
            </div>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <div style={{ display: 'flex', justifySelf: 'flex-start', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Trusted Boost (x{explainData.quality_score}):</span>
                <span>+{explainData.score_breakdown.trusted_boost}</span>
              </div>
              <div style={{ display: 'flex', justifySelf: 'flex-start', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Preference (x{explainData.preference_score}):</span>
                <span>+{explainData.score_breakdown.preference_boost}</span>
              </div>
              <div style={{ display: 'flex', justifySelf: 'flex-start', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Topic Affinity ('{explainData.best_topic_matched}'):</span>
                <span>+{explainData.score_breakdown.semantic_affinity}</span>
              </div>
              <div style={{ display: 'flex', justifySelf: 'flex-start', justifyContent: 'space-between', color: explainData.clickbait_score > 0 ? 'var(--danger)' : 'inherit' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Clickbait Deductions ({Math.round(explainData.clickbait_score * 100)}%):</span>
                <span>-{explainData.score_breakdown.clickbait_penalty}</span>
              </div>
              <div style={{ display: 'flex', justifySelf: 'flex-start', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Gravity Freshness Decay:</span>
                <span>+{explainData.score_breakdown.freshness_decay}</span>
              </div>
            </div>
          </div>

          <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
            <h4 style={{ fontSize: '0.8rem', color: 'var(--text-primary)', marginBottom: '6px' }}>Clickbait Telemetry Logs:</h4>
            {explainData.clickbait_reasons.length > 0 ? (
              <ul style={{ paddingLeft: '16px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                {explainData.clickbait_reasons.map((r, i) => (
                  <li key={i} style={{ color: 'var(--danger)' }}>Flagged: <strong>{r}</strong></li>
                ))}
              </ul>
            ) : (
              <span>Clean! Title matches zero clickbait emoji or uppercase abuse rules.</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
