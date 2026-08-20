import React, { useMemo } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import { Line, Bar } from 'react-chartjs-2';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, BarElement, Tooltip, Legend, Filler);

const COLORS = {
  green: '#00b894',
  red: '#d63031',
  yellow: '#fdcb6e',
  cyan: '#00cec9',
  blue: '#58a6ff',
  orange: '#f0883e',
  purple: '#bc8cff',
};

const HIGH_CONFIDENCE_DATES = [
  '2026-08-15T00:00:00+07:00',
  '2026-08-16T00:00:00+07:00',
  '2026-08-17T00:00:00+07:00',
  '2026-08-18T00:00:00+07:00',
  '2026-08-19T00:00:00+07:00',
  '2026-08-20T00:00:00+07:00',
];

const CYCLE_SCORES = [35, 40, 45, 50, 50, 55];
const CYCLE_NEW_FINDINGS = [23, 12, 9, 7, 0, 14];
const CYCLE_FIXED_FINDINGS = [0, 18, 8, 7, 5, 14];

export default function TimelinePanel({ convergence, cycle, findings }) {
  const timelineData = useMemo(() => {
    const currentCycle = cycle?.current_cycle || 6;
    const cycles = [];
    const allFindings = findings?.findings || [];
    const cyclePrefixes = ['C1', 'C2', 'C3', 'C4', 'C5', 'C6'];

    for (let i = 0; i < currentCycle; i++) {
      const prefix = cyclePrefixes[i] || `C${i + 1}`;
      const cycleFindings = allFindings.filter(f => f.id && f.id.includes(`-${prefix}-`));
      const cycleOpen = cycleFindings.filter(f => f.status === 'OPEN' || f.status === 'IN_PROGRESS' || f.status === 'VERIFYING');
      const cycleFixed = cycleFindings.filter(f => f.status === 'FIXED' || f.status === 'VERIFIED');

      cycles.push({
        cycleNumber: i + 1,
        classification: i + 1 === currentCycle ? (cycle?.classification || 'NOT_READY') : 'NOT_READY',
        date: HIGH_CONFIDENCE_DATES[i] || 'N/A',
        score: CYCLE_SCORES[i] || 0,
        newFindings: CYCLE_NEW_FINDINGS[i] || 0,
        fixedFindings: CYCLE_FIXED_FINDINGS[i] || 0,
        totalFindings: cycleFindings.length,
        openCount: cycleOpen.length,
        fixedCount: cycleFixed.length,
        isCurrent: i + 1 === currentCycle,
      });
    }
    return cycles;
  }, [cycle, findings]);

  const burndownData = {
    labels: timelineData.map(c => `Cycle ${c.cycleNumber}`),
    datasets: [
      {
        label: 'New Findings',
        data: timelineData.map(c => c.newFindings),
        borderColor: COLORS.red,
        backgroundColor: 'rgba(214, 48, 49, 0.1)',
        fill: true,
        tension: 0.3,
        pointBackgroundColor: COLORS.red,
      },
      {
        label: 'Fixed Findings',
        data: timelineData.map(c => c.fixedFindings),
        borderColor: COLORS.green,
        backgroundColor: 'rgba(0, 184, 148, 0.1)',
        fill: true,
        tension: 0.3,
        pointBackgroundColor: COLORS.green,
      },
    ],
  };

  const scoreData = {
    labels: timelineData.map(c => `Cycle ${c.cycleNumber}`),
    datasets: [{
      label: 'Score',
      data: timelineData.map(c => c.score),
      borderColor: COLORS.cyan,
      backgroundColor: 'rgba(0, 206, 201, 0.15)',
      fill: true,
      tension: 0.3,
      pointBackgroundColor: COLORS.cyan,
      pointRadius: 6,
      pointHoverRadius: 8,
      borderWidth: 2,
    }],
  };

  const openClosedData = {
    labels: timelineData.map(c => `Cycle ${c.cycleNumber}`),
    datasets: [
      {
        label: 'Open',
        data: timelineData.map(c => c.openCount),
        backgroundColor: COLORS.red,
        borderRadius: 4,
      },
      {
        label: 'Fixed/Verified',
        data: timelineData.map(c => c.fixedCount),
        backgroundColor: COLORS.green,
        borderRadius: 4,
      },
    ],
  };

  const chartBase = {
    responsive: true,
    maintainAspectRatio: false,
    color: '#8b949e',
    plugins: {
      legend: {
        labels: { color: '#8b949e', font: { size: 11 }, padding: 16, usePointStyle: true },
      },
    },
    scales: {
      x: { grid: { color: '#21262d' }, ticks: { color: '#8b949e', font: { size: 10 } } },
      y: { grid: { color: '#21262d' }, ticks: { color: '#8b949e', font: { size: 10 } }, beginAtZero: true },
    },
  };

  const scoreOpts = {
    ...chartBase,
    scales: {
      ...chartBase.scales,
      y: { ...chartBase.scales.y, min: 0, max: 100 },
    },
  };

  const stackedOpts = {
    ...chartBase,
    scales: {
      ...chartBase.scales,
      x: { ...chartBase.scales.x, stacked: true },
      y: { ...chartBase.scales.y, stacked: true },
    },
  };

  if (!convergence) {
    return <div className="empty-state"><div className="empty-state-text">No timeline data</div></div>;
  }

  return (
    <div>
      <div className="charts-grid" style={{ marginBottom: 24 }}>
        <div className="chart-container wide">
          <div className="card-header">
            <span className="card-title">Score Progression</span>
            <span className="card-subtitle">Current: {convergence.overall_score}/100</span>
          </div>
          <div className="chart-inner tall">
            <Line data={scoreData} options={scoreOpts} />
          </div>
        </div>

        <div className="chart-container">
          <div className="card-header">
            <span className="card-title">Finding Burndown</span>
            <span className="card-subtitle">New vs Fixed per cycle</span>
          </div>
          <div className="chart-inner">
            <Line data={burndownData} options={chartBase} />
          </div>
        </div>

        <div className="chart-container">
          <div className="card-header">
            <span className="card-title">Open vs Fixed by Cycle</span>
            <span className="card-subtitle">Stacked distribution</span>
          </div>
          <div className="chart-inner">
            <Bar data={openClosedData} options={stackedOpts} />
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Cycle History</span>
        </div>
        <div className="timeline">
          {timelineData.slice().reverse().map(cyc => (
            <div key={cyc.cycleNumber} className="timeline-item">
              <div className="timeline-header">
                <span className="timeline-cycle">
                  Cycle {cyc.cycleNumber}
                  {cyc.isCurrent && <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 8 }}>(current)</span>}
                </span>
                <span className={`timeline-classification ${cyc.classification}`}>
                  {cyc.classification}
                </span>
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  {cyc.date !== 'N/A' ? new Date(cyc.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : ''}
                </span>
              </div>
              <div className="timeline-details">
                <div className="timeline-stat">
                  <strong style={{ color: 'var(--cyan)', fontSize: 18 }}>{cyc.score}</strong> score
                </div>
                <div className="timeline-stat">
                  <strong style={{ color: 'var(--red)' }}>{cyc.newFindings}</strong> new findings
                </div>
                <div className="timeline-stat">
                  <strong style={{ color: 'var(--green)' }}>{cyc.fixedFindings}</strong> fixed
                </div>
                <div className="timeline-stat">
                  <strong>{cyc.openCount}</strong> open / <strong>{cyc.fixedCount}</strong> resolved
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}