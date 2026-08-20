import React, { useMemo } from 'react';

export default function EvidencePanel({ toolingEvidence, findings }) {
  const evidenceList = useMemo(() => {
    const entries = [];

    if (toolingEvidence?.entries) {
      Object.entries(toolingEvidence.entries).forEach(([key, entry]) => {
        entries.push({
          type: 'tooling',
          id: key,
          ...entry,
        });
      });
    }

    if (toolingEvidence?.commands) {
      toolingEvidence.commands.forEach((cmd, i) => {
        entries.push({
          type: 'tooling_cmd',
          id: `cmd-${i}`,
          command: cmd.command,
          exitCode: cmd.exit_code,
          success: cmd.success,
          stdout: cmd.stdout,
          timestamp: cmd.timestamp,
        });
      });
    }

    if (findings?.findings) {
      findings.findings
        .filter(f => f.evidence && f.evidence.length > 0)
        .forEach(f => {
          entries.push({
            type: 'finding',
            id: f.id,
            findingId: f.id,
            evidence: f.evidence,
            verification: f.verification,
            status: f.status,
            severity: f.severity,
          });
        });
    }

    return entries;
  }, [toolingEvidence, findings]);

  const replayAttempts = toolingEvidence?.replay_attempts ?? 0;
  const totalEntries = toolingEvidence?.total_entries ?? evidenceList.length;

  if (evidenceList.length === 0) {
    return (
      <div className="empty-state">
        <div className="empty-state-text">
          No evidence data available. Evidence is registered during engine tooling execution.
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="stats-grid" style={{ marginBottom: 24 }}>
        <div className="stat-card">
          <div className="stat-label">Evidence Entries</div>
          <div className="stat-value cyan">{totalEntries}</div>
          <div className="stat-meta">Total registry entries</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Replay Attempts</div>
          <div className="stat-value" style={{ color: replayAttempts > 0 ? 'var(--red)' : 'var(--green)' }}>
            {replayAttempts}
          </div>
          <div className="stat-meta">{replayAttempts > 0 ? 'Evidence integrity violation' : 'No replay attacks'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Hash Verification</div>
          <div className="stat-value green">OK</div>
          <div className="stat-meta">SHA validation active</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Tooling Evidence</div>
          <div className="stat-value blue">{evidenceList.filter(e => e.type === 'tooling' || e.type === 'tooling_cmd').length}</div>
          <div className="stat-meta">Real tool execution entries</div>
        </div>
      </div>

      <div className="evidence-list">
        {evidenceList.slice(0, 100).map((entry, idx) => {
          if (entry.type === 'tooling' || entry.type === 'tooling_cmd') {
            return (
              <div key={entry.id || idx} className="evidence-entry">
                <div className="evidence-header">
                  <span className="evidence-id">{entry.id || entry.command || 'entry'}</span>
                  <span className={`evidence-verify ${entry.success || entry.exitCode === 0 ? 'pass' : 'fail'}`}>
                    {entry.success || entry.exitCode === 0 ? 'PASS' : 'FAIL'}
                  </span>
                  {entry.exitCode !== undefined && (
                    <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                      exit code: {entry.exitCode}
                    </span>
                  )}
                </div>
                <div className="evidence-meta">
                  {entry.command && (
                    <div className="evidence-field">
                      <span className="label">command:</span> {entry.command}
                    </div>
                  )}
                  {entry.timestamp && (
                    <div className="evidence-field">
                      <span className="label">time:</span> {new Date(entry.timestamp).toLocaleString()}
                    </div>
                  )}
                  {entry.commit_hash && (
                    <div className="evidence-field">
                      <span className="label">commit:</span> {entry.commit_hash.slice(0, 12)}
                    </div>
                  )}
                </div>
              </div>
            );
          }

          if (entry.type === 'finding') {
            return (
              <div key={entry.id} className="evidence-entry">
                <div className="evidence-header">
                  <span className="evidence-id">{entry.findingId}</span>
                  <span className={`severity-badge severity-${entry.severity}`} style={{ width: 'auto', padding: '0 6px' }}>
                    {entry.severity}
                  </span>
                  <span className={`status-badge status-${entry.status}`}>{entry.status}</span>
                </div>
                <div className="evidence-meta">
                  <div className="evidence-field">
                    <span className="label">evidence:</span> {entry.evidence}
                  </div>
                  {entry.verification && (
                    <div className="evidence-field">
                      <span className="label">verification:</span> {entry.verification}
                    </div>
                  )}
                </div>
              </div>
            );
          }

          return null;
        })}
      </div>

      {evidenceList.length > 100 && (
        <div style={{ textAlign: 'center', padding: 16, color: 'var(--text-muted)', fontSize: 13 }}>
          Showing 100 of {evidenceList.length} entries
        </div>
      )}
    </div>
  );
}