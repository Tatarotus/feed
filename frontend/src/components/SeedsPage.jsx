import React, { useState, useEffect } from 'react';
import { api } from '../utils/api';

export default function SeedsPage({ onBack, onRefreshFeed }) {
  const [interests, setInterests] = useState([]);
  const [mutations, setMutations] = useState([]);
  const [loading, setLoading] = useState(false);
  const [expandedTopics, setExpandedTopics] = useState({});
  
  // Form states
  const [newTopic, setNewTopic] = useState("");
  const [seedUrl, setSeedUrl] = useState("");
  const [seedWeight, setSeedWeight] = useState(2.0);
  const [activeTab, setActiveTab] = useState("all"); // 'all', 'topics', 'seeds'

  const toggleExpanded = (topic) => {
    setExpandedTopics(prev => ({
      ...prev,
      [topic]: !prev[topic]
    }));
  };

  const groupedMutationTree = React.useMemo(() => {
    const gen2ByFirstGen = {};
    const gen1ByParent = {};

    mutations.forEach(m => {
      if (m.generation_depth === 1) {
        const parent = m.parent_topic;
        if (!gen1ByParent[parent]) {
          gen1ByParent[parent] = [];
        }
        gen1ByParent[parent].push(m);
      } else if (m.generation_depth === 2) {
        const firstGenTopic = m.parent_topic;
        if (!gen2ByFirstGen[firstGenTopic]) {
          gen2ByFirstGen[firstGenTopic] = [];
        }
        gen2ByFirstGen[firstGenTopic].push(m);
      }
    });

    return { gen1ByParent, gen2ByFirstGen };
  }, [mutations]);

  const loadInterests = async () => {
    setLoading(true);
    try {
      const [ints, muts] = await Promise.all([
        api.getInterests(),
        api.getMutations()
      ]);
      setInterests(ints);
      setMutations(muts || []);
    } catch (err) {
      console.error("Failed to load curation vectors and mutations:", err);
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
                  const isExpanded = !!expandedTopics[item.topic];

                  // Find mutation children using our memoized grouped tree
                  const childMutations = groupedMutationTree.gen1ByParent[item.topic] || [];

                  return (
                    <div 
                      key={item.id}
                      style={{
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '6px',
                        backgroundColor: 'var(--bg-card)',
                        border: '1px solid var(--border-subtle)',
                        padding: '12px',
                        borderRadius: '8px',
                        fontSize: '0.82rem',
                        transition: 'all 0.3s ease'
                      }}
                    >
                      {/* Parent Interest Row (become clickable for expansion) */}
                      <div 
                        onClick={() => toggleExpanded(item.topic)}
                        style={{ 
                          display: 'flex', 
                          alignItems: 'center', 
                          justifyContent: 'space-between', 
                          width: '100%',
                          cursor: 'pointer',
                          borderRadius: '6px',
                          padding: '4px 6px',
                          margin: '-4px -6px',
                          transition: 'background-color 0.2s ease',
                          WebkitTapHighlightColor: 'transparent',
                        }}
                        className="parent-interest-row"
                        onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.04)'}
                        onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
                          {/* Expansion arrow indicator */}
                          <span style={{ 
                            color: 'var(--text-muted)', 
                            fontSize: '0.7rem', 
                            fontFamily: 'monospace', 
                            userSelect: 'none',
                            display: 'inline-block',
                            transition: 'transform 0.2s ease',
                            transform: isExpanded ? 'rotate(90deg)' : 'none',
                            marginRight: '2px',
                            width: '10px',
                            textAlign: 'center'
                          }}>
                            ▶
                          </span>

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
                                fontWeight: isSeed ? '600' : 'bold',
                                color: 'var(--text-primary)',
                                maxWidth: '200px'
                              }}
                              title={displayText}
                            >
                              {displayText} {childMutations.length > 0 && (
                                <span style={{ color: 'var(--accent)', fontSize: '0.78rem', fontWeight: '500', marginLeft: '4px' }}>
                                  ({childMutations.length})
                                </span>
                              )}
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
                              onClick={(e) => {
                                e.stopPropagation();
                                handleAdjustWeight(item.id, item.weight, -0.5);
                              }}
                              style={{ padding: '2px 6px', fontSize: '0.75rem', lineHeight: '1', cursor: 'pointer', background: 'transparent', border: 'none', color: 'var(--text-secondary)' }}
                              title="Decrease weight influence"
                            >
                              −
                            </button>
                            <span style={{ fontSize: '0.76rem', fontWeight: '700', color: 'var(--text-primary)', minWidth: '32px', textAlign: 'center' }}>
                              {item.weight.toFixed(1)}x
                            </span>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleAdjustWeight(item.id, item.weight, 0.5);
                              }}
                              style={{ padding: '2px 6px', fontSize: '0.75rem', lineHeight: '1', cursor: 'pointer', background: 'transparent', border: 'none', color: 'var(--text-secondary)' }}
                              title="Increase weight influence"
                            >
                              +
                            </button>
                          </div>

                          {/* Remove button */}
                          <button 
                            onClick={(e) => {
                              e.stopPropagation();
                              handleRemoveInterest(item.id);
                            }}
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

                      {/* Mutation Children Tree view (with smooth height expansion & opacity transition) */}
                      <div style={{
                        maxHeight: isExpanded ? '1600px' : '0px',
                        opacity: isExpanded ? 1 : 0,
                        overflow: 'hidden',
                        transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
                        marginTop: isExpanded ? '6px' : '0px',
                        borderTop: isExpanded ? '1px solid rgba(255,255,255,0.04)' : 'none',
                        paddingTop: isExpanded ? '8px' : '0px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '6px'
                      }}>
                        {childMutations.length === 0 ? (
                          <div style={{ padding: '8px 12px', color: 'var(--text-muted)', fontSize: '0.72rem', fontStyle: 'italic', fontFamily: 'monospace' }}>
                            └── no active mutations evolved yet
                          </div>
                        ) : (
                          childMutations.map((m1, idx1) => {
                            const isLast1 = idx1 === childMutations.length - 1;
                            const branchChar1 = isLast1 ? "└── " : "├── ";
                            
                            // Find second-generation mutations
                            const secondGenMuts = groupedMutationTree.gen2ByFirstGen[m1.mutation_topic] || [];

                            // Calculate dynamic glow and opacity based on energy economy
                            const energy1 = m1.energy || 1.0;
                            const fatigue1 = m1.fatigue_multiplier || 1.0;
                            const glowSize1 = Math.min(20, 2 + energy1 * 3);
                            
                            // Visual state styles based on status and economy metrics
                            let opacityVal1 = Math.max(0.70, Math.min(1.0, 0.70 + (energy1 / 3.0) * 0.30));
                            let borderStyle1 = '1px solid rgba(255, 255, 255, 0.05)';
                            let bgStyle1 = 'rgba(255,255,255,0.02)';
                            let textCol1 = 'var(--text-primary)';
                            let glowColor1 = m1.status === 'promoted' ? '34, 197, 94' : '37, 99, 235';
                            const isDecaying1 = m1.confidence_score < 0.20;

                            if (isDecaying1) {
                              opacityVal1 = 0.75;
                              borderStyle1 = '1px dashed rgba(239, 68, 68, 0.3)';
                              bgStyle1 = 'rgba(239, 68, 68, 0.05)';
                              textCol1 = 'var(--text-secondary)';
                            } else if (m1.status === 'promoted') {
                              borderStyle1 = '1px solid rgba(34, 197, 94, 0.25)';
                              bgStyle1 = 'rgba(34, 197, 94, 0.07)';
                              textCol1 = '#22c55e';
                            } else {
                              // Experimental / standard mutation state (soft purple/blue)
                              borderStyle1 = '1px solid rgba(139, 92, 246, 0.18)';
                              bgStyle1 = 'rgba(139, 92, 246, 0.03)';
                              glowColor1 = '139, 92, 246';
                            }

                            const hasGlow1 = !isDecaying1 && (energy1 > 1.5 || m1.status === 'promoted');
                            const boxShadowStyle1 = hasGlow1 
                              ? `0 0 ${glowSize1}px rgba(${glowColor1}, 0.15)`
                              : 'none';

                            return (
                              <div key={m1.id} style={{ display: 'flex', flexDirection: 'column', gap: '4px', opacity: opacityVal1, transition: 'all 0.3s ease' }}>
                                {/* First generation child row */}
                                <div style={{
                                  display: 'flex',
                                  alignItems: 'center',
                                  justifyContent: 'space-between',
                                  padding: '6px 8px',
                                  borderRadius: '6px',
                                  fontSize: '0.75rem',
                                  backgroundColor: bgStyle1,
                                  border: borderStyle1,
                                  boxShadow: boxShadowStyle1,
                                  transition: 'all 0.3s ease'
                                }}>
                                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px', minWidth: 0 }}>
                                    <span style={{ fontFamily: 'monospace', color: 'var(--text-muted)', whiteSpace: 'pre' }}>{branchChar1}</span>
                                    <span style={{ 
                                      fontWeight: m1.status === 'promoted' ? '600' : 'normal',
                                      color: textCol1,
                                      whiteSpace: 'nowrap',
                                      overflow: 'hidden',
                                      textOverflow: 'ellipsis',
                                      maxWidth: '180px'
                                    }}>
                                      {m1.mutation_topic}
                                    </span>
                                    <span style={{
                                      fontSize: '0.58rem',
                                      padding: '1px 5px',
                                      borderRadius: '8px',
                                      backgroundColor: m1.status === 'promoted' ? 'rgba(34, 197, 94, 0.2)' : 'rgba(255,255,255,0.06)',
                                      color: m1.status === 'promoted' ? '#22c55e' : 'var(--text-muted)',
                                      marginLeft: '4px',
                                      fontWeight: '600'
                                    }}>
                                      {m1.status.toUpperCase()}
                                    </span>
                                    {isDecaying1 && (
                                      <span style={{ fontSize: '0.55rem', color: '#ef4444', fontStyle: 'italic', marginLeft: '4px' }}>
                                        (decaying)
                                      </span>
                                    )}
                                  </div>

                                  {/* Stats */}
                                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                                    <span title="Confidence Score" style={{ cursor: 'help' }}>🎯 {(m1.confidence_score * 100).toFixed(0)}%</span>
                                    <span title="Telemetry Score" style={{ cursor: 'help', color: m1.telemetry_score >= 0 ? '#22c55e' : '#ef4444' }}>
                                      📊 {m1.telemetry_score >= 0 ? `+${m1.telemetry_score.toFixed(2)}` : m1.telemetry_score.toFixed(2)}
                                    </span>
                                    <span title="Survival Health" style={{ cursor: 'help' }}>❤️ {(m1.survival_score * 100).toFixed(0)}%</span>
                                  </div>
                                </div>

                                {/* First gen Energy Economy Details Row */}
                                <div style={{
                                  display: 'flex',
                                  flexWrap: 'wrap',
                                  gap: '12px',
                                  fontSize: '0.66rem',
                                  color: 'var(--text-muted)',
                                  marginTop: '1px',
                                  marginBottom: '4px',
                                  paddingLeft: '24px',
                                  fontFamily: 'monospace'
                                }}>
                                  <span title="Ecosystem Energy Level" style={{ color: energy1 >= 2.0 ? '#fbbf24' : 'var(--text-muted)' }}>⚡ Energy: {energy1.toFixed(1)}</span>
                                  <span title="Cluster Attention Share">🧠 Attention: {((m1.attention_share || 0.0) * 100).toFixed(0)}%</span>
                                  <span title="Semantic Fatigue Modifier" style={{ color: fatigue1 < 0.8 ? '#ef4444' : 'var(--text-muted)' }}>🔥 Fatigue: {((1.0 - fatigue1) * 100).toFixed(0)}%</span>
                                  <span title="Competition Cluster Rank" style={{ color: m1.competition_score === 1 ? '#3b82f6' : 'var(--text-muted)' }}>📈 Rank #{m1.competition_score ? m1.competition_score.toFixed(0) : '1'}</span>
                                </div>

                                {/* Second generation grandchild rows */}
                                {secondGenMuts.length > 0 && (
                                  <div style={{
                                    marginLeft: '20px',
                                    paddingLeft: '0px',
                                    display: 'flex',
                                    flexDirection: 'column',
                                    gap: '4px',
                                    marginTop: '2px',
                                    marginBottom: '6px'
                                  }}>
                                    {secondGenMuts.map((m2, idx2) => {
                                      const isLast2 = idx2 === secondGenMuts.length - 1;
                                      const prefix = isLast1 ? "    " : "│   ";
                                      const branchChar2 = prefix + (isLast2 ? "└── " : "├── ");

                                      const energy2 = m2.energy || 1.0;
                                      const fatigue2 = m2.fatigue_multiplier || 1.0;
                                      const isDecaying2 = m2.confidence_score < 0.20;

                                      let opacityVal2 = Math.max(0.70, Math.min(1.0, 0.70 + (energy2 / 3.0) * 0.30));
                                      let borderStyle2 = 'none';
                                      let bgStyle2 = 'transparent';
                                      let textCol2 = 'var(--text-secondary)';

                                      if (isDecaying2) {
                                        opacityVal2 = 0.75;
                                        bgStyle2 = 'rgba(239, 68, 68, 0.03)';
                                        textCol2 = 'var(--text-secondary)';
                                      } else if (m2.status === 'promoted') {
                                        borderStyle2 = '1px solid rgba(34, 197, 94, 0.15)';
                                        bgStyle2 = 'rgba(34, 197, 94, 0.04)';
                                        textCol2 = '#22c55e';
                                      }

                                      return (
                                        <div key={m2.id} style={{ display: 'flex', flexDirection: 'column', gap: '2px', opacity: opacityVal2 }}>
                                          <div 
                                            style={{
                                              display: 'flex',
                                              alignItems: 'center',
                                              justifyContent: 'space-between',
                                              padding: '4px 6px',
                                              borderRadius: '4px',
                                              fontSize: '0.7rem',
                                              backgroundColor: bgStyle2,
                                              border: borderStyle2,
                                              transition: 'all 0.3s ease'
                                            }}
                                          >
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '4px', minWidth: 0 }}>
                                              <span style={{ fontFamily: 'monospace', color: 'var(--text-muted)', whiteSpace: 'pre' }}>{branchChar2}</span>
                                              <span style={{ 
                                                color: textCol2,
                                                whiteSpace: 'nowrap',
                                                overflow: 'hidden',
                                                textOverflow: 'ellipsis',
                                                maxWidth: '160px'
                                              }}>
                                                {m2.mutation_topic}
                                              </span>
                                              <span style={{ fontSize: '0.58rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                                                (2nd gen)
                                              </span>
                                            </div>

                                            {/* Grandchild Stats */}
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.64rem', color: 'var(--text-muted)' }}>
                                              <span title="Confidence Score">🎯 {(m2.confidence_score * 100).toFixed(0)}%</span>
                                              <span title="Telemetry Score" style={{ color: m2.telemetry_score >= 0 ? '#22c55e' : '#ef4444' }}>
                                                📊 {m2.telemetry_score >= 0 ? `+${m2.telemetry_score.toFixed(2)}` : m2.telemetry_score.toFixed(2)}
                                              </span>
                                              <span title="Survival Health">❤️ {(m2.survival_score * 100).toFixed(0)}%</span>
                                            </div>
                                          </div>

                                          {/* Second gen Energy Details Row */}
                                          <div style={{
                                            display: 'flex',
                                            flexWrap: 'wrap',
                                            gap: '10px',
                                            fontSize: '0.62rem',
                                            color: 'var(--text-muted)',
                                            paddingLeft: '44px',
                                            fontFamily: 'monospace',
                                            marginBottom: '3px'
                                          }}>
                                            <span title="Energy">⚡ Energy: {energy2.toFixed(1)}</span>
                                            <span title="Attention">🧠 Attention: {((m2.attention_share || 0.0) * 100).toFixed(0)}%</span>
                                            <span title="Fatigue" style={{ color: fatigue2 < 0.8 ? '#ef4444' : 'inherit' }}>🔥 Fatigue: {((1.0 - fatigue2) * 100).toFixed(0)}%</span>
                                            <span title="Rank">📈 Rank #{m2.competition_score ? m2.competition_score.toFixed(0) : '1'}</span>
                                          </div>
                                        </div>
                                      );
                                    })}
                                  </div>
                                )}
                              </div>
                            );
                          })
                        )}
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
