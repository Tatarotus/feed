import React, { useState, useEffect } from 'react';
import { api } from '../utils/api';

export default function LikedVideosPage({ onPlayVideo }) {
  const [likedList, setLikedList] = useState([]);
  const [loading, setLoading] = useState(false);
  const [sortBy, setSortBy] = useState("newest");
  const [groupBy, setGroupBy] = useState("none"); // "none", "date", "channel", "topic"
  const [searchQuery, setSearchQuery] = useState("");
  
  // Pagination
  const [limit] = useState(24);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);

  const fetchLikedVideos = async (reset = false) => {
    setLoading(true);
    try {
      const currentOffset = reset ? 0 : offset;
      const data = await api.getLikedVideos(sortBy, searchQuery, limit, currentOffset);
      
      if (reset) {
        setLikedList(data);
        setOffset(limit);
      } else {
        setLikedList(prev => [...prev, ...data]);
        setOffset(currentOffset + limit);
      }
      
      if (data.length < limit) {
        setHasMore(false);
      } else {
        setHasMore(true);
      }
    } catch (e) {
      console.error("Failed to load liked videos:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLikedVideos(true);
  }, [sortBy, searchQuery]);

  const handleSearchChange = (e) => {
    setSearchQuery(e.target.value);
  };

  // Grouping helper
  const getGroupedList = () => {
    if (groupBy === "none") {
      return [{ title: "All Liked Videos", items: likedList }];
    }
    
    const groups = {};
    likedList.forEach(item => {
      let key = "Other";
      if (groupBy === "date") {
        try {
          const date = new Date(item.liked_at);
          key = date.toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
        } catch (e) {
          key = "Unknown Date";
        }
      } else if (groupBy === "channel") {
        key = item.channel?.custom_name || item.channel?.title || "Unknown Channel";
      } else if (groupBy === "topic") {
        key = item.source_bucket || "General Exploration";
      }
      
      if (!groups[key]) {
        groups[key] = [];
      }
      groups[key].push(item);
    });

    return Object.keys(groups).map(title => ({
      title,
      items: groups[title]
    }));
  };

  const groupedData = getGroupedList();

  return (
    <div style={{ padding: '24px', color: 'var(--text-primary)' }}>
      {/* Header section with styling */}
      <div style={{ display: 'flex', justifyContent: 'between', alignItems: 'center', flexWrap: 'wrap', gap: '16px', marginBottom: '24px', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '16px' }}>
        <div>
          <h2 style={{ fontSize: '1.4rem', fontWeight: 'bold', margin: 0, background: 'linear-gradient(135deg, #f4f4f5 30%, #a1a1aa 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
            Permanent Liked Videos
          </h2>
          <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', margin: '4px 0 0' }}>
            Semantic anchor repository storing historical preference memory and vector seeds.
          </p>
        </div>
        
        {/* Search bar */}
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <input 
            type="text" 
            placeholder="Search liked titles..." 
            value={searchQuery}
            onChange={handleSearchChange}
            style={{
              padding: '6px 12px',
              fontSize: '0.8rem',
              borderRadius: '6px',
              border: '1px solid var(--border-subtle)',
              background: 'var(--bg-card)',
              color: 'var(--text-primary)',
              outline: 'none',
              width: '200px'
            }}
          />
        </div>
      </div>

      {/* Control panel (Sorting + Grouping) */}
      <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', marginBottom: '24px', backgroundColor: 'var(--bg-surface)', padding: '12px 16px', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', fontWeight: '600' }}>Sort By:</span>
          <select 
            value={sortBy} 
            onChange={(e) => setSortBy(e.target.value)}
            style={{
              padding: '4px 8px',
              fontSize: '0.75rem',
              borderRadius: '4px',
              background: 'var(--bg-main)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border-subtle)',
              outline: 'none',
              cursor: 'pointer'
            }}
          >
            <option value="newest">Newest Liked</option>
            <option value="oldest">Oldest Liked</option>
            <option value="most_watched">Most Watched</option>
            <option value="semantic_similarity">Semantic Similarity</option>
          </select>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', fontWeight: '600' }}>Group By:</span>
          <select 
            value={groupBy} 
            onChange={(e) => setGroupBy(e.target.value)}
            style={{
              padding: '4px 8px',
              fontSize: '0.75rem',
              borderRadius: '4px',
              background: 'var(--bg-main)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border-subtle)',
              outline: 'none',
              cursor: 'pointer'
            }}
          >
            <option value="none">No Grouping</option>
            <option value="date">Date Liked</option>
            <option value="channel">Channel</option>
            <option value="topic">Semantic Topic</option>
          </select>
        </div>
      </div>

      {/* Grid displaying grouped/ungrouped data */}
      {likedList.length === 0 && !loading ? (
        <div style={{ textAlign: 'center', padding: '60px', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
          No liked videos found matching your filters. Permanent likes are stored when clicking the Like button.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
          {groupedData.map((group, gIdx) => (
            <div key={gIdx}>
              <h3 style={{ fontSize: '0.9rem', fontWeight: 'bold', textTransform: 'uppercase', color: 'var(--accent)', letterSpacing: '0.05em', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '6px', marginBottom: '16px' }}>
                {group.title} <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'none' }}>({group.items.length})</span>
              </h3>
              
              <div className="video-grid">
                {group.items.map((item) => {
                  const video = item.video;
                  const channel = item.channel;
                  const matchedTopic = item.source_bucket || "Exploration";
                  return (
                    <div 
                      key={item.id} 
                      className="video-card" 
                      onClick={() => onPlayVideo(video)}
                      style={{ cursor: 'pointer' }}
                    >
                      <div className="card-thumbnail-wrapper">
                        <img 
                          src={video.thumbnail_url || `https://i.ytimg.com/vi/${video.id}/hqdefault.jpg`} 
                          alt={video.title} 
                          className="card-thumbnail-img"
                        />
                        <div className="thumbnail-bottom-overlay">
                          <span className="badge semantic" style={{ border: '1px solid var(--border-subtle)', fontSize: '0.62rem', padding: '2px 6px', borderRadius: '4px', background: 'rgba(0,0,0,0.8)', color: 'var(--accent)' }}>
                            {matchedTopic}
                          </span>
                        </div>
                      </div>
                      
                      <div className="card-details-wrapper">
                        <h4 className="card-title" style={{ fontSize: '0.85rem', fontWeight: '600', lineHeight: '1.4', margin: '4px 0' }}>
                          {video.title}
                        </h4>
                        
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '6px' }}>
                          {channel?.thumbnail_url && (
                            <img 
                              src={channel.thumbnail_url} 
                              alt="" 
                              style={{ width: '16px', height: '16px', borderRadius: '50%' }}
                            />
                          )}
                          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                            {channel?.custom_name || channel?.title || "Unknown Channel"}
                          </span>
                        </div>
                        
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '8px', fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                          <span>Score: {Math.round(item.semantic_score * 100)}%</span>
                          <span>Liked: {new Date(item.liked_at).toLocaleDateString()}</span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination control */}
      {hasMore && likedList.length > 0 && (
        <div style={{ textAlign: 'center', marginTop: '32px' }}>
          <button 
            onClick={() => fetchLikedVideos(false)} 
            disabled={loading}
            style={{
              padding: '8px 24px',
              fontSize: '0.8rem',
              fontWeight: '600',
              borderRadius: '20px',
              border: '1px solid var(--border-subtle)',
              background: 'rgba(255,255,255,0.06)',
              color: 'var(--text-primary)',
              cursor: 'pointer',
              transition: 'background-color 0.2s'
            }}
            onMouseOver={(e) => e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.12)'}
            onMouseOut={(e) => e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.06)'}
          >
            {loading ? "Loading..." : "Load More Liked Videos"}
          </button>
        </div>
      )}
    </div>
  );
}
