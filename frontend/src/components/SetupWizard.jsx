import React, { useState } from 'react';
import { api } from '../utils/api';

const CURATED_PACKS = {
  ai_ml: {
    name: "AI & Local Models",
    description: "Deep learning, local LLMs, quantization, and papers.",
    channels: [
      { id: "UCBNCLEeP2v_N-cR3JqL_yGg", title: "Two Minute Papers" },
      { id: "UC517c2fQ2qJ88x59Yp_C8Ew", title: "David Ondrej" },
      { id: "UCZHmQk67mSJgfCCTn7xBfew", title: "Yannic Kilcher" },
      { id: "UCsBjURrPoezykLs9EqgamOA", title: "Fireship" }
    ]
  },
  systems_linux: {
    name: "Linux & Hardcore Systems",
    description: "Linux administration, networking, edge inference, and homelabs.",
    channels: [
      { id: "UCm5mt-A4w61lknZ9lCsZtBw", title: "Level1Techs" },
      { id: "UC_0CVCfC_3iuHqmyClu59Uw", title: "ETA PRIME" },
      { id: "UC8ENHE5xdFSwx71u3fDH5Xw", title: "ThePrimeagen" }
    ]
  },
  science_math: {
    name: "Science & Engineering",
    description: "Mathematics, physics, foundational philosophy, and visual thinking.",
    channels: [
      { id: "UCYO_jab_esuFRV4b17AJtAw", title: "3Blue1Brown" },
      { id: "UCHnyfMqiRRG1u-2MsSQLbXA", title: "Veritasium" },
      { id: "UCsXVk37bltHxD1rDPwtNM8Q", title: "Kurzgesagt" }
    ]
  }
};

export default function SetupWizard({ onComplete }) {
  const [selectedPacks, setSelectedPacks] = useState(['ai_ml']);
  const [topicsText, setTopicsText] = useState("local LLMs, embedded engineering, neuroscience");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const togglePack = (packKey) => {
    if (selectedPacks.includes(packKey)) {
      setSelectedPacks(selectedPacks.filter(k => k !== packKey));
    } else {
      setSelectedPacks([...selectedPacks, packKey]);
    }
  };

  const handleSetupSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      // 1. Gather all selected channels
      const channelsToSub = [];
      selectedPacks.forEach(packKey => {
        channelsToSub.push(...CURATED_PACKS[packKey].channels);
      });

      if (channelsToSub.length === 0) {
        throw new Error("Please select at least one channel pack to initialize your feed.");
      }

      // Create subscriptions sequentially
      for (const channel of channelsToSub) {
        await api.createChannel({
          id: channel.id,
          title: channel.title,
          is_trusted: true,
          provider: "rss"
        }).catch(err => console.warn(`Channel subscribe warning: ${err.message}`));
      }

      // 2. Parse and seed explicit interest topics
      const topics = topicsText
        .split(',')
        .map(t => t.trim())
        .filter(t => t.length > 1);

      for (const topic of topics) {
        await api.followTopic(topic).catch(err => console.warn(`Follow topic warning: ${err.message}`));
      }

      // 3. Kickstart background pipeline sweep to sync XML feeds instantly
      await api.triggerPipelineSync();

      // Complete wizard
      onComplete();
    } catch (err) {
      setError(err.message || "Failed to initialize Setup Wizard.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      maxWidth: '640px',
      margin: '80px auto',
      padding: '24px',
      backgroundColor: 'var(--bg-surface)',
      border: '1px solid var(--border-subtle)',
      borderRadius: '8px'
    }}>
      <div style={{ marginBottom: '24px', textAlign: 'center' }}>
        <h1 style={{ fontSize: '1.75rem', marginBottom: '8px' }}>Welcome to SignalFeed</h1>
        <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>
          Configure your personal signal radar. Select starter curation packages and list immediate interest tracks.
        </p>
      </div>

      {error && (
        <div style={{
          backgroundColor: 'rgba(239, 68, 68, 0.1)',
          border: '1px solid var(--danger)',
          color: 'var(--danger)',
          padding: '12px',
          borderRadius: '4px',
          marginBottom: '16px',
          fontSize: '0.85rem'
        }}>
          {error}
        </div>
      )}

      <form onSubmit={handleSetupSubmit}>
        {/* Curated packages select */}
        <div style={{ marginBottom: '20px' }}>
          <label style={{
            display: 'block',
            fontSize: '0.8rem',
            fontWeight: '600',
            textTransform: 'uppercase',
            color: 'var(--text-muted)',
            marginBottom: '8px'
          }}>
            1. Select Starter Channel Packs
          </label>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {Object.entries(CURATED_PACKS).map(([key, pack]) => {
              const active = selectedPacks.includes(key);
              return (
                <div 
                  key={key}
                  onClick={() => togglePack(key)}
                  style={{
                    backgroundColor: active ? 'rgba(59, 130, 246, 0.05)' : 'var(--bg-card)',
                    border: active ? '1px solid var(--accent)' : '1px solid var(--border-subtle)',
                    padding: '12px',
                    borderRadius: '6px',
                    cursor: 'pointer',
                    transition: 'border-color var(--transition-fast)'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                    <h3 style={{ fontSize: '0.95rem' }}>{pack.name}</h3>
                    <input 
                      type="checkbox" 
                      checked={active} 
                      onChange={() => {}} 
                      style={{ cursor: 'pointer' }}
                    />
                  </div>
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>{pack.description}</p>
                </div>
              );
            })}
          </div>
        </div>

        {/* Interests seed input */}
        <div style={{ marginBottom: '24px' }}>
          <label style={{
            display: 'block',
            fontSize: '0.8rem',
            fontWeight: '600',
            textTransform: 'uppercase',
            color: 'var(--text-muted)',
            marginBottom: '8px'
          }}>
            2. Seed Focus Keywords (Comma separated)
          </label>
          <input
            type="text"
            value={topicsText}
            onChange={(e) => setTopicsText(e.target.value)}
            placeholder="e.g. quantization, embedded engineering, category theory"
            required
            style={{ width: '100%', padding: '10px' }}
          />
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px', display: 'block' }}>
            These tags are converted to vector embeddings to immediately prime your semantic interest vector.
          </span>
        </div>

        <button 
          type="submit" 
          disabled={loading}
          className="primary" 
          style={{ width: '100%', padding: '12px', fontSize: '0.95rem' }}
        >
          {loading ? "Syncing Pipeline & Vectorizing..." : "Initialize SignalFeed Dashboard"}
        </button>
      </form>
    </div>
  );
}
