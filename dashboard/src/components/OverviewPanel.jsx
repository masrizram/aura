import React from 'react';
import { computeSeverityStats } from '../api';

export default function OverviewPanel({ convergence, cycle, findings }) {
  if (!convergence || !cycle) {
    return <div className="empty-state"><div className="empty-state-text">No data available</div></div>;
  }

  const conv = convergence;
  const cyc = cycle;
  const severityStats = computeSeverityStats(findings?.findings);
  const openTotal = severityStats.P0 + severityStats.P1 + severityStats.P2;
  const score = conv.overall_score;
  const scoreColor = score >= 80 ? 'green' : score >= 60 ? 'yellow' : 'red';
  const classification = conv.classification || 'UNKNOWN';

  const classBadge = classification === 'PRODUCTION_READY' ? 'ready' :
    classification === 'CONDITIONALLY_READY' ? 'conditional' : 'not-ready';

  return (
    <div>
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">Engine</div>
          <div className="stat-value cyan" style={{ fontSize: 18 }}>{cyc.engine_name || 'AURA'}</div>
          <div className="stat-meta">v{cyc.version || '2.1.0'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Cycles Completed</div>
          <div className="stat-value blue">{cyc.cycles_completed}</div>
          <div className="stat-meta">Current: Cycle {cyc.current_cycle}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Classification</div>
          <div className="convergence-badge" style={{ marginTop: 4, display: 'inline-flex' }}>
            <span className={classBadge}>{classification}</span>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Converged</div>
          <div style={{ marginTop: 4 }}>
            <span className={`convergence-badge ${conv.converged ? 'ready' : 'not-ready'}`}>
              {conv.converged ? 'PRODUCTION READY' : 'NOT READY'}
            </span>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Open P0</div>
          <div className="stat-value red">{severityStats.P0}</div>
          <div className="stat-meta">Catastrophic blockers</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Open P1</div>
          <div className="stat-value" style={{ color: '#f0883e' }}>{severityStats.P1}</div>
          <div className="stat-meta">Critical findings</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Open P2</div>
          <div className="stat-value yellow">{severityStats.P2}</div>
          <div className="stat-meta">High findings</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Open P0-P2</div>
          <div className="stat-value" style={{ color: openTotal > 0 ? 'var(--red)' : 'var(--green)' }}>{openTotal}</div>
          <div className="stat-meta">Total active findings</div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-header">
          <span className="card-title">Overall Score</span>
          <span className="card-subtitle">Consecutive converged cycles: {conv.consecutive_converged_cycles}</span>
        </div>
        <div className="big-score">
          <div className={`big-score-number ${scoreColor}`}>{score}</div>
          <div className="big-score-label">out of 100</div>
          <div className="big-score-bar">
            <div
              className="big-score-fill"
              style={{ width: `${score}%`, backgroundColor: `var(--${scoreColor})` }}
            />
          </div>
        </div>
      </div>

      <div className="summary-row">
        <div className="card" style={{ flex: 1 }}>
          <div className="card-header">
            <span className="card-title">Cycle Summary</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 13 }}>
            <div><span style={{ color: 'var(--text-muted)' }}>Phase:</span> <strong>{cyc.current_phase}</strong></div>
            <div><span style={{ color: 'var(--text-muted)' }}>Status:</span> <strong>{cyc.status}</strong></div>
            <div><span style={{ color: 'var(--text-muted)' }}>Scope:</span> <strong>{cyc.audit_scope_pct}%</strong></div>
            <div><span style={{ color: 'var(--text-muted)' }}>New findings:</span> <strong>{cyc.new_findings_this_cycle}</strong></div>
            <div><span style={{ color: 'var(--text-muted)' }}>Fixed this cycle:</span> <strong>{cyc.findings_fixed_this_cycle}</strong></div>
            <div><span style={{ color: 'var(--text-muted)' }}>Without progress:</span> <strong>{cyc.cycles_without_progress || 0}</strong></div>
          </div>
        </div>
        <div className="card" style={{ flex: 1 }}>
          <div className="card-header">
            <span className="card-title">Quick Stats</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 13 }}>
            <div><span style={{ color: 'var(--text-muted)' }}>Gates passing:</span> <strong style={{ color: 'var(--green)' }}>{Object.values(conv.gates || {}).filter(Boolean).length}</strong> / 12</div>
            <div><span style={{ color: 'var(--text-muted)' }}>Consecutive converged:</span> <strong>{conv.consecutive_converged_cycles}</strong></div>
            <div><span style={{ color: 'var(--text-muted)' }}>Total findings:</span> <strong>{findings?.findings?.length || 0}</strong></div>
            <div><span style={{ color: 'var(--text-muted)' }}>Confidence:</span> <strong>{conv.confidence}</strong></div>
            <div><span style={{ color: 'var(--text-muted)' }}>Module integrity:</span> <strong style={{ color: 'var(--green)' }}>PASS</strong></div>
            <div><span style={{ color: 'var(--text-muted)' }}>Started:</span> <strong>{cyc.started_at ? new Date(cyc.started_at).toLocaleString() : 'N/A'}</strong></div>
          </div>
        </div>
      </div>

      {conv.reason && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">Reason</span>
          </div>
          <div className="reason-block">{conv.reason}</div>
        </div>
      )}
    </div>
  );
}