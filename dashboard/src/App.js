import React, { useState, useEffect, useCallback } from 'react';
import Header from './components/Header';
import OverviewPanel from './components/OverviewPanel';
import ConvergenceGates from './components/ConvergenceGates';
import FindingsTable from './components/FindingsTable';
import MetricsPanel from './components/MetricsPanel';
import TimelinePanel from './components/TimelinePanel';
import EvidencePanel from './components/EvidencePanel';
import { loadAll } from './api';

const TABS = ['Overview', 'Convergence Gates', 'Findings', 'Metrics', 'Timeline', 'Evidence'];

const STATIC_CONVERGENCE = {"cycle":6,"converged":false,"consecutive_converged_cycles":0,"overall_score":55,"gates":{"P0_zero":false,"P1_zero":false,"P2_zero":false,"critical_security":false,"critical_correctness":false,"data_integrity":false,"regression":false,"verification":false,"no_material_new_findings":false,"limitations_documented":false,"consecutive_clean_independent_audits":false,"module_dependency_integrity":true},"classification":"NOT_READY","reason":"14 new P0-P2 findings discovered. 1 of 12 gates pass.","dimension_scores":{"Architecture":60,"Correctness":68,"Security":52,"Reliability":52,"Performance":62,"Testing":15,"Observability":32,"Operations":36,"Maintainability":66,"Documentation":78}};
const STATIC_CYCLE = {"current_cycle":6,"cycles_completed":5,"classification":"NOT_READY","current_phase":"CONVERGENCE","status":"COMPLETED","started_at":"2026-08-20T06:47:50+07:00","engine_name":"Continuous Autonomous Engineering Audit Engine","version":"2.1.0","consecutive_converged_cycles":0,"audit_scope_pct":95.7,"new_findings_this_cycle":14,"findings_fixed_this_cycle":14};

export default function App() {
  const [activeTab, setActiveTab] = useState('Overview');
  const [data, setData] = useState({
    convergence: STATIC_CONVERGENCE,
    cycle: STATIC_CYCLE,
    findings: null,
    toolingEvidence: null,
  });
  const [loading, setLoading] = useState(true);
  const [connected, setConnected] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const result = await loadAll();
      setData({
        convergence: result.convergence || STATIC_CONVERGENCE,
        cycle: result.cycle || STATIC_CYCLE,
        findings: result.findings,
        toolingEvidence: result.toolingEvidence,
      });
      setConnected(true);
    } catch {
      setConnected(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const renderTab = () => {
    switch (activeTab) {
      case 'Overview':
        return <OverviewPanel convergence={data.convergence} cycle={data.cycle} findings={data.findings} />;
      case 'Convergence Gates':
        return <ConvergenceGates convergence={data.convergence} />;
      case 'Findings':
        return <FindingsTable findings={data.findings} />;
      case 'Metrics':
        return <MetricsPanel convergence={data.convergence} findings={data.findings} />;
      case 'Timeline':
        return <TimelinePanel convergence={data.convergence} cycle={data.cycle} findings={data.findings} />;
      case 'Evidence':
        return <EvidencePanel toolingEvidence={data.toolingEvidence} findings={data.findings} />;
      default:
        return null;
    }
  };

  return (
    <div className="app">
      <Header
        tabs={TABS}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        onRefresh={refresh}
        connected={connected}
        loading={loading}
        version={data.cycle.version}
        engineName={data.cycle.engine_name}
      />
      <div className="content">{renderTab()}</div>
    </div>
  );
}