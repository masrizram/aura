import React, { useState, useMemo } from 'react';

export default function FindingsTable({ findings }) {
  const [search, setSearch] = useState('');
  const [severityFilter, setSeverityFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [sortField, setSortField] = useState('id');
  const [sortDir, setSortDir] = useState('asc');
  const [expandedRows, setExpandedRows] = useState(new Set());

  const allFindings = findings?.findings || [];

  const uniqueSeverities = useMemo(() => [...new Set(allFindings.map(f => f.severity))].sort(), [allFindings]);
  const uniqueStatuses = useMemo(() => [...new Set(allFindings.map(f => f.status))].sort(), [allFindings]);
  const uniqueCategories = useMemo(() => [...new Set(allFindings.map(f => f.category))].sort(), [allFindings]);

  const filtered = useMemo(() => {
    let list = allFindings;
    const q = search.toLowerCase();
    if (q) {
      list = list.filter(f =>
        f.id.toLowerCase().includes(q) ||
        (f.problem || '').toLowerCase().includes(q) ||
        (f.category || '').toLowerCase().includes(q) ||
        (f.location || '').toLowerCase().includes(q)
      );
    }
    if (severityFilter) list = list.filter(f => f.severity === severityFilter);
    if (statusFilter) list = list.filter(f => f.status === statusFilter);
    if (categoryFilter) list = list.filter(f => f.category === categoryFilter);
    return list;
  }, [allFindings, search, severityFilter, statusFilter, categoryFilter]);

  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      let va = a[sortField] ?? '';
      let vb = b[sortField] ?? '';
      if (sortField === 'risk_score') { va = Number(va); vb = Number(vb); }
      if (va < vb) return sortDir === 'asc' ? -1 : 1;
      if (va > vb) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });
  }, [filtered, sortField, sortDir]);

  const handleSort = (field) => {
    if (sortField === field) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('asc');
    }
  };

  const toggleExpand = (id) => {
    setExpandedRows(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const renderSortIndicator = (field) => {
    if (sortField !== field) return null;
    return <span style={{ marginLeft: 4 }}>{sortDir === 'asc' ? '\u25B2' : '\u25BC'}</span>;
  };

  if (!allFindings.length) {
    return <div className="empty-state"><div className="empty-state-text">No findings data available</div></div>;
  }

  return (
    <div>
      <div className="table-controls">
        <input
          className="search-input"
          placeholder="Search findings..."
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <select className="filter-select" value={severityFilter} onChange={e => setSeverityFilter(e.target.value)}>
          <option value="">All Severities</option>
          {uniqueSeverities.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select className="filter-select" value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
          <option value="">All Statuses</option>
          {uniqueStatuses.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select className="filter-select" value={categoryFilter} onChange={e => setCategoryFilter(e.target.value)}>
          <option value="">All Categories</option>
          {uniqueCategories.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <span className="findings-count">
          {sorted.length} of {allFindings.length} findings
        </span>
      </div>

      <div className="table-wrapper">
        <table className="findings-table">
          <thead>
            <tr>
              <th onClick={() => handleSort('id')} className={sortField === 'id' ? 'sorted' : ''}>
                ID {renderSortIndicator('id')}
              </th>
              <th onClick={() => handleSort('severity')} className={sortField === 'severity' ? 'sorted' : ''}>
                Severity {renderSortIndicator('severity')}
              </th>
              <th onClick={() => handleSort('status')} className={sortField === 'status' ? 'sorted' : ''}>
                Status {renderSortIndicator('status')}
              </th>
              <th onClick={() => handleSort('category')} className={sortField === 'category' ? 'sorted' : ''}>
                Category {renderSortIndicator('category')}
              </th>
              <th onClick={() => handleSort('problem')} className={sortField === 'problem' ? 'sorted' : ''}>
                Problem {renderSortIndicator('problem')}
              </th>
              <th onClick={() => handleSort('risk_score')} className={sortField === 'risk_score' ? 'sorted' : ''}>
                Risk {renderSortIndicator('risk_score')}
              </th>
              <th style={{ width: 40 }}></th>
            </tr>
          </thead>
          <tbody>
            {sorted.map(f => {
              const isExpanded = expandedRows.has(f.id);
              return (
                <React.Fragment key={f.id}>
                  <tr className={isExpanded ? 'expanded' : ''}>
                    <td style={{ fontFamily: 'Consolas, monospace', fontSize: 12, color: 'var(--cyan)' }}>{f.id}</td>
                    <td><span className={`severity-badge severity-${f.severity}`}>{f.severity}</span></td>
                    <td><span className={`status-badge status-${f.status}`}>{f.status}</span></td>
                    <td><span className="category-badge">{f.category}</span></td>
                    <td style={{ maxWidth: 400, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.problem}</td>
                    <td style={{ textAlign: 'center', fontFamily: 'Consolas, monospace' }}>{f.risk_score}</td>
                    <td>
                      <button className="expand-row-btn" onClick={() => toggleExpand(f.id)}>
                        {isExpanded ? '\u25B2' : '\u25BC'}
                      </button>
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr>
                      <td colSpan={7} style={{ padding: 0 }}>
                        <div className="detail-panel">
                          <div className="detail-grid">
                            {f.location && (
                              <div className="detail-item">
                                <div className="detail-label">Location</div>
                                <div className="detail-value" style={{ fontFamily: 'Consolas, monospace', fontSize: 11 }}>{f.location}</div>
                              </div>
                            )}
                            {f.root_cause && (
                              <div className="detail-item">
                                <div className="detail-label">Root Cause</div>
                                <div className="detail-value">{f.root_cause}</div>
                              </div>
                            )}
                            {f.impact && (
                              <div className="detail-item">
                                <div className="detail-label">Impact</div>
                                <div className="detail-value">{f.impact}</div>
                              </div>
                            )}
                            {f.evidence && (
                              <div className="detail-item">
                                <div className="detail-label">Evidence</div>
                                <div className="detail-value">{f.evidence}</div>
                              </div>
                            )}
                            {f.recommended_fix && (
                              <div className="detail-item">
                                <div className="detail-label">Recommended Fix</div>
                                <div className="detail-value">{f.recommended_fix}</div>
                              </div>
                            )}
                            {f.implemented_fix && (
                              <div className="detail-item">
                                <div className="detail-label">Implemented Fix</div>
                                <div className="detail-value" style={{ color: 'var(--green)' }}>{f.implemented_fix}</div>
                              </div>
                            )}
                            {f.verification && (
                              <div className="detail-item">
                                <div className="detail-label">Verification</div>
                                <div className="detail-value" style={{ color: 'var(--cyan)' }}>{f.verification}</div>
                              </div>
                            )}
                            {f.confidence && (
                              <div className="detail-item">
                                <div className="detail-label">Confidence</div>
                                <div className="detail-value">{f.confidence}</div>
                              </div>
                            )}
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}