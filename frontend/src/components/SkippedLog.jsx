import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { ChevronUp, ChevronDown } from 'lucide-react';
import { api } from '../api/client';
import PitcherCard from './PitcherCard';

const CONF_COLORS = {
  HIGH:   '#00c853',
  MEDIUM: '#f59e0b',
  LOW:    '#8b949e',
};

const REC_COLORS = {
  OVER:  { color: '#00c853', bg: 'rgba(0,200,83,0.12)' },
  UNDER: { color: '#ef4444', bg: 'rgba(239,68,68,0.12)' },
  PASS:  { color: '#8b949e', bg: 'rgba(139,148,158,0.12)' },
};

export default function SkippedLog() {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [sortKey, setSortKey] = useState('date');
  const [sortDir, setSortDir] = useState('desc');
  const [cardPick, setCardPick] = useState(null);

  useEffect(() => {
    api.skipped()
      .then(data => setRecords(Array.isArray(data) ? data : []))
      .catch(() => setRecords([]))
      .finally(() => setLoading(false));
  }, []);

  const toggleSort = (key) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortKey(key); setSortDir('desc'); }
  };

  const resolved  = records.filter(r => r.actual_ks != null);
  const pending   = records.filter(r => r.actual_ks == null);

  // Miss direction stats for resolved entries
  const avgMiss = resolved.length
    ? (resolved.reduce((s, r) => s + (r.miss ?? 0), 0) / resolved.length).toFixed(2)
    : null;
  const bigMisses = resolved.filter(r => Math.abs(r.miss ?? 0) >= 3);

  const sorted = [...records].sort((a, b) => {
    let av = a[sortKey], bv = b[sortKey];
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

  if (loading) return (
    <div style={{ color: 'var(--text-muted)', padding: '2rem', textAlign: 'center' }}>
      Loading skipped predictions...
    </div>
  );

  if (records.length === 0) return (
    <div style={{ color: 'var(--text-muted)', padding: '2rem', textAlign: 'center' }}>
      No skipped predictions yet. Bets below the 5% edge threshold will appear here with actual results for model analysis.
    </div>
  );

  return (
    <div>
      {cardPick && (
        <PitcherCard
          pick={{
            pitcher_name:      cardPick.pitcher_name,
            matchup:           cardPick.date ?? '',
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

      {/* Summary strip */}
      <div style={{ display: 'flex', gap: '1.5rem', marginBottom: '1.25rem', flexWrap: 'wrap', alignItems: 'center' }}>
        <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
          <span style={{ color: 'var(--text-primary)', fontWeight: 700 }}>{records.length}</span> skipped
          {pending.length > 0 && (
            <span style={{ marginLeft: 8, color: 'var(--accent-blue)' }}>· {pending.length} pending results</span>
          )}
        </div>
        {avgMiss != null && (
          <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
            Avg miss:{' '}
            <span style={{ fontWeight: 700, color: parseFloat(avgMiss) > 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}>
              {parseFloat(avgMiss) > 0 ? '+' : ''}{avgMiss}K
            </span>
            {' '}(actual − predicted)
          </div>
        )}
        {bigMisses.length > 0 && (
          <div style={{ fontSize: '0.82rem', color: '#f59e0b' }}>
            ⚠ {bigMisses.length} big miss{bigMisses.length > 1 ? 'es' : ''} (≥3K off)
          </div>
        )}
        <div style={{ marginLeft: 'auto', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
          Positive miss = pitcher outperformed model prediction
        </div>
      </div>

      {/* Table */}
      <div style={{ borderRadius: 12, border: '1px solid var(--border)', overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: 'var(--bg-secondary)', borderBottom: '1px solid var(--border)' }}>
                <ColHeader label="Date"       k="date" />
                <ColHeader label="Pitcher"    k="pitcher_name" />
                <ColHeader label="Would Bet"  k="recommendation" />
                <ColHeader label="Line"       k="line" />
                <ColHeader label="Pred K"     k="predicted_ks" />
                <ColHeader label="Actual"     k="actual_ks" />
                <ColHeader label="Miss"       k="miss" />
                <ColHeader label="Edge"       k="edge" />
                <ColHeader label="Conf"       k="confidence" />
                <ColHeader label="Skip Reason" k="skip_reason" />
              </tr>
            </thead>
            <tbody>
              {sorted.map((row, i) => {
                const rec   = REC_COLORS[row.recommendation] ?? REC_COLORS.PASS;
                const miss  = row.miss;
                const missColor = miss == null ? 'var(--text-muted)'
                  : Math.abs(miss) >= 3 ? '#f59e0b'
                  : miss > 0 ? 'var(--accent-green)' : 'var(--accent-red)';
                const edgePct = row.edge != null ? (row.edge * 100).toFixed(1) : '—';

                return (
                  <motion.tr key={`${row.date}-${row.pitcher_name}`}
                    initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.02 }}
                    style={{ borderBottom: '1px solid var(--border)', background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)' }}
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
                        color: rec.color, background: rec.bg,
                      }}>{row.recommendation ?? '—'}</span>
                    </td>
                    <td style={{ padding: '0.6rem 0.75rem', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>{row.line}</td>
                    <td style={{ padding: '0.6rem 0.75rem', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>{row.predicted_ks}</td>
                    <td style={{ padding: '0.6rem 0.75rem', fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-primary)', textAlign: 'center' }}>
                      {row.actual_ks != null ? `${row.actual_ks}K` : <span style={{ color: 'var(--accent-blue)', fontSize: '0.72rem' }}>pending</span>}
                    </td>
                    <td style={{ padding: '0.6rem 0.75rem', fontSize: '0.82rem', fontWeight: 700, color: missColor, textAlign: 'center' }}>
                      {miss != null ? `${miss > 0 ? '+' : ''}${miss}` : '—'}
                    </td>
                    <td style={{ padding: '0.6rem 0.75rem', fontSize: '0.82rem', fontWeight: 700,
                      color: (row.edge ?? 0) > 0 ? 'var(--accent-green)' : 'var(--accent-red)', whiteSpace: 'nowrap' }}>
                      {row.edge != null ? `${row.edge > 0 ? '+' : ''}${edgePct}%` : '—'}
                    </td>
                    <td style={{ padding: '0.6rem 0.75rem' }}>
                      <span style={{
                        fontSize: '0.68rem', fontWeight: 700, padding: '2px 7px', borderRadius: 999,
                        color: CONF_COLORS[row.confidence] || '#8b949e',
                        background: (CONF_COLORS[row.confidence] || '#8b949e') + '18',
                        border: `1px solid ${(CONF_COLORS[row.confidence] || '#8b949e')}30`,
                      }}>{row.confidence ?? '—'}</span>
                    </td>
                    <td style={{ padding: '0.6rem 0.75rem', fontSize: '0.75rem', color: 'var(--text-muted)', maxWidth: 180, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {row.skip_reason ?? '—'}
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
