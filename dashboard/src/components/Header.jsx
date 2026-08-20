import React from 'react';

export default function Header({ tabs, activeTab, onTabChange, onRefresh, connected, loading, version, engineName }) {
  return (
    <header className="header">
      <div className="header-logo">
        <h1>AURA</h1>
        <span className="version">v{version || '2.1.0'}</span>
      </div>
      <nav className="header-tabs">
        {tabs.map(tab => (
          <button
            key={tab}
            className={`header-tab${activeTab === tab ? ' active' : ''}`}
            onClick={() => onTabChange(tab)}
          >
            {tab}
          </button>
        ))}
      </nav>
      <div className="header-actions">
        <div className="header-status">
          <div className={`header-status-dot ${connected ? 'connected' : 'disconnected'}`} />
          <span>{connected ? 'Live' : 'Static'}</span>
        </div>
        <button className="refresh-btn" onClick={onRefresh} disabled={loading}>
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>
    </header>
  );
}