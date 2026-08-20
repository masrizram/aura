const API_BASE = process.env.REACT_APP_API_BASE || '/api';

async function fetchJSON(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch ${path}: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

let cachedConvergence = null;
let cachedFindings = null;
let cachedCycle = null;
let cachedToolingEvidence = null;

export async function loadAll() {
  try {
    const [convergence, findings, cycle] = await Promise.all([
      fetchJSON('/state/convergence.json').catch(() => null),
      fetchJSON('/state/findings.json').catch(() => null),
      fetchJSON('/state/cycle.json').catch(() => null),
    ]);

    cachedConvergence = convergence;
    cachedFindings = findings;
    cachedCycle = cycle;

    try {
      cachedToolingEvidence = await fetchJSON('/state/tooling-evidence.json');
    } catch {
      cachedToolingEvidence = null;
    }

    return { convergence, findings, cycle, toolingEvidence: cachedToolingEvidence };
  } catch (err) {
    console.warn('API unavailable, using static imports');
    return {
      convergence: cachedConvergence,
      findings: cachedFindings,
      cycle: cachedCycle,
      toolingEvidence: cachedToolingEvidence,
    };
  }
}

export function getConvergence() { return cachedConvergence; }
export function getFindings() { return cachedFindings; }
export function getCycle() { return cachedCycle; }
export function getToolingEvidence() { return cachedToolingEvidence; }

export function getGateDefinitions() {
  return [
    { id: 'P0_zero', number: 1, name: 'P0 Zero', desc: 'Zero open P0 (catastrophic) findings' },
    { id: 'P1_zero', number: 2, name: 'P1 Zero', desc: 'Zero open P1 (critical) findings' },
    { id: 'P2_zero', number: 3, name: 'P2 Zero', desc: 'Zero open P2 (high) findings' },
    { id: 'critical_security', number: 4, name: 'Critical Security', desc: 'All SECURITY P0-P2 findings VERIFIED' },
    { id: 'critical_correctness', number: 5, name: 'Critical Correctness', desc: 'All CORRECTNESS P0-P2 findings VERIFIED' },
    { id: 'data_integrity', number: 6, name: 'Data Integrity', desc: 'All DATA_INTEGRITY findings VERIFIED' },
    { id: 'regression', number: 7, name: 'Regression', desc: 'Zero re-appeared findings from previous cycles' },
    { id: 'verification', number: 8, name: 'Verification', desc: 'All FIXED findings have independent verifier evidence' },
    { id: 'no_material_new_findings', number: 9, name: 'No New Findings', desc: 'Zero new P0-P3 findings for 2 consecutive cycles' },
    { id: 'limitations_documented', number: 10, name: 'Limitations Documented', desc: 'Remaining limitations explicitly listed' },
    { id: 'consecutive_clean_independent_audits', number: 11, name: 'Consecutive Clean Audits', desc: '2 cycles with zero new P0-P3 AND 3+ independent cycles' },
    { id: 'module_dependency_integrity', number: 12, name: 'Module Integrity', desc: 'All required modules loaded (orchestrator-controlled)' },
  ];
}

export function getDimensionDefinitions() {
  return [
    { key: 'Architecture', label: 'Architecture', weight: 0.14 },
    { key: 'Correctness', label: 'Correctness', weight: 0.16 },
    { key: 'Security', label: 'Security', weight: 0.18 },
    { key: 'Reliability', label: 'Reliability', weight: 0.12 },
    { key: 'Performance', label: 'Performance', weight: 0.08 },
    { key: 'Testing', label: 'Testing', weight: 0.12 },
    { key: 'Observability', label: 'Observability', weight: 0.06 },
    { key: 'Operations', label: 'Operations', weight: 0.06 },
    { key: 'Maintainability', label: 'Maintainability', weight: 0.04 },
    { key: 'Documentation', label: 'Documentation', weight: 0.04 },
  ];
}

export function computeSeverityStats(findings) {
  if (!findings) return { P0: 0, P1: 0, P2: 0, P3: 0, P4: 0, P5: 0 };
  const open = findings.filter(f => f.status === 'OPEN' || f.status === 'IN_PROGRESS' || f.status === 'VERIFYING' || f.status === 'REJECTED');
  return {
    P0: open.filter(f => f.severity === 'P0').length,
    P1: open.filter(f => f.severity === 'P1').length,
    P2: open.filter(f => f.severity === 'P2').length,
    P3: open.filter(f => f.severity === 'P3').length,
    P4: open.filter(f => f.severity === 'P4').length,
    P5: open.filter(f => f.severity === 'P5').length,
  };
}

export function computeStatusDistribution(findings) {
  if (!findings) return {};
  const dist = {};
  findings.forEach(f => {
    dist[f.status] = (dist[f.status] || 0) + 1;
  });
  return dist;
}

export function computeCategoryDistribution(findings) {
  if (!findings) return {};
  const dist = {};
  findings.forEach(f => {
    dist[f.category] = (dist[f.category] || 0) + 1;
  });
  return dist;
}