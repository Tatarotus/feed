import React, { useState, useEffect, useRef } from 'react';
import { api } from './utils/api';
import SetupWizard from './components/SetupWizard';
import FeedList from './components/FeedList';
import QueuePanel from './components/QueuePanel';
import ChannelConfig from './components/ChannelConfig';
import FocusPlayer from './components/FocusPlayer';
import SeedsPage from './components/SeedsPage';
import { SignalLogo, SearchIcon, QueueIcon, ThemeIcon } from './components/SignalLogo';

export default function App() {
  const [onboarded, setOnboarded] = useState(true);
  const [checkingOnboard, setCheckingOnboard] = useState(true);
  
  // Dynamic collections
  const [feed, setFeed] = useState([]);
  const [queue, setQueue] = useState([]);
  
  // Toggles and layout states
  const [calmMode, setCalmMode] = useState(false); // Default to showing visuals
  const [learningMode, setLearningMode] = useState(false);
  const [serendipity, setSerendipity] = useState(0.2); // Default to Balanced (20%)
  const latestFeedRequestId = useRef(0);
  const [activeVideo, setActiveVideo] = useState(() => {
    const val = localStorage.getItem('activeVideo');
    try {
      return val ? JSON.parse(val) : null;
    } catch (e) {
      return null;
    }
  });
  const handlePlayVideo = (video) => {
    setActiveVideo(video);
    if (video) {
      localStorage.setItem('activeVideo', JSON.stringify(video));
    } else {
      localStorage.removeItem('activeVideo');
    }
  };
  const [currentView, setCurrentView] = useState("feed"); // 'feed', 'seeds'
  
  // Sidebar visibility states (persisted in localStorage)
  const [showCurationSidebar, setShowCurationSidebar] = useState(() => {
    const val = localStorage.getItem('showCurationSidebar');
    return val !== null ? val === 'true' : true;
  });
  const [showQueueSidebar, setShowQueueSidebar] = useState(() => {
    const val = localStorage.getItem('showQueueSidebar');
    return val !== null ? val === 'true' : true;
  });
  const [lightTheme, setLightTheme] = useState(() => {
    return localStorage.getItem('lightTheme') === 'true';
  });
  
  // Search bar states
  const [searchQuery, setSearchQuery] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  
  const [feedLoading, setFeedLoading] = useState(false);
  const [queueLoading, setQueueLoading] = useState(false);

  // Check if system has completed onboarding (channels and interests exist)
  const checkOnboardStatus = async () => {
    try {
      const chans = await api.getChannels();
      const ints = await api.getInterests();
      // If either is empty, trigger Setup Wizard onboarding
      if (chans.length === 0 || ints.length === 0) {
        setOnboarded(false);
      } else {
        setOnboarded(true);
      }
    } catch (e) {
      console.error("Health check onboarding error:", e);
    } finally {
      setCheckingOnboard(false);
    }
  };

  const loadFeed = async (serenVal = serendipity) => {
    const requestId = ++latestFeedRequestId.current;
    setFeedLoading(true);
    try {
      const data = await api.getFeed(500, serenVal);
      if (requestId === latestFeedRequestId.current) {
        setFeed(data);
      }
    } catch (err) {
      if (requestId === latestFeedRequestId.current) {
        console.error("Failed to load feed:", err);
      }
    } finally {
      if (requestId === latestFeedRequestId.current) {
        setFeedLoading(false);
      }
    }
  };

  const loadQueue = async () => {
    setQueueLoading(true);
    try {
      const data = await api.getQueue();
      setQueue(data);
    } catch (err) {
      console.error("Failed to load queue:", err);
    } finally {
      setQueueLoading(false);
    }
  };

  const handleSearchSubmit = async (e) => {
    e.preventDefault();
    if (!searchQuery.trim()) {
      setIsSearching(false);
      loadFeed();
      return;
    }

    setFeedLoading(true);
    setIsSearching(true);
    try {
      const results = await api.search(searchQuery.trim());
      // Convert raw videos back to feed format with search mock ratings
      const formattedResults = results.map(video => ({
        video,
        score: 80.0,
        badge: "Search Match",
        breakdown: {
          trusted_boost: 0.0,
          preference_boost: 0.0,
          semantic_affinity: 80.0,
          clickbait_penalty: 0.0,
          negative_demotion: 0.0,
          freshness_decay: 0.0
        },
        best_topic: searchQuery,
        is_discovery: false,
        sources: ["vector_search"]
      }));
      setFeed(formattedResults);
    } catch (err) {
      alert(`Search failed: ${err.message}`);
    } finally {
      setFeedLoading(false);
    }
  };

  const clearSearch = () => {
    setSearchQuery("");
    setIsSearching(false);
    loadFeed();
  };

  const handleRefreshAll = async () => {
    setFeedLoading(true);
    try {
      // 1. Trigger database pipeline sweep
      await api.triggerPipelineSync();
      // 2. Wait 2 seconds for worker task to kick off
      await new Promise(resolve => setTimeout(resolve, 2000));
      // 3. Reload collections
      await loadFeed();
      await loadQueue();
    } catch (err) {
      console.error(err);
    } finally {
      setFeedLoading(false);
    }
  };

  useEffect(() => {
    checkOnboardStatus();
  }, []);

  useEffect(() => {
    if (onboarded && !checkingOnboard) {
      loadFeed();
      loadQueue();
    }
  }, [onboarded, checkingOnboard]);

  useEffect(() => {
    localStorage.setItem('showCurationSidebar', showCurationSidebar);
  }, [showCurationSidebar]);

  useEffect(() => {
    localStorage.setItem('showQueueSidebar', showQueueSidebar);
  }, [showQueueSidebar]);

  useEffect(() => {
    localStorage.setItem('lightTheme', lightTheme);
  }, [lightTheme]);

  if (checkingOnboard) {
    return (
      <div style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        height: '100vh',
        backgroundColor: 'var(--bg-main)',
        color: 'var(--text-muted)'
      }}>
        Analyzing local SignalFeed station lifecycle...
      </div>
    );
  }

  if (!onboarded) {
    return <SetupWizard onComplete={() => setOnboarded(true)} />;
  }

  return (
    <div className={`app-container ${lightTheme ? 'light-theme' : ''}`}>
      {/* 1. Top Fixed Navbar */}
      <header className="app-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {/* Curation Sidebar Toggle Menu Button */}
          <button 
            onClick={() => setShowCurationSidebar(!showCurationSidebar)}
            style={{ 
              background: 'transparent', 
              border: 'none', 
              fontSize: '1.2rem', 
              cursor: 'pointer', 
              padding: '4px 8px',
              display: 'flex',
              alignItems: 'center',
              color: showCurationSidebar ? 'var(--text-primary)' : 'var(--text-muted)'
            }}
            title="Toggle Curation Sidebar (Left)"
          >
            ☰
          </button>
          <div className="app-header-brand" onClick={clearSearch} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <SignalLogo style={{ width: '22px', height: '22px' }} />
            <span>SignalFeed</span> <span style={{ fontSize: '0.62rem', opacity: 0.6, fontWeight: 'normal', backgroundColor: 'var(--bg-card)', padding: '2px 6px', borderRadius: '4px', border: '1px solid var(--border-subtle)' }}>v0.1</span>
          </div>
        </div>

        {/* Centered search input form */}
        <form onSubmit={handleSearchSubmit} className="search-form-wrapper">
          <input
            type="text"
            className="search-input-field"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search topics, channels, or transcripts..."
          />
          {searchQuery && (
            <button type="button" onClick={clearSearch} className="search-clear-btn">
              ✕
            </button>
          )}
          <button type="submit" className="search-submit-btn" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <SearchIcon style={{ width: '13px', height: '13px' }} />
            <span>Search</span>
          </button>
        </form>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={{ fontSize: '0.72rem', color: 'var(--success)', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            ● System Healthy
          </span>
          <span style={{ borderLeft: '1px solid var(--border-subtle)', height: '16px' }}></span>
          {/* See Later Playlist Sidebar Toggle Button */}
          <button 
            onClick={() => setShowQueueSidebar(!showQueueSidebar)}
            style={{ 
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              background: showQueueSidebar ? 'var(--bg-card)' : 'transparent',
              borderColor: showQueueSidebar ? 'var(--border-focus)' : 'var(--border-subtle)',
              fontSize: '0.74rem', 
              padding: '4px 12px',
              borderRadius: '16px',
              color: showQueueSidebar ? 'var(--accent)' : 'var(--text-secondary)'
            }}
            title="Toggle See Later Queue (Right)"
          >
            <QueueIcon style={{ width: '12px', height: '12px' }} />
            <span>{showQueueSidebar ? 'Queue Active' : 'Show Queue'}</span>
          </button>
          
          <span style={{ borderLeft: '1px solid var(--border-subtle)', height: '16px' }}></span>

          {/* Theme Toggle Button */}
          <button 
            onClick={() => setLightTheme(!lightTheme)}
            style={{ 
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              padding: '4px 8px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--text-secondary)'
            }}
            title={lightTheme ? "Toggle Obsidian Dark Theme" : "Toggle Zinc Light Theme"}
          >
            <ThemeIcon light={lightTheme} style={{ width: '18px', height: '18px' }} />
          </button>
        </div>
      </header>

      {/* 2. Main Dashboard columns body */}
      <div className="app-body">
        {/* Left Sidebar: Subscriptions + Seeding Config */}
        <aside className={`left-sidebar ${showCurationSidebar ? '' : 'collapsed'}`}>
          <ChannelConfig 
            onSyncComplete={handleRefreshAll} 
            serendipity={serendipity}
            onSerendipityChange={(val) => {
              setSerendipity(val);
              loadFeed(val);
            }}
            onManageSeeds={() => setCurrentView("seeds")}
          />
        </aside>

        {/* Center Panel: Content Recommendations Feed or Seeds Page */}
        <main className="feed-scroll-container">
          {currentView === "seeds" ? (
            <SeedsPage 
              onBack={() => setCurrentView("feed")}
              onRefreshFeed={handleRefreshAll}
            />
          ) : (
            <FeedList 
              feed={feed}
              loading={feedLoading}
              onRefresh={handleRefreshAll}
              onPlayVideo={handlePlayVideo}
              onQueueUpdate={loadQueue}
              calmMode={calmMode}
              learningMode={learningMode}
              setCalmMode={setCalmMode}
              setLearningMode={setLearningMode}
              serendipity={serendipity}
              onSerendipityChange={(val) => {
                setSerendipity(val);
                loadFeed(val);
              }}
            />
          )}
        </main>

        {/* Right Sidebar: See Later Playlist Sidebar */}
        <aside className={`right-sidebar ${showQueueSidebar ? '' : 'collapsed'}`}>
          <QueuePanel 
            queue={queue}
            onRefreshQueue={loadQueue}
            onPlayVideo={handlePlayVideo}
          />
        </aside>
      </div>

      {/* Focused overlay player */}
      <FocusPlayer 
        video={activeVideo} 
        onClose={() => handlePlayVideo(null)} 
      />
    </div>
  );
}
