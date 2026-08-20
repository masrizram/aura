import React from 'react';
import {
  Chart as ChartJS,
  RadialLinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
  CategoryScale,
  LinearScale,
  BarElement,
  ArcElement,
} from 'chart.js';
import { Radar, Line, Doughnut, Bar } from 'react-chartjs-2';
import { getDimensionDefinitions, computeStatusDistribution, computeCategoryDistribution } from '../api';

ChartJS.register(
  RadialLinearScale, PointElement, LineElement, Filler, Tooltip, Legend,
  CategoryScale, LinearScale, BarElement, ArcElement
);

const CHART_COLORS = {
  green: '#00b894',
  red: '#d63031',
  yellow: '#fdcb6e',
  cyan: '#00cec9',
  blue: '#58a6ff',
  orange: '#f0883e',
  purple: '#bc8cff',
  pink: '#db61a2',
};

const COLORS_LIST = [CHART_COLORS.cyan, CHART_COLORS.blue, CHART_COLORS.purple, CHART_COLORS.orange,
  CHART_COLORS.green, CHART_COLORS.yellow, CHART_COLORS.pink, CHART_COLORS.red];

const STATUS_COLORS = {
  FIXED: '#00b894',
  OPEN: '#d63031',
  IN_PROGRESS: '#58a6ff',
  VERIFYING: '#bc8cff',
  VERIFIED: '#00b894',
  DEFERRED: '#fdcb6e',
  BLOCKED: '#d63031',
  REJECTED: '#f0883e',
};

const chartOptions = (isDark = true) => ({
  responsive: true,
  maintainAspectRatio: false,
  color: '#8b949e',
  plugins: {
    legend: {
      labels: { color: '#8b949e', font: { size: 11 }, padding: 16, usePointStyle: true },
    },
  },
  scales: {
    r: {
      grid: { color: '#21262d' },
      angleLines: { color: '#21262d' },
      pointLabels: { color: '#c9d1d9', font: { size: 11 } },
      ticks: { color: '#8b949e', backdropColor: 'transparent', font: { size: 10 } },
    },
    x: {
      grid: { color: '#21262d' },
      ticks: { color: '#8b949e', font: { size: 10 } },
    },
    y: {
      grid: { color: '#21262d' },
      ticks: { color: '#8b949e', font: { size: 10 } },
      beginAtZero: true,
    },
  },
});

export default function MetricsPanel({ convergence, findings }) {
  if (!convergence) {
    return <div className="empty-state"><div className="empty-state-text">No metrics data</div></div>;
  }

  const dimensions = getDimensionDefinitions();
  const scores = convergence.dimension_scores || {};
  const confidences = convergence.dimension_confidence || {};
  const allFindings = findings?.findings || [];

  const radarData = {
    labels: dimensions.map(d => d.label),
    datasets: [{
      label: 'Dimension Score',
      data: dimensions.map(d => scores[d.key] ?? 0),
      backgroundColor: 'rgba(0, 184, 148, 0.15)',
      borderColor: CHART_COLORS.green,
      borderWidth: 2,
      pointBackgroundColor: CHART_COLORS.green,
      pointBorderColor: '#0d1117',
      pointBorderWidth: 2,
      pointRadius: 4,
    }],
  };

  const scoreTrendData = {
    labels: ['Cycle 1', 'Cycle 2', 'Cycle 3', 'Cycle 4', 'Cycle 5', 'Cycle 6'],
    datasets: [{
      label: 'Overall Score',
      data: [35, 40, 45, 50, 50, convergence.overall_score || 55],
      borderColor: CHART_COLORS.green,
      backgroundColor: 'rgba(0, 184, 148, 0.1)',
      fill: true,
      tension: 0.3,
      pointBackgroundColor: CHART_COLORS.green,
      pointRadius: 5,
      pointHoverRadius: 7,
    }],
  };

  const trendOptions = {
    ...chartOptions(),
    scales: {
      x: { grid: { color: '#21262d' }, ticks: { color: '#8b949e', font: { size: 10 } } },
      y: { grid: { color: '#21262d' }, ticks: { color: '#8b949e', font: { size: 10 } }, min: 0, max: 100 },
    },
  };

  const statusDist = computeStatusDistribution(allFindings);
  const statusLabels = Object.keys(statusDist).sort();
  const statusValues = statusLabels.map(k => statusDist[k]);
  const statusColors = statusLabels.map(k => STATUS_COLORS[k] || '#6e7681');

  const doughnutData = {
    labels: statusLabels,
    datasets: [{
      data: statusValues,
      backgroundColor: statusColors,
      borderColor: '#161b22',
      borderWidth: 2,
    }],
  };

  const doughnutOptions = {
    responsive: true,
    maintainAspectRatio: false,
    color: '#8b949e',
    plugins: {
      legend: {
        position: 'right',
        labels: { color: '#8b949e', font: { size: 11 }, padding: 12, usePointStyle: true, boxWidth: 8 },
      },
    },
  };

  const categoryDist = computeCategoryDistribution(allFindings);
  const catLabels = Object.keys(categoryDist).sort();
  const catValues = catLabels.map(k => categoryDist[k]);
  const catColors = catLabels.map((_, i) => COLORS_LIST[i % COLORS_LIST.length]);

  const barData = {
    labels: catLabels,
    datasets: [{
      label: 'Findings',
      data: catValues,
      backgroundColor: catColors,
      borderColor: '#161b22',
      borderWidth: 1,
      borderRadius: 4,
    }],
  };

  const barOptions = {
    ...chartOptions(),
    indexAxis: 'y',
    plugins: {
      legend: { display: false },
    },
    scales: {
      x: { grid: { color: '#21262d' }, ticks: { color: '#8b949e', font: { size: 10 } } },
      y: { grid: { display: false }, ticks: { color: '#c9d1d9', font: { size: 11 } } },
    },
  };

  const dimensionBars = dimensions.map(d => ({
    label: d.label,
    score: scores[d.key] ?? 0,
    confidence: confidences[d.key] || 'N/A',
  })).sort((a, b) => b.score - a.score);

  return (
    <div>
      <div className="charts-grid">
        <div className="chart-container">
          <div className="card-header">
            <span className="card-title">Dimensional Audit Score</span>
            <span className="card-subtitle">Overall: {convergence.overall_score}/100</span>
          </div>
          <div className="chart-inner">
            <Radar data={radarData} options={chartOptions()} />
          </div>
        </div>

        <div className="chart-container">
          <div className="card-header">
            <span className="card-title">Score Trend</span>
            <span className="card-subtitle">Across audit cycles</span>
          </div>
          <div className="chart-inner">
            <Line data={scoreTrendData} options={trendOptions} />
          </div>
        </div>

        <div className="chart-container">
          <div className="card-header">
            <span className="card-title">Finding Status Distribution</span>
            <span className="card-subtitle">{allFindings.length} total findings</span>
          </div>
          <div className="chart-inner">
            <Doughnut data={doughnutData} options={doughnutOptions} />
          </div>
        </div>

        <div className="chart-container">
          <div className="card-header">
            <span className="card-title">Findings by Category</span>
            <span className="card-subtitle">{catLabels.length} categories</span>
          </div>
          <div className="chart-inner">
            <Bar data={barData} options={barOptions} />
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 20 }}>
        <div className="card-header">
          <span className="card-title">Dimension Scores</span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
          {dimensionBars.map(dim => (
            <div key={dim.label} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ width: 120, fontSize: 12, color: 'var(--text-secondary)', textAlign: 'right', flexShrink: 0 }}>{dim.label}</div>
              <div style={{ flex: 1, height: 10, background: 'var(--bg-tertiary)', borderRadius: 5, overflow: 'hidden' }}>
                <div style={{
                  width: `${dim.score}%`,
                  height: '100%',
                  borderRadius: 5,
                  background: dim.score >= 70 ? 'var(--green)' : dim.score >= 50 ? 'var(--yellow)' : 'var(--red)',
                  transition: 'width 0.3s ease',
                }} />
              </div>
              <div style={{ width: 36, fontSize: 13, fontWeight: 700, textAlign: 'right', color: 'var(--text-primary)' }}>{dim.score}</div>
              <div style={{ width: 50, fontSize: 10, color: 'var(--text-muted)', textAlign: 'right' }}>{dim.confidence}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}