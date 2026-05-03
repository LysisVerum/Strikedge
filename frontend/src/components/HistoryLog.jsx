import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { ChevronUp, ChevronDown } from 'lucide-react';
import { api } from '../api/client';
import PitcherCard from './PitcherCard';

const RESULT_STYLE = {
  WIN:     { bg: 'rgba(0,200,83,0.10)',    border: 'rgba(0,200,83,0.25)',    text: '#00c853' },
  LOSS:    { bg: 'rgba(239,68,68,0.10)',   border: 'rgba(239,68,68,0.25)',   text: '#ef4444' },
  PUSH:    { bg: 'rgba(139,148,158,0.10)', border: 'rgba(139,148,158,0.25)', text: '#8b949e' },
  PENDING: { bg: 'rgba(29,155,240,0.08)',  border: 'rgba(29,155,240,0.2)',   text: '#1d9bf0' },
};

const CONF_COLORS = {
  HIGH:   '#00c853',
  MEDIUM: '#f59e0b',
  LOW:    '#8b949e',
};

export default function HistoryLog() {
  const [records, setRecords]   = useState([]);
  const [loading, setLoading]   = useState(true);
  const [sortKey, setSortKey]   = useState('date');
  const [sortDir, setSortDir]   = useState('desc');
  const [filter, setFilter]     = useState('ALL');
  const [cardPick, setCardPick] = useState(null);

  useEffect(() => {
    api.liveRecord()
      .then(data => setRecords((data.records || []).filter(r => r.bet > 0)))
      .catch(() => setRecords([]))
      .finally(() => setLoading(false));
  }, []);

  const toggleSort = (key) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortKey(key); setSortDir('desc'); }
  };

  async function handleDelete(date, pitcher_name) {
    try {
      await api.deleteLine({ date, pitcher_name });
      setRecords(prev => prev.filter(r => !(r.date === date && r.pitcher_name === pitcher_name)));
    } catch (e) {
      console.error('Delete failed:', e);
    }
  }

  const pending  = records.filter(r => !r.outcome);
  const resolved = records.filter(r =>  r.outcome);
  const wins   = resolved.filter(r => r.outcome === 'WIN').length;
  const losses = resolved.filter(r => r.outcome === 'LOSS').length;
  const pushes = resolved.filter(r => r.outcome === 'PUSH').length;

  const filtered =
    filter === 'ALL'     ? records :
    filter === 'PENDING' ? pending :
    resolved.filter(r => r.outcome === filter);

  const sorted = [...filtered].sort((a, b) => {
    let av = a[sortKey], bv = b[sortKey];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    if (av < bv) return sortDir === 'asc' ? -1 : 1;
    if (av > bv) return sortDir === 'asc' ? 1 : -1;
    return 0;
  });

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

  if (records.length === 0) return (
    <div style={{ color: 'var(--text-muted)', padding: '2rem', textAlign: 'center' }}>
      No picks logged yet. Picks are auto-logged each day when the slate loads.
    </div>
  );

  return (
    <div>
      {/* Summary strip */}
      <div style={{ display: 'flex', gap: '0.6rem', marginBottom: '1.25rem', flexWrap: 'wrap', alignItems: 'center' }}>
        {[
          { label: 'ALL',     count: records.length },
          { label: 'WIN',     count: wins },
          { label: 'LOSS',    count: losses },
          { label: 'PUSH',    count: pushes },
          { label: 'PENDING', count: pending.length },
        ].map(({ label, count }) => {
          const s = RESULT_STYLE[label] ?? RESULT_STYLE.PENDING;
          const active = filter === label;
          return (
            <motion.button key={label} whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.96 }}
              onClick={() => setFilter(label)}
              style={{
                padding: '0.35rem 0.85rem', borderRadius: 8, cursor: 'pointer',
                border: `1px solid ${active ? s.border : 'var(--border)'}`,
                background: active ? s.bg : 'transparent',
                color: active ? s.text : 'var(--text-muted)',
                fontSize: '0.8rem', fontWeight: 600,
              }}>
              {label} <span style={{ opacity: 0.7 }}>({count})</span>
            </motion.button>
          );
        })}
        <div style={{ marginLeft: 'auto', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
          {wins}W · {losses}L · {pushes}P
          {pending.length > 0 && <span style={{ marginLeft: 6, color: '#1d9bf0' }}>· {pending.length} pending</span>}
          {(wins + losses) > 0 && (
            <span style={{ marginLeft: 8, color: 'var(--accent-green)', fontWeight: 700 }}>
              {((wins / (wins + losses)) * 100).toFixed(1)}% win rate
            </span>
          )}
        </div>
      </div>

      {cardPick && (
        <PitcherCard
          pick={{
            pitcher_name:      cardPick.pitcher_name,
            matchup:           cardPick.matchup ?? cardPick.date ?? '',
            predicted_ks:      cardPick.predicted_ks,
            line:              cardPick.line,
            model_prob_over:   cardPick.model_prob_over ?? null,
            implied_prob_over: cardPick.implied_prob_over ?? null,
            edge_pct:          cardPick.edge,
            edge_pct_display:  cardPick.edge != null ? `${cardPick.edge >= 0 ? '+' : ''}${(cardPick.edge * 100).toFixed(1)}%` : '—',
            confidence:        cardPick.confidence,
            recommendation:    cardPick.recommendation,
            features:          cardPick.features ?? null,
          }}
          onClose={() => setCardPick(null)}
        />
      )}

      {/* Table */}
      <div style={{ borderRadius: 12, border: '1px solid var(--border)', overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: 'var(--bg-secondary)', borderBottom: '1px solid var(--border)' }}>
                <ColHeader label="Date"    k="date" />
                <ColHeader label="Pitcher" k="pitcher_name" />
                <ColHeader label="Rec"     k="recommendation" />
                <ColHeader label="Line"    k="line" />
                <ColHeader label="Pred K"  k="predicted_ks" />
                <ColHeader label="Actual"  k="actual_ks" />
                <ColHeader label="Edge"    k="edge" />
                <ColHeader label="Conf"    k="confidence" />
                <ColHeader label="Bet"     k="bet" />
                <ColHeader label="P&L"     k="pnl" />
                <ColHeader label="Result"  k="outcome" />
                <th style={{ padding: '0.6rem 0.5rem', width: 28 }} />
              </tr>
            </thead>
            <tbody>
              {sorted.map((row, i) => {
                const isPending = !row.outcome;
                const rs = isPending ? RESULT_STYLE.PENDING : (RESULT_STYLE[row.outcome] || RESULT_STYLE.PUSH);
                const edgePct = row.edge != null ? (row.edge * 100).toFixed(1) : '—';
                const edgePos = row.edge > 0;
                return (
                  <motion.tr key={`${row.date}-${row.pitcher_name}`}
                    initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.02 }}
                    style={{ borderBottom: '1px solid var(--border)', background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)', opacity: isPending ? 0.75 : 1 }}
                    onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-card-hover)'}
                    onMouseLeave={e => e.currentTarget.style.background = i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)'}
                  >
                    <td style={{ padding: '0.6rem 0.75rem', fontSize: '0.78rem', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{row.date}</td>
                    <td style={{ padding: '0.6rem 0.75rem', whiteSpace: 'nowrap' }}>
                      <button onClick={() => setCardPick(row)}
                        style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', fontSize: '0.84rem', fontWeight: 600, color: 'var(--text-primary)', textDecoration: 'underline dotted', textUnderlineOffset: 3 }}>
                        {row.pitcher_name}
                      </button>
                    </td>
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
                    <td style={{ padding: '0.6rem 0.75rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                      {row.bet != null ? `$${row.bet.toFixed(0)}` : '—'}
                    </td>
                    <td style={{ padding: '0.6rem 0.75rem', fontSize: '0.82rem', fontWeight: 700,
                      color: (row.pnl ?? 0) >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                      {row.pnl != null ? `${row.pnl >= 0 ? '+' : ''}$${row.pnl.toFixed(0)}` : '—'}
                    </td>
                    <td style={{ padding: '0.6rem 0.75rem' }}>
                      <span style={{
                        fontSize: '0.72rem', fontWeight: 800, padding: '3px 10px', borderRadius: 999,
                        background: rs.bg, border: `1px solid ${rs.border}`, color: rs.text,
                      }}>
                        {isPending ? 'PENDING' : row.outcome}
                      </span>
                    </td>
                    <td style={{ padding: '0.6rem 0.5rem', textAlign: 'center' }}>
                      {isPending && (
                        <button
                          onClick={() => handleDelete(row.date, row.pitcher_name)}
                          title="Remove pick"
                          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', fontSize: '0.85rem', padding: '2px 4px', borderRadius: 4, lineHeight: 1 }}
                          onMouseEnter={e => e.currentTarget.style.color = '#ef4444'}
                          onMouseLeave={e => e.currentTarget.style.color = 'var(--text-muted)'}
                        >✕</button>
                      )}
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
