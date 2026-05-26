import React, { useState, useEffect, useRef } from 'react';
import { api } from '../utils/api';

export default function ChannelConfig({ onSyncComplete, serendipity = 0.2, onSerendipityChange, onManageSeeds }) {
  const [channels, setChannels] = useState([]);
  const [newChanId, setNewChanId] = useState("");
  
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(null);

  const dialRef = useRef(null);
  const [isDragging, setIsDragging] = useState(false);

  const handleDrag = (clientX, clientY, rect) => {
    const x = clientX - rect.left - 90;
    const y = clientY - rect.top - 90;
    
    let angle = Math.atan2(y, x);
    let angleDeg = (angle * 180) / Math.PI;
    if (angleDeg < 0) {
      angleDeg += 360;
    }
    
    let relativeAngle = angleDeg - 135;
    if (relativeAngle < 0) {
      relativeAngle += 360;
    }
    
    let rawValue = 0.05;
    if (angleDeg > 45 && angleDeg < 135) {
      if (angleDeg > 90) {
        rawValue = 0.05;
      } else {
        rawValue = 0.60;
      }
    } else {
      const progress = Math.min(Math.max(relativeAngle / 270, 0), 1);
      rawValue = 0.05 + progress * (0.60 - 0.05);
    }
    
    const levels = [0.05, 0.20, 0.40, 0.60];
    const closest = levels.reduce((prev, curr) => 
      Math.abs(curr - rawValue) < Math.abs(prev - rawValue) ? curr : prev
    );
    
    onSerendipityChange(closest);
  };

  const handleMouseDown = (e) => {
    setIsDragging(true);
    if (dialRef.current) {
      const rect = dialRef.current.getBoundingClientRect();
      handleDrag(e.clientX, e.clientY, rect);
    }
  };

  const handleTouchStart = (e) => {
    setIsDragging(true);
    if (dialRef.current && e.touches[0]) {
      const rect = dialRef.current.getBoundingClientRect();
      handleDrag(e.touches[0].clientX, e.touches[0].clientY, rect);
    }
  };

  useEffect(() => {
    const handleMouseMove = (e) => {
      if (!isDragging) return;
      if (dialRef.current) {
        const rect = dialRef.current.getBoundingClientRect();
        handleDrag(e.clientX, e.clientY, rect);
      }
    };

    const handleTouchMove = (e) => {
      if (!isDragging) return;
      if (dialRef.current && e.touches[0]) {
        const rect = dialRef.current.getBoundingClientRect();
        handleDrag(e.touches[0].clientX, e.touches[0].clientY, rect);
      }
    };

    const handleMouseUp = () => {
      setIsDragging(false);
    };

    if (isDragging) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
      window.addEventListener('touchmove', handleTouchMove);
      window.addEventListener('touchend', handleMouseUp);
    }

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
      window.removeEventListener('touchmove', handleTouchMove);
      window.removeEventListener('touchend', handleMouseUp);
    };
  }, [isDragging]);

  const loadSettings = async () => {
    setLoading(true);
    try {
      const chans = await api.getChannels();
      setChannels(chans);
    } catch (err) {
      console.error("Failed to load settings options:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSettings();
  }, []);

  const handleAddChannel = async (e) => {
    e.preventDefault();
    if (!newChanId) return;
    
    setActionLoading("subscribing");
    try {
      await api.createChannel({
        id: newChanId.trim(),
        is_trusted: true,
        provider: "rss"
      });
      setNewChanId("");
      await loadSettings();
      onSyncComplete();
    } catch (err) {
      alert(`Subscribe failure: ${err.message}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleToggleTrust = async (channel) => {
    try {
      await api.updateChannel(channel.id, { is_trusted: !channel.is_trusted });
      await loadSettings();
      onSyncComplete();
    } catch (err) {
      alert(`Failed to update channel settings: ${err.message}`);
    }
  };

  const handleAdjustPreference = async (channel, delta) => {
    const newPref = Math.max(0.1, Math.min(3.0, Math.round((channel.preference_score + delta) * 10) / 10));
    try {
      await api.updateChannel(channel.id, { preference_score: newPref });
      await loadSettings();
      onSyncComplete();
    } catch (err) {
      console.error(err);
    }
  };

  const handleDeleteChannel = async (channelId) => {
    if (!confirm("Are you sure you want to unsubscribe from this channel? All cached video recommendations will be removed.")) return;
    try {
      await api.deleteChannel(channelId);
      await loadSettings();
      onSyncComplete();
    } catch (err) {
      alert(err.message);
    }
  };

  // Calculate drag handle coordinates on circular track (radius = 74, center = 90)
  const progress = (serendipity - 0.05) / (0.60 - 0.05);
  const handleAngleDeg = 135 + progress * 270;
  const handleAngleRad = (handleAngleDeg * Math.PI) / 180;
  const handleX = 90 + 74 * Math.cos(handleAngleRad);
  const handleY = 90 + 74 * Math.sin(handleAngleRad);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* 1. Panel Header Title */}
      <div className="panel-header">
        <span className="panel-title">Curation Config</span>
      </div>

      <div className="scroll-section" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        
        {/* 1.5. Serendipity Thermostat Dial */}
        <div style={{ 
          display: 'flex', 
          flexDirection: 'column', 
          alignItems: 'center', 
          paddingBottom: '16px', 
          borderBottom: '1px solid var(--border-subtle)',
          position: 'relative'
        }}>
          <h3 style={{ 
            fontSize: '0.78rem', 
            fontWeight: '700', 
            textTransform: 'uppercase', 
            color: 'var(--text-muted)',
            marginBottom: '16px',
            letterSpacing: '0.05em'
          }}>
            Curation Serendipity
          </h3>
          
          <div 
            ref={dialRef}
            className="thermostat-dial"
            onMouseDown={handleMouseDown}
            onTouchStart={handleTouchStart}
            style={{ cursor: isDragging ? 'grabbing' : 'pointer' }}
            title="Drag the circular thermostat dial to adjust Curation Serendipity"
          >
            <svg width="180" height="180" style={{ position: 'absolute', top: '0', left: '0', pointerEvents: 'none', zIndex: 30 }}>
              <circle 
                cx="90" 
                cy="90" 
                r="74" 
                fill="none" 
                stroke="var(--border-subtle)" 
                strokeWidth="6" 
                strokeDasharray={2 * Math.PI * 74}
                strokeDashoffset={2 * Math.PI * 74 * 0.25}
                strokeLinecap="round"
                style={{ transform: 'rotate(135deg)', transformOrigin: '90px 90px' }}
              />
              <circle 
                cx="90" 
                cy="90" 
                r="74" 
                fill="none" 
                stroke="var(--accent)" 
                strokeWidth="8" 
                strokeDasharray={2 * Math.PI * 74}
                strokeDashoffset={2 * Math.PI * 74 * (1 - progress * 0.75)}
                strokeLinecap="round"
                style={{ 
                  transform: 'rotate(135deg)', 
                  transformOrigin: '90px 90px',
                  transition: 'stroke-dashoffset 0.25s cubic-bezier(0.4, 0, 0.2, 1), stroke 0.25s ease'
                }}
              />
              {/* Circular knob/handle on the tip of the arc */}
              <circle 
                cx={handleX} 
                cy={handleY} 
                r="9" 
                fill="var(--accent)" 
                stroke="#ffffff" 
                strokeWidth="2.5"
                style={{ 
                  filter: 'drop-shadow(0 2px 4px rgba(0,0,0,0.4))',
                  transition: 'cx 0.25s cubic-bezier(0.4, 0, 0.2, 1), cy 0.25s cubic-bezier(0.4, 0, 0.2, 1)'
                }}
              />
            </svg>
            
            <div className="thermostat-face" style={{ pointerEvents: 'none' }}>
              <span className="thermostat-pct">
                {Math.round(serendipity * 100)}%
              </span>
              <span className="thermostat-label">
                {serendipity <= 0.05 ? "Conservative" : 
                 serendipity <= 0.2 ? "Balanced" : 
                 serendipity <= 0.4 ? "High Discovery" : "Serendipitous"}
              </span>
              <span className="thermostat-sublabel">
                Discovery
              </span>
            </div>
          </div>
        </div>

        {/* 2. Manage Curation Vectors Pill Button */}
        <div style={{ borderBottom: '1px solid var(--border-subtle)', paddingBottom: '20px' }}>
          <button
            onClick={onManageSeeds}
            style={{
              width: '100%',
              background: 'rgba(255, 255, 255, 0.08)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '20px',
              padding: '10px 16px',
              fontSize: '0.8rem',
              fontWeight: '600',
              color: 'var(--text-primary)',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
              transition: 'background-color 0.2s, transform 0.1s',
              outline: 'none'
            }}
            onMouseOver={(e) => e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.15)'}
            onMouseOut={(e) => e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.08)'}
            onMouseDown={(e) => e.currentTarget.style.transform = 'scale(0.98)'}
            onMouseUp={(e) => e.currentTarget.style.transform = 'scale(1)'}
          >
            📡 Manage Topics & Seeds
          </button>
        </div>

        {/* 3. Subscriptions Segment */}
        <div>
          <h3 className="sidebar-section-header">
            Subscribe to Channel
          </h3>
          <form onSubmit={handleAddChannel} style={{ display: 'flex', gap: '6px', marginBottom: '16px' }}>
            <input 
              type="text" 
              value={newChanId}
              onChange={(e) => setNewChanId(e.target.value)}
              placeholder="YouTube URL, @handle, or ID..."
              required
              disabled={actionLoading === "subscribing"}
              style={{ 
                flex: 1, 
                padding: '6px 10px', 
                fontSize: '0.75rem', 
                borderRadius: '4px', 
                border: '1px solid var(--border-subtle)', 
                background: 'var(--bg-main)', 
                color: 'var(--text-primary)',
                outline: 'none'
              }}
            />
            <button 
              type="submit" 
              disabled={actionLoading === "subscribing"}
              style={{ 
                padding: '6px 12px', 
                fontSize: '0.75rem', 
                borderRadius: '4px', 
                border: '1px solid var(--border-subtle)', 
                background: 'rgba(255, 255, 255, 0.08)', 
                color: 'var(--text-primary)', 
                cursor: 'pointer',
                transition: 'background-color 0.2s'
              }}
              onMouseOver={(e) => e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.15)'}
              onMouseOut={(e) => e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.08)'}
            >
              {actionLoading === "subscribing" ? "Adding..." : "Add"}
            </button>
          </form>
        </div>

        {/* 4. Subscriptions weights configuration */}
        <div>
          <h3 className="sidebar-section-header">
            Subscribed Channels ({channels.length})
          </h3>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {channels.map(channel => (
              <div 
                key={channel.id}
                style={{
                  backgroundColor: 'var(--bg-card)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '6px',
                  padding: '8px 10px'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '4px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', minWidth: 0, flex: 1 }}>
                    {channel.thumbnail_url ? (
                      <img 
                        src={channel.thumbnail_url} 
                        alt="" 
                        style={{ width: '18px', height: '18px', borderRadius: '50%', objectFit: 'cover', flexShrink: 0 }} 
                        onError={(e) => { e.target.style.display = 'none'; }}
                      />
                    ) : (
                      <div style={{ width: '18px', height: '18px', borderRadius: '50%', backgroundColor: 'var(--border-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.55rem', fontWeight: 'bold', color: 'var(--text-muted)', flexShrink: 0 }}>
                        {(channel.custom_name || channel.title).substring(0, 1).toUpperCase()}
                      </div>
                    )}
                    <span 
                      style={{ 
                        fontSize: '0.78rem', 
                        fontWeight: '600', 
                        color: 'var(--text-primary)',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}
                      title={channel.custom_name || channel.title}
                    >
                      {channel.custom_name || channel.title}
                    </span>
                  </div>
                  <span 
                    onClick={() => handleDeleteChannel(channel.id)}
                    style={{ fontSize: '0.7rem', color: 'var(--text-muted)', cursor: 'pointer', flexShrink: 0 }}
                    title="Unsubscribe from channel feed"
                  >
                    Unsub
                  </span>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '6px', fontSize: '0.68rem' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}>
                    <input 
                      type="checkbox"
                      checked={channel.is_trusted}
                      onChange={() => handleToggleTrust(channel)}
                      style={{ cursor: 'pointer' }}
                    />
                    <span style={{ color: 'var(--text-secondary)' }}>Trusted</span>
                  </label>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <button 
                      onClick={() => handleAdjustPreference(channel, -0.1)}
                      style={{ padding: '0 4px', fontSize: '0.65rem' }}
                    >
                      -
                    </button>
                    <span style={{ fontWeight: '700', color: 'var(--text-primary)', minWidth: '32px', textAlign: 'center' }}>{channel.preference_score.toFixed(1)}x</span>
                    <button 
                      onClick={() => handleAdjustPreference(channel, 0.1)}
                      style={{ padding: '0 4px', fontSize: '0.65rem' }}
                    >
                      +
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  );
}
