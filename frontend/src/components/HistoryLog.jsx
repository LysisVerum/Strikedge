import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { ChevronUp, ChevronDown } from 'lucide-react';
import { api } from '../api/client';

const RESULT_STYLE = {
  WIN:  { bg: 'rgba(0,200,83,0.10)',    border: 'rgba(0,200,83,0.25)',    text: '#00c853' },
  LOSS: { bg: 'rgba(239,68,68,0.10)',   border: 'rgba(239,68,68,0.25)',   text: '#ef4444' },
  PUSH: { bg: 'rgba(139,148,158,0.10)', border: 'rgba(139,148,158,0.25)', text: '#8b949e' },
};

const CONF_COLORS = {
  HIGH:   '#00c853',
  MEDIUM: '#f59e0b',
  LOW:    '#8b949e',
};

export default function HistoryLog() {
  const [records, setRecords]  = useState([]);
  const [loading, setLoading]  = useState(true);
  const [sortKey, setSortKey]  = useState('date');
  const [sortDir, setSortDir]  = useState('desc');
  const [filter, setFilter]    = useState('ALL');

  useEffect(() => {
    api.liveRecord()
      .then(data => setRecords(data.records || []))
      .catch(() => setRecords([]))
      .finally(() => setLoading(false));
  }, []);

  const toggleSort = (key) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortKey(key); setSortDir('desc'); }
  };

  const resolved = records.filter(r => r.outcome !== null && r.outcome !== undefined);
  const filtered = filter === 'ALL' ? resolved : resolved.filter(r => r.outcome === filter);

  const sorted = [...filtered].sort((a, b) => {
    let av = a[sortKey], bv = b[sortKey];
    if (av < bv) return sortDir === 'asc' ? -1 : 1;
    if (av > bv) return sortDir === 'asc' ? 1 : -1;
    return 0;
  });

  const wins   = resolved.filter(r => r.outcome === 'WIN').length;
  const losses = resolved.filter(r => r.outcome === 'LOSS').length;
  const pushes = resolved.filter(r => r.outcome === 'PUSH').length;
  const pending = records.filter(r => !r.outcome).length;

  const SortIcon = ({ k }) => {
    if (sortKey !== k) return <span style={{ opacity: 0.3, fontSize: '0.65rem' }}>⇅</span>;
    return sortDir === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />;
  };

  const ColHeader = ({ label, k, style = {} }) => (
    <th onClick={() => toggleSort(k)} style={{
      padding: '0.6rem 0.75rem', textAlign: 'left',
      fontSize: '0.7rem', color: 'var(--text-muted)',
      textTransform: 'uppercase', letterSpacing: '0.08em',
      cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap',
      ...style,
    }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3 }}>
        {label} <SortIcon k={k} />
      </span>
    </th>
  );

  if (loading) return <div style={{ color: 'var(--text-muted)', padding: '2rem', textAlign: 'center' }}>Loading history...</div>;

  if (resolved.length === 0) return (
    <div style={{ color: 'var(--text-muted)', padding: '2rem', textAlign: 'center' }}>
      No resolved bets yet. Submit lines in the Live Record tab and results auto-update each day.
    </div>
  );

  return (
    <div>
      {/* Summary strip */}
      <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.25rem', flexWrap: 'wrap', alignItems: 'center' }}>
        {[
          { label: 'ALL',  count: resolved.length },
          { label: 'WIN',  count: wins },
          { label: 'LOSS', count: losses },
          { label: 'PUSH', count: pushes },
        ].map(({ label, count }) => (
          <motion.button key={label} whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.96 }}
            onClick={() => setFilter(label)}
            style={{
              padding: '0.35rem 0.85rem', borderRadius: 8, cursor: 'pointer',
              border: `1px solid ${filter === label ? (RESULT_STYLE[label]?.border ?? 'var(--accent-blue)') : 'var(--border)'}`,
              background: filter === label ? (RESULT_STYLE[label]?.bg ?? 'var(--glow-blue)') : 'transparent',
              color: filter === label ? (RESULT_STYLE[label]?.text ?? 'var(--accent-blue)') : 'var(--text-muted)',
              fontSize: '0.8rem', fontWeight: 600,
            }}>
            {label} <span style={{ opacity: 0.7 }}>({count})</span>
          </motion.button>
        ))}
        <div style={{ marginLeft: 'auto', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
          {wins}W · {losses}L · {pushes}P
          {pending > 0 && <span style={{ marginLeft: 6, color: 'var(--accent-blue)' }}>· {pending} pending</span>}
          {(wins + losses) > 0 && (
            <span style={{ marginLeft: 8, color: 'var(--accent-green)', fontWeight: 700 }}>
              {((wins / (wins + losses)) * 100).toFixed(1)}% win rate
            </span>
          )}
        </div>
      </div>

      {/* Table */}
      <div style={{ borderRadius: 12, border: '1px solid var(--border)', overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: 'var(--bg-secondary)', borderBottom: '1px solid var(--border)' }}>
                <ColHeader label="Date"      k="date" />
                <ColHeader label="Pitcher"   k="pitcher_name" />
                <ColHeader label="Rec"       k="recommendation" />
                <ColHeader label="Line"      k="line" />
                <ColHeader label="Pred K"    k="predicted_ks" />
                <ColHeader label="Actual"    k="actual_ks" />
                <ColHeader label="Edge"      k="edge" />
                <ColHeader label="Conf"      k="confidence" />
                <ColHeader label="Bet"       k="bet" />
                <ColHeader label="P&L"       k="pnl" />
                <ColHeader label="Result"    k="outcome" />
              </tr>
            </thead>
            <tbody>
              {sorted.map((row, i) => {
                const rs = RESULT_STYLE[row.outcome] || RESULT_STYLE.PUSH;
                const edgePct = row.edge != null ? (row.edge * 100).toFixed(1) : '—';
                const edgePos = row.edge > 0;
                return (
                  <motion.tr key={`${row.date}-${row.pitcher_name}`}
                    initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.03 }}
                    style={{ borderBottom: '1px solid var(--border)', background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)' }}
                    onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-card-hover)'}
                    onMouseLeave={e => e.currentTarget.style.background = i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)'}
                  >
                    <td style={{ padding: '0.6rem 0.75rem', fontSize: '0.78rem', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{row.date}</td>
                    <td style={{ padding: '0.6rem 0.75rem', fontSize: '0.84rem', fontWeight: 600, color: 'var(--text-primary)', whiteSpace: 'nowrap' }}>{row.pitcher_name}</td>
                    <td style={{ padding: '0.6rem 0.75rem' }}>
                      <span style={{ fontSize: '0.72rem', fontWeight: 800, padding: '2px 8px', borderRadius: 999,
                        color: row.recommendation === 'OVER' ? '#00c853' : '#ef4444',
                        background: row.recommendation === 'OVER' ? 'rgba(0,200,83,0.12)' : 'rgba(239,68,68,0.12)',
                      }}>{row.recommendation}</span>
                    </td>
                    <td style={{ padding: '0.6rem 0.75rem', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>{row.line}</td>
                    <td style={{ padding: '0.6rem 0.75rem', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>{row.predicted_ks}</td>
                    <td style={{ padding: '0.6rem 0.75rem', fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-primary)', textAlign: 'center' }}>
                      {row.actual_ks != null ? `${row.actual_ks}K` : '—'}
                    </td>
                    <td style={{ padding: '0.6rem 0.75rem', fontSize: '0.82rem', fontWeight: 700,
                      color: edgePos ? 'var(--accent-green)' : 'var(--accent-red)', whiteSpace: 'nowrap' }}>
                      {edgePos ? '+' : ''}{edgePct}%
                    </td>
                    <td style={{ padding: '0.6rem 0.75rem' }}>
                      <span style={{
                        fontSize: '0.68rem', fontWeight: 700, padding: '2px 7px', borderRadius: 999,
                        color: CONF_COLORS[row.confidence] || '#8b949e',
                        background: (CONF_COLORS[row.confidence] || '#8b949e') + '18',
                        border: `1px solid ${(CONF_COLORS[row.confidence] || '#8b949e')}30`,
                      }}>{row.confidence}</span>
                    </td>
                    <td style={{ padding: '0.6rem 0.75rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>${row.bet?.toFixed(0) ?? '—'}</td>
                    <td style={{ padding: '0.6rem 0.75rem', fontSize: '0.82rem', fontWeight: 700,
                      color: (row.pnl ?? 0) >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                      {row.pnl != null ? `${row.pnl >= 0 ? '+' : ''}$${row.pnl.toFixed(0)}` : '—'}
                    </td>
                    <td style={{ padding: '0.6rem 0.75rem' }}>
                      <span style={{
                        fontSize: '0.72rem', fontWeight: 800, padding: '3px 10px', borderRadius: 999,
                        background: rs.bg, border: `1px solid ${rs.border}`, color: rs.text,
                      }}>{row.outcome}</span>
                    </td>
                  </motion.tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
