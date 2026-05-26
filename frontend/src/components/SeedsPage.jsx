import React, { useState, useEffect } from 'react';
import { api } from '../utils/api';

export default function SeedsPage({ onBack, onRefreshFeed }) {
  const [interests, setInterests] = useState([]);
  const [loading, setLoading] = useState(false);
  
  // Form states
  const [newTopic, setNewTopic] = useState("");
  const [seedUrl, setSeedUrl] = useState("");
  const [seedWeight, setSeedWeight] = useState(2.0);
  const [activeTab, setActiveTab] = useState("all"); // 'all', 'topics', 'seeds'

  const loadInterests = async () => {
    setLoading(true);
    try {
      const ints = await api.getInterests();
      setInterests(ints);
    } catch (err) {
      console.error("Failed to load curation vectors:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadInterests();
  }, []);

  const handleAddTopic = async (e) => {
    e.preventDefault();
    if (!newTopic.trim()) return;

    try {
      await api.followTopic(newTopic.trim());
      setNewTopic("");
      await loadInterests();
      onRefreshFeed();
    } catch (err) {
      alert(`Follow topic failure: ${err.message}`);
    }
  };

  const handleAddManualSeed = async (e) => {
    e.preventDefault();
    if (!seedUrl.trim()) return;

    setLoading(true);
    try {
      await api.addManualSeed({
        url: seedUrl.trim(),
        weight: parseFloat(seedWeight)
      });
      setSeedUrl("");
      setSeedWeight(2.0);
      await loadInterests();
      onRefreshFeed();
      alert("Manual training seed successfully injected! The system fetched metadata and generated semantic embeddings in the background.");
    } catch (err) {
      alert(`Seed injection failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleRemoveInterest = async (id) => {
    try {
      await api.unfollowTopic(id);
      await loadInterests();
      onRefreshFeed();
    } catch (err) {
      alert(`Remove failed: ${err.message}`);
    }
  };

  const handleAdjustWeight = async (id, currentWeight, delta) => {
    const nextWeight = Math.min(Math.max(currentWeight + delta, 0.1), 5.0);
    try {
      await api.updateInterestWeight(id, { weight: nextWeight });
      await loadInterests();
      onRefreshFeed();
    } catch (err) {
      alert(`Weight update failed: ${err.message}`);
    }
  };

  const standardTopics = interests.filter(item => !item.topic.startsWith("Seed:"));
  const manualSeeds = interests.filter(item => item.topic.startsWith("Seed:"));

  return (
    <div style={{
      padding: '24px',
      maxWidth: '1000px',
      margin: '0 auto',
      color: 'var(--text-primary)'
    }}>
      {/* Premium Back navigation header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: '28px',
        borderBottom: '1px solid var(--border-subtle)',
        paddingBottom: '16px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <button 
            onClick={onBack}
            style={{
              background: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '50%',
              width: '40px',
              height: '40px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '1.2rem',
              cursor: 'pointer',
              color: 'var(--text-primary)',
              transition: 'background 0.2s'
            }}
            title="Back to Feed"
          >
            ←
          </button>
          <div>
            <h1 style={{ fontSize: '1.5rem', fontWeight: '700', margin: 0 }}>Curation Vectors</h1>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '4px 0 0 0' }}>
              Add semantic interest terms or inject manual training seeds to shape your recommendations
            </p>
          </div>
        </div>

        {/* Tab filters */}
        <div style={{ display: 'flex', gap: '8px' }}>
          {['all', 'topics', 'seeds'].map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              style={{
                padding: '6px 14px',
                borderRadius: '16px',
                fontSize: '0.75rem',
                fontWeight: '600',
                textTransform: 'capitalize',
                background: activeTab === tab ? 'var(--accent)' : 'rgba(255,255,255,0.05)',
                border: activeTab === tab ? 'none' : '1px solid var(--border-subtle)',
                color: activeTab === tab ? '#fff' : 'var(--text-secondary)',
                cursor: 'pointer'
              }}
            >
              {tab} ({tab === 'all' ? interests.length : tab === 'topics' ? standardTopics.length : manualSeeds.length})
            </button>
          ))}
        </div>
      </div>

      {/* Grid Layout splits forms from current vectors list */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: '24px',
        alignItems: 'start'
      }}>
        {/* Left Column: Form inputs */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Card 1: Add standard topic */}
          {(activeTab === 'all' || activeTab === 'topics') && (
            <div style={{
              background: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '8px',
              padding: '20px'
            }}>
              <h2 style={{ fontSize: '1rem', fontWeight: '600', marginBottom: '12px', marginTop: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
                🏷️ Add Interest Topic
              </h2>
              <p style={{ fontSize: '0.76rem', color: 'var(--text-muted)', marginBottom: '16px' }}>
                Enter keywords or concepts you want to prioritize in your feed. The system uses pgvector to find semantically relevant content.
              </p>
              <form onSubmit={handleAddTopic} style={{ display: 'flex', gap: '8px' }}>
                <input 
                  type="text" 
                  value={newTopic}
                  onChange={(e) => setNewTopic(e.target.value)}
                  placeholder="e.g. quantum computing, rust programming..."
                  style={{
                    flex: 1,
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: '6px',
                    padding: '8px 12px',
                    fontSize: '0.8rem',
                    color: 'var(--text-primary)'
                  }}
                />
                <button type="submit" className="primary" style={{ padding: '8px 16px', borderRadius: '6px', fontSize: '0.8rem' }}>
                  Add Topic
                </button>
              </form>
            </div>
          )}

          {/* Card 2: Add manual training seed */}
          {(activeTab === 'all' || activeTab === 'seeds') && (
            <div style={{
              background: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '8px',
              padding: '20px'
            }}>
              <h2 style={{ fontSize: '1rem', fontWeight: '600', marginBottom: '12px', marginTop: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
                ⭐ Inject Manual Training Seed
              </h2>
              <p style={{ fontSize: '0.76rem', color: 'var(--text-muted)', marginBottom: '16px' }}>
                Seed your feed with a video you enjoyed in the past. Just paste the YouTube URL, and the system will automatically fetch the video's details and generate semantic training vectors.
              </p>
              <form onSubmit={handleAddManualSeed} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <input 
                  type="url" 
                  value={seedUrl}
                  onChange={(e) => setSeedUrl(e.target.value)}
                  placeholder="YouTube Video URL (e.g. https://www.youtube.com/watch?v=...)"
                  required
                  style={{
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: '6px',
                    padding: '10px 14px',
                    fontSize: '0.82rem',
                    color: 'var(--text-primary)'
                  }}
                />
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Seed Weight Influence:</span>
                  <select 
                    value={seedWeight} 
                    onChange={(e) => setSeedWeight(parseFloat(e.target.value))}
                    style={{
                      background: 'var(--bg-card)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: '6px',
                      padding: '6px 12px',
                      fontSize: '0.8rem',
                      color: 'var(--text-primary)'
                    }}
                  >
                    <option value="1.0">Standard Weight (1.0x)</option>
                    <option value="2.0">Strong Seed (2.0x)</option>
                    <option value="3.0">Heavy Influence (3.0x)</option>
                  </select>
                </div>
                <button type="submit" className="primary" style={{ padding: '10px 16px', borderRadius: '6px', fontSize: '0.82rem', fontWeight: '600' }} disabled={loading}>
                  {loading ? "Fetching Metadata & Embedding..." : "🚀 Inject Training Seed"}
                </button>
              </form>
            </div>
          )}
        </div>

        {/* Right Column: Interactive List of all active vectors */}
        <div style={{
          background: 'var(--bg-surface)',
          border: '1px solid var(--border-subtle)',
          borderRadius: '8px',
          padding: '20px',
          maxHeight: '70vh',
          overflowY: 'auto'
        }}>
          <h2 style={{ fontSize: '1rem', fontWeight: '600', marginBottom: '16px', marginTop: 0 }}>
            Active Vectors & Weights
          </h2>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {interests.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '40px 20px', color: 'var(--text-muted)' }}>
                <span style={{ fontSize: '2rem' }}>📡</span>
                <p style={{ fontSize: '0.8rem', marginTop: '12px' }}>No curation vectors yet. Add your first interest above!</p>
              </div>
            ) : (
              interests
                .filter(item => {
                  if (activeTab === 'topics') return !item.topic.startsWith("Seed:");
                  if (activeTab === 'seeds') return item.topic.startsWith("Seed:");
                  return true;
                })
                .map(item => {
                  const isSeed = item.topic.startsWith("Seed:");
                  const displayText = isSeed ? item.topic.substring(5) : item.topic;

                  return (
                    <div 
                      key={item.id}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        backgroundColor: 'var(--bg-card)',
                        border: '1px solid var(--border-subtle)',
                        padding: '10px 14px',
                        borderRadius: '6px',
                        fontSize: '0.82rem'
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0 }}>
                        {isSeed ? (
                          <span style={{ color: 'var(--warning)', fontSize: '1.1rem', flexShrink: 0 }} title="Manual Video Seed">
                            ⭐
                          </span>
                        ) : (
                          <span style={{ color: 'var(--text-muted)', fontSize: '1rem', flexShrink: 0 }} title="Followed Topic">
                            🏷️
                          </span>
                        )}
                        <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
                          <span 
                            style={{ 
                              whiteSpace: 'nowrap', 
                              overflow: 'hidden', 
                              textOverflow: 'ellipsis',
                              fontWeight: isSeed ? '600' : 'normal',
                              color: isSeed ? 'var(--text-primary)' : 'var(--text-secondary)',
                              maxWidth: '220px'
                            }}
                            title={displayText}
                          >
                            {displayText}
                          </span>
                          <span style={{ fontSize: '0.64rem', color: 'var(--text-muted)' }}>
                            {isSeed ? 'Algorithmic Seed' : 'Interest Keyword'}
                          </span>
                        </div>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        {/* Adjust weights */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', backgroundColor: 'rgba(255,255,255,0.02)', borderRadius: '4px', padding: '2px' }}>
                          <button
                            onClick={() => handleAdjustWeight(item.id, item.weight, -0.5)}
                            style={{ padding: '2px 6px', fontSize: '0.75rem', lineHeight: '1', cursor: 'pointer' }}
                            title="Decrease weight influence"
                          >
                            −
                          </button>
                          <span style={{ fontSize: '0.76rem', fontWeight: '700', color: 'var(--text-primary)', minWidth: '32px', textAlign: 'center' }}>
                            {item.weight.toFixed(1)}x
                          </span>
                          <button
                            onClick={() => handleAdjustWeight(item.id, item.weight, 0.5)}
                            style={{ padding: '2px 6px', fontSize: '0.75rem', lineHeight: '1', cursor: 'pointer' }}
                            title="Increase weight influence"
                          >
                            +
                          </button>
                        </div>

                        {/* Remove button */}
                        <button 
                          onClick={() => handleRemoveInterest(item.id)}
                          style={{
                            background: 'transparent',
                            border: 'none',
                            cursor: 'pointer',
                            color: 'var(--danger)',
                            fontWeight: 'bold',
                            fontSize: '1.2rem',
                            padding: '4px 8px',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center'
                          }}
                          title="Remove vector"
                        >
                          ×
                        </button>
                      </div>
                    </div>
                  );
                })
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
