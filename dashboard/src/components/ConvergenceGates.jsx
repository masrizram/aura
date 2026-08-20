import React from 'react';
import { getGateDefinitions } from '../api';

export default function ConvergenceGates({ convergence }) {
  if (!convergence) {
    return <div className="empty-state"><div className="empty-state-text">No convergence data</div></div>;
  }

  const gateDefs = getGateDefinitions();
  const gates = convergence.gates || {};
  const passing = Object.values(gates).filter(Boolean).length;
  const total = gateDefs.length;
  const ratio = total > 0 ? (passing / total) * 100 : 0;

  return (
    <div>
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-header">
          <span className="card-title">Gate Status: {passing} / {total} Passing</span>
          <span className={`convergence-badge ${convergence.converged ? 'ready' : 'not-ready'}`}>
            {convergence.converged ? 'CONVERGED' : 'NOT CONVERGED'}
          </span>
        </div>
        <div className="gate-summary-bar">
          <div className="gate-summary-pass" style={{ width: `${ratio}%` }} />
          <div className="gate-summary-fail" style={{ width: `${100 - ratio}%` }} />
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6, fontSize: 11, color: 'var(--text-muted)' }}>
          <span>0 gates</span>
          <span>{passing} of {total} ({Math.round(ratio)}%)</span>
          <span>{total} gates</span>
        </div>
      </div>

      <div className="gates-grid">
        {gateDefs.map(gate => {
          const isPass = gates[gate.id] === true;
          return (
            <div key={gate.id} className="gate-card">
              <div className="gate-number">Gate {gate.number}</div>
              <div className="gate-name">{gate.name}</div>
              <div className="gate-desc">{gate.desc}</div>
              <div className={`gate-status ${isPass ? 'pass' : 'fail'}`}>
                <div className="gate-status-dot" />
                {isPass ? 'PASS' : 'FAIL'}
              </div>
            </div>
          );
        })}
      </div>

      {convergence.reason && (
        <div className="card" style={{ marginTop: 20 }}>
          <div className="card-header">
            <span className="card-title">Convergence Reason</span>
          </div>
          <div className="reason-block">{convergence.reason}</div>
        </div>
      )}
    </div>
  );
}