import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { api } from '../api/client';

const TIER_COLORS = {
  HIGH:   { text: '#00c853', bg: 'rgba(0,200,83,0.10)',   border: 'rgba(0,200,83,0.25)' },
  MEDIUM: { text: '#f59e0b', bg: 'rgba(245,158,11,0.10)', border: 'rgba(245,158,11,0.25)' },
  LOW:    { text: '#8b949e', bg: 'rgba(139,148,158,0.10)',border: 'rgba(139,148,158,0.25)' },
};

function StatBox({ label, value, sub, color = 'var(--text-primary)', delay = 0 }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.4 }}
      style={{ padding: '1.25rem', borderRadius: 12, border: '1px solid var(--border)', background: 'var(--bg-card)', textAlign: 'center' }}
    >
      <div style={{ fontSize: '1.8rem', fontWeight: 900, color, fontFamily: 'Space Grotesk, sans-serif', lineHeight: 1 }}>{value}</div>
      <div style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-secondary)', marginTop: 6 }}>{label}</div>
      {sub && <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: 2 }}>{sub}</div>}
    </motion.div>
  );
}

function PnlCurve({ data }) {
  if (!data || data.length < 2) return null;
  const min = Math.min(0, ...data);
  const max = Math.max(0, ...data);
  const range = max - min || 1;
  const W = 500, H = 100;
  const toX = i => (i / (data.length - 1)) * W;
  const toY = v => H - ((v - min) / range) * H;
  const pts  = data.map((v, i) => `${toX(i)},${toY(v)}`).join(' ');
  const area = `0,${H} ` + data.map((v, i) => `${toX(i)},${toY(v)}`).join(' ') + ` ${W},${H}`;
  const zeroY = toY(0);
  const final = data[data.length - 1];
  const color = final >= 0 ? '#00c853' : '#ef4444';

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '0.5rem' }}>
        <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          Cumulative P&L
        </p>
        <span style={{ fontSize: '0.9rem', fontWeight: 800, color, fontFamily: 'Space Grotesk' }}>
          {final >= 0 ? '+' : ''}${final.toFixed(0)}
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 120, overflow: 'visible' }} preserveAspectRatio="none">
        <defs>
          <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.18" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        <polygon points={area} fill="url(#areaGrad)" />
        <line x1={0} y1={zeroY} x2={W} y2={zeroY} stroke="var(--border)" strokeWidth="1" strokeDasharray="4 4" />
        <polyline points={pts} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" />
      </svg>
    </div>
  );
}

function MonthBar({ month, roi, maxRoi, index }) {
  const positive = roi >= 0;
  const barH = maxRoi > 0 ? Math.abs(roi / maxRoi) * 70 : 0;
  return (
    <motion.div
      initial={{ opacity: 0 }} animate={{ opacity: 1 }}
      transition={{ delay: index * 0.03 }}
      style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3, flex: 1, minWidth: 0 }}
    >
      <span style={{ fontSize: '0.6rem', fontWeight: 700, color: positive ? 'var(--accent-green)' : 'var(--accent-red)', whiteSpace: 'nowrap' }}>
        {positive ? '+' : ''}{roi}%
      </span>
      <div style={{ width: '80%', maxWidth: 28, height: 70, display: 'flex', alignItems: 'flex-end', justifyContent: 'center' }}>
        <motion.div
          initial={{ height: 0 }} animate={{ height: barH }}
          transition={{ delay: index * 0.03 + 0.15, duration: 0.4, ease: 'easeOut' }}
          style={{ width: '100%', borderRadius: 3,
            background: positive ? 'linear-gradient(180deg,#00c853,rgba(0,200,83,0.3))' : 'linear-gradient(180deg,#ef4444,rgba(239,68,68,0.3))' }}
        />
      </div>
      <span style={{ fontSize: '0.6rem', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{month.slice(5)}</span>
    </motion.div>
  );
}

function Accuracy() {
  const [acc, setAcc] = useState(null);

  useEffect(() => { api.kAccuracy().then(setAcc).catch(() => {}); }, []);

  if (!acc) return <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>Loading...</div>;

  const resolved = acc.records.filter(r => r.actual_ks !== null);

  // Aggregate to season totals per pitcher
  const byPitcher = {};
  for (const r of resolved) {
    if (!byPitcher[r.pitcher_name]) byPitcher[r.pitcher_name] = { pred: 0, actual: 0, starts: 0 };
    byPitcher[r.pitcher_name].pred   += r.predicted_ks;
    byPitcher[r.pitcher_name].actual += r.actual_ks;
    byPitcher[r.pitcher_name].starts += 1;
  }
  const pitchers = Object.entries(byPitcher)
    .filter(([, v]) => v.starts >= 3)  // need at least 3 starts for a meaningful total
    .map(([name, v]) => ({ name, ...v, pctErr: Math.abs(v.pred - v.actual) / v.actual * 100 }));

  // Season-level %MAE: average % error on season K totals across pitchers
  const seasonPctMae = pitchers.length > 0
    ? (pitchers.reduce((s, p) => s + p.pctErr, 0) / pitchers.length).toFixed(1)
    : null;

  // Scatter bounds
  const W = 400, H = 220;
  const allTotals = pitchers.flatMap(p => [p.pred, p.actual]);
  const minV = allTotals.length ? Math.max(0, Math.min(...allTotals) * 0.9) : 0;
  const maxV = allTotals.length ? Math.max(...allTotals) * 1.05 : 100;
  const toX = v => ((v - minV) / (maxV - minV)) * W;
  const toY = v => H - ((v - minV) / (maxV - minV)) * H;

  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '0.85rem', marginBottom: '1.5rem' }}>
        <StatBox label="Season % MAE" value={seasonPctMae != null ? `${seasonPctMae}%` : '—'}
          sub={pitchers.length ? `${pitchers.length} pitchers` : 'need 3+ starts'}
          color="var(--accent-blue)" delay={0} />
        <StatBox label="Game MAE" value={acc.mae != null ? `${acc.mae} K` : '—'}
          sub="per start" delay={0.05} />
        <StatBox label="Within 1K" value={acc.within_1 != null ? `${acc.within_1}%` : '—'} color="var(--accent-green)" delay={0.1} />
        <StatBox label="Within 2K" value={acc.within_2 != null ? `${acc.within_2}%` : '—'} color="var(--accent-green)" delay={0.15} />
      </div>

      {pitchers.length > 1 && (
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
          style={{ padding: '1.25rem', borderRadius: 12, border: '1px solid var(--border)', background: 'var(--bg-card)', marginBottom: '1.25rem' }}>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.75rem' }}>
            Season K Total: Predicted vs Actual (one dot per pitcher, 3+ starts)
          </p>
          <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 240, overflow: 'visible' }}>
            {/* Perfect prediction diagonal */}
            <line x1={toX(minV)} y1={toY(minV)} x2={toX(maxV)} y2={toY(maxV)}
              stroke="var(--border)" strokeWidth="1" strokeDasharray="4 4" />
            {pitchers.map((p, i) => {
              const color = p.pctErr <= 5 ? '#00c853' : p.pctErr <= 12 ? '#f59e0b' : '#ef4444';
              return (
                <circle key={i} cx={toX(p.pred)} cy={toY(p.actual)}
                  r={Math.min(4 + p.starts * 0.3, 8)} fill={color} fillOpacity={0.75} stroke={color} strokeWidth={1}>
                  <title>{p.name}: pred {p.pred.toFixed(0)}K / actual {p.actual.toFixed(0)}K over {p.starts} starts ({p.pctErr.toFixed(1)}% off)</title>
                </circle>
              );
            })}
          </svg>
          <div style={{ display: 'flex', gap: '1rem', marginTop: '0.25rem', fontSize: '0.68rem', color: 'var(--text-muted)' }}>
            <span><span style={{ color: '#00c853' }}>●</span> within 5%</span>
            <span><span style={{ color: '#f59e0b' }}>●</span> within 12%</span>
            <span><span style={{ color: '#ef4444' }}>●</span> off by 12%+</span>
            <span style={{ marginLeft: 'auto' }}>dot size = starts logged · dashed = perfect</span>
          </div>
        </motion.div>
      )}

      {pitchers.length > 0 && (
        <div style={{ borderRadius: 10, border: '1px solid var(--border)', overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
            <thead>
              <tr style={{ background: 'var(--bg-secondary)' }}>
                {['Pitcher','Starts','Predicted Ks','Actual Ks','Diff','% Off'].map(h => (
                  <th key={h} style={{ padding: '0.5rem 0.75rem', fontSize: '0.7rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', borderBottom: '1px solid var(--border)', textAlign: 'left', whiteSpace: 'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...pitchers].sort((a, b) => a.pctErr - b.pctErr).map((p, i) => {
                const diff = p.pred - p.actual;
                const pctColor = p.pctErr <= 5 ? '#00c853' : p.pctErr <= 12 ? '#f59e0b' : '#ef4444';
                return (
                  <tr key={p.name} style={{ borderTop: '1px solid var(--border)', background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)' }}>
                    <td style={{ padding: '0.5rem 0.75rem', fontWeight: 600, color: 'var(--text-primary)' }}>{p.name}</td>
                    <td style={{ padding: '0.5rem 0.75rem', color: 'var(--text-muted)' }}>{p.starts}</td>
                    <td style={{ padding: '0.5rem 0.75rem', color: 'var(--text-secondary)' }}>{p.pred.toFixed(1)}</td>
                    <td style={{ padding: '0.5rem 0.75rem', fontWeight: 700, color: 'var(--text-primary)' }}>{p.actual.toFixed(1)}</td>
                    <td style={{ padding: '0.5rem 0.75rem', fontWeight: 600,
                      color: diff > 0 ? 'var(--accent-red)' : diff < 0 ? 'var(--accent-green)' : 'var(--text-muted)' }}>
                      {diff > 0 ? '+' : ''}{diff.toFixed(1)}K
                    </td>
                    <td style={{ padding: '0.5rem 0.75rem', fontWeight: 700, color: pctColor }}>
                      {p.pctErr.toFixed(1)}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {acc.records.length === 0 && (
        <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
          No predictions logged yet. Predictions are saved automatically each morning when the slate loads.
        </div>
      )}
    </div>
  );
}

export default function PerformancePanel() {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);
  const [view, setView]       = useState('overview');

  useEffect(() => {
    api.performance()
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>Loading backtest results...</div>
  );

  if (error) return (
    <div style={{ padding: '1rem 1.25rem', borderRadius: 10, background: 'rgba(245,158,11,0.07)', border: '1px solid rgba(245,158,11,0.2)', fontSize: '0.85rem', color: 'var(--accent-amber)' }}>
      <strong>Backtest not run yet.</strong>
      <div style={{ marginTop: 6, color: 'var(--text-muted)', fontFamily: 'monospace', fontSize: '0.8rem' }}>
        cd backend<br />python -m train.backtest
      </div>
    </div>
  );

  const { overall, byTier, monthly, cumulative_pnl, bankroll, kelly_frac } = data;
  const maxRoi   = Math.max(...monthly.map(m => Math.abs(m.roi)), 1);
  const roiColor = overall.roi.startsWith('+') ? 'var(--accent-green)' : 'var(--accent-red)';
  const pnlColor = overall.pnl >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';

  return (
    <div>
      {/* Tab switcher */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem' }}>
        {[['overview','Overview'],['accuracy','Accuracy']].map(([v, label]) => (
          <button key={v} onClick={() => setView(v)} style={{
            padding: '6px 16px', borderRadius: 8, fontSize: '0.82rem', fontWeight: 600,
            cursor: 'pointer', border: '1px solid',
            background: view === v ? 'rgba(29,155,240,0.12)' : 'transparent',
            borderColor: view === v ? 'rgba(29,155,240,0.4)' : 'var(--border)',
            color: view === v ? 'var(--accent-blue)' : 'var(--text-muted)',
          }}>{label}</button>
        ))}
      </div>

      {view === 'accuracy' && <Accuracy />}

      {view === 'overview' && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '0.85rem', marginBottom: '2rem' }}>
            <StatBox label="Win Rate" value={overall.winRate} color="var(--accent-green)" delay={0} />
            <StatBox label="ROI"      value={overall.roi}     color={roiColor}            delay={0.05} />
            <StatBox label="P&L"      value={`${overall.pnl >= 0 ? '+$' : '-$'}${Math.abs(overall.pnl).toFixed(0)}`} color={pnlColor} delay={0.1} />
            <StatBox label="Total Bets" value={overall.bets} sub={`${overall.wins}W · ${overall.losses}L · ${overall.pushes}P`} delay={0.15} />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.25rem', marginBottom: '1.25rem' }}>
            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2, duration: 0.4 }}
              style={{ padding: '1.25rem', borderRadius: 12, border: '1px solid var(--border)', background: 'var(--bg-card)' }}>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '1rem' }}>By Confidence</p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
                {Object.entries(byTier).map(([tier, stats]) => {
                  const c = TIER_COLORS[tier] ?? TIER_COLORS.LOW;
                  const winPct = stats.wins / Math.max(stats.wins + stats.losses, 1);
                  return (
                    <div key={tier}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5 }}>
                        <span style={{ fontSize: '0.72rem', fontWeight: 700, padding: '2px 8px', borderRadius: 999, background: c.bg, border: `1px solid ${c.border}`, color: c.text }}>{tier}</span>
                        <div style={{ display: 'flex', gap: '0.75rem', fontSize: '0.78rem' }}>
                          <span style={{ color: 'var(--text-muted)' }}>{stats.bets} bets</span>
                          <span style={{ color: c.text, fontWeight: 700 }}>{stats.winRate}</span>
                          <span style={{ color: stats.roi.startsWith('+') ? 'var(--accent-green)' : 'var(--accent-red)', fontWeight: 700 }}>{stats.roi}</span>
                        </div>
                      </div>
                      <div style={{ height: 4, borderRadius: 2, background: 'var(--border)', overflow: 'hidden' }}>
                        <motion.div initial={{ width: 0 }} animate={{ width: `${winPct * 100}%` }} transition={{ delay: 0.3, duration: 0.6, ease: 'easeOut' }}
                          style={{ height: '100%', background: c.text, borderRadius: 2 }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </motion.div>

            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25, duration: 0.4 }}
              style={{ padding: '1.25rem', borderRadius: 12, border: '1px solid var(--border)', background: 'var(--bg-card)' }}>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '1rem' }}>Monthly ROI</p>
              <div style={{ display: 'flex', gap: '0.25rem', alignItems: 'flex-end', justifyContent: 'space-between', overflowX: 'auto' }}>
                {monthly.slice(-12).map((m, i) => <MonthBar key={m.month} {...m} maxRoi={maxRoi} index={i} />)}
              </div>
            </motion.div>
          </div>

          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35, duration: 0.4 }}
            style={{ padding: '1.25rem', borderRadius: 12, border: '1px solid var(--border)', background: 'var(--bg-card)', marginBottom: '1.25rem' }}>
            <PnlCurve data={cumulative_pnl} />
          </motion.div>

          <div style={{ padding: '0.75rem 1rem', borderRadius: 8, background: 'rgba(29,155,240,0.06)', border: '1px solid rgba(29,155,240,0.15)', fontSize: '0.78rem', color: 'var(--text-muted)', lineHeight: 1.6 }}>
            Walk-forward backtest · 2024–2025 seasons · ${bankroll} bankroll · {kelly_frac * 100}% Kelly · HIGH confidence only · real DraftKings/FanDuel lines · live bets appended as they settle.
          </div>
        </>
      )}
    </div>
  );
}
