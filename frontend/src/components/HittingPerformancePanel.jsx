import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { api } from '../api/client';

const ACCENT        = '#f97316';
const ACCENT_BG     = 'rgba(249,115,22,0.10)';
const ACCENT_BORDER = 'rgba(249,115,22,0.20)';

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
  if (!data || data.length < 2) return (
    <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.82rem' }}>
      No resolved bets yet — P&L curve will appear as picks settle.
    </div>
  );
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
        <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Cumulative P&L</p>
        <span style={{ fontSize: '0.9rem', fontWeight: 800, color, fontFamily: 'Space Grotesk' }}>
          {final >= 0 ? '+' : ''}${final.toFixed(0)}
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 120, overflow: 'visible' }} preserveAspectRatio="none">
        <defs>
          <linearGradient id="hittingAreaGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.18" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        <polygon points={area} fill="url(#hittingAreaGrad)" />
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

function AccuracyView({ data }) {
  if (!data) return <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>Loading...</div>;

  const batters = (data.by_batter ?? []).filter(b => b.games >= 10);

  // Scatter bounds — season H totals: predicted vs actual
  const W = 400, H = 220;
  const allTotals = batters.flatMap(b => [b.pred, b.actual]);
  const minV = allTotals.length ? Math.max(0, Math.min(...allTotals) * 0.9) : 0;
  const maxV = allTotals.length ? Math.max(...allTotals) * 1.05 : 200;
  const toX = v => ((v - minV) / (maxV - minV)) * W;
  const toY = v => H - ((v - minV) / (maxV - minV)) * H;

  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '0.85rem', marginBottom: '1.5rem' }}>
        <StatBox label="Season % MAE" value={data.season_pct_mae != null ? `${data.season_pct_mae}%` : '—'}
          sub={batters.length ? `${batters.length} batters` : 'need 10+ games'}
          color={ACCENT} delay={0} />
        <StatBox label="Game MAE" value={data.mae != null ? `${data.mae.toFixed(2)} H` : '—'}
          sub="per game" delay={0.05} />
        <StatBox label="Within 0.5H" value={data.within_half != null ? `${data.within_half}%` : '—'} color="var(--accent-green)" delay={0.1} />
        <StatBox label="Within 1H"   value={data.within_one  != null ? `${data.within_one}%`  : '—'} color="var(--accent-green)" delay={0.15} />
      </div>

      {batters.length > 1 && (
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
          style={{ padding: '1.25rem', borderRadius: 12, border: '1px solid var(--border)', background: 'var(--bg-card)', marginBottom: '1.25rem' }}>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.75rem' }}>
            Season H Total: Predicted vs Actual (one dot per batter, 10+ games)
          </p>
          <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 240, overflow: 'visible' }}>
            <line x1={toX(minV)} y1={toY(minV)} x2={toX(maxV)} y2={toY(maxV)}
              stroke="var(--border)" strokeWidth="1" strokeDasharray="4 4" />
            {batters.map((b, i) => {
              const color = b.pctErr <= 5 ? '#00c853' : b.pctErr <= 12 ? '#f59e0b' : '#ef4444';
              return (
                <circle key={i} cx={toX(b.pred)} cy={toY(b.actual)}
                  r={Math.min(3 + b.games * 0.04, 7)} fill={color} fillOpacity={0.7} stroke={color} strokeWidth={1}>
                  <title>#{b.batter_id}: pred {b.pred.toFixed(0)}H / actual {b.actual.toFixed(0)}H over {b.games} games ({b.pctErr.toFixed(1)}% off)</title>
                </circle>
              );
            })}
          </svg>
          <div style={{ display: 'flex', gap: '1rem', marginTop: '0.25rem', fontSize: '0.68rem', color: 'var(--text-muted)' }}>
            <span><span style={{ color: '#00c853' }}>●</span> within 5%</span>
            <span><span style={{ color: '#f59e0b' }}>●</span> within 12%</span>
            <span><span style={{ color: '#ef4444' }}>●</span> off by 12%+</span>
            <span style={{ marginLeft: 'auto' }}>dot size = games logged · dashed = perfect</span>
          </div>
        </motion.div>
      )}

      {batters.length > 0 && (
        <div style={{ borderRadius: 10, border: '1px solid var(--border)', overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
            <thead>
              <tr style={{ background: 'var(--bg-secondary)' }}>
                {['Batter', 'Games', 'Predicted H', 'Actual H', 'Diff', '% Off'].map(h => (
                  <th key={h} style={{ padding: '0.5rem 0.75rem', fontSize: '0.7rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', borderBottom: '1px solid var(--border)', textAlign: 'left', whiteSpace: 'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...batters].sort((a, b) => a.pctErr - b.pctErr).map((b, i) => {
                const diff = b.pred - b.actual;
                const pctColor = b.pctErr <= 5 ? '#00c853' : b.pctErr <= 12 ? '#f59e0b' : '#ef4444';
                return (
                  <tr key={b.batter_id} style={{ borderTop: '1px solid var(--border)', background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)' }}>
                    <td style={{ padding: '0.5rem 0.75rem', fontWeight: 600, color: 'var(--text-primary)' }}>#{b.batter_id}</td>
                    <td style={{ padding: '0.5rem 0.75rem', color: 'var(--text-muted)' }}>{b.games}</td>
                    <td style={{ padding: '0.5rem 0.75rem', color: 'var(--text-secondary)' }}>{b.pred.toFixed(1)}</td>
                    <td style={{ padding: '0.5rem 0.75rem', fontWeight: 700, color: 'var(--text-primary)' }}>{b.actual.toFixed(1)}</td>
                    <td style={{ padding: '0.5rem 0.75rem', fontWeight: 600,
                      color: diff > 0 ? 'var(--accent-red)' : diff < 0 ? 'var(--accent-green)' : 'var(--text-muted)' }}>
                      {diff > 0 ? '+' : ''}{diff.toFixed(1)}H
                    </td>
                    <td style={{ padding: '0.5rem 0.75rem', fontWeight: 700, color: pctColor }}>
                      {b.pctErr.toFixed(1)}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {!data.test_rows && (
        <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
          No backtest data yet. Run: <code>cd backend && python -m train.backtest_hitting</code>
        </div>
      )}
    </div>
  );
}

export default function HittingPerformancePanel() {
  const [data, setData]       = useState(null);
  const [accData, setAccData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);
  const [view, setView]       = useState('overview');

  useEffect(() => {
    api.hittingPerformance()
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (view === 'accuracy') {
      api.hittingAccuracy().then(setAccData).catch(() => {});
    }
  }, [view]);

  if (loading) return (
    <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>Loading hitting performance...</div>
  );
  if (error) return (
    <div style={{ padding: '1rem 1.25rem', borderRadius: 10, background: ACCENT_BG, border: `1px solid ${ACCENT_BORDER}`, fontSize: '0.85rem', color: ACCENT }}>
      <strong>Performance data unavailable.</strong>
      <div style={{ marginTop: 6, color: 'var(--text-muted)', fontSize: '0.8rem' }}>{error}</div>
    </div>
  );

  const overall        = data?.overall        ?? {};
  const byTier         = data?.byTier         ?? {};
  const monthly        = data?.monthly        ?? [];
  const cumulative_pnl = data?.cumulative_pnl ?? [];
  const bankroll       = data?.bankroll       ?? 1000;
  const kelly_frac     = data?.kelly_frac     ?? 0.25;
  const accuracy       = data?.model_accuracy ?? {};

  const maxRoi   = monthly.length ? Math.max(...monthly.map(m => Math.abs(Number(m.roi) || 0)), 1) : 1;
  const roiStr   = typeof overall.roi === 'string' ? overall.roi : `${(overall.roi ?? 0) >= 0 ? '+' : ''}${(overall.roi ?? 0).toFixed(1)}%`;
  const roiColor = roiStr.startsWith('+') ? 'var(--accent-green)' : 'var(--accent-red)';
  const pnlColor = (overall.pnl ?? 0) >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';

  return (
    <div>
      {/* Tab switcher */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem' }}>
        {[['overview','Overview'],['accuracy','Accuracy']].map(([v, label]) => (
          <button key={v} onClick={() => setView(v)} style={{
            padding: '6px 16px', borderRadius: 8, fontSize: '0.82rem', fontWeight: 600,
            cursor: 'pointer', border: '1px solid',
            background: view === v ? ACCENT_BG : 'transparent',
            borderColor: view === v ? ACCENT_BORDER : 'var(--border)',
            color: view === v ? ACCENT : 'var(--text-muted)',
          }}>{label}</button>
        ))}
      </div>

      {view === 'accuracy' && <AccuracyView data={accData} />}

      {view === 'overview' && (
        <>
          {overall.bets === 0 ? (
            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
              style={{ textAlign: 'center', padding: '2.5rem 1rem', color: 'var(--text-muted)' }}>
              <div style={{ fontSize: '2rem', marginBottom: '0.75rem', opacity: 0.3 }}>📊</div>
              <p style={{ fontSize: '0.88rem' }}>No settled hit prop bets yet.</p>
              <p style={{ fontSize: '0.78rem', marginTop: '0.4rem', opacity: 0.75 }}>Results will appear here as picks resolve. Check the Accuracy tab for model backtest metrics.</p>
            </motion.div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '0.85rem', marginBottom: '2rem' }}>
              <StatBox label="Win Rate"   value={overall.winRate ?? '—'}   color="var(--accent-green)" delay={0} />
              <StatBox label="ROI"        value={roiStr}                    color={roiColor}            delay={0.05} />
              <StatBox label="P&L"        value={`${(overall.pnl ?? 0) >= 0 ? '+$' : '-$'}${Math.abs(overall.pnl ?? 0).toFixed(0)}`} color={pnlColor} delay={0.1} />
              <StatBox label="Total Bets" value={overall.bets ?? 0} sub={`${overall.wins ?? 0}W · ${overall.losses ?? 0}L`} delay={0.15} />
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.25rem', marginBottom: '1.25rem' }}>
            {Object.keys(byTier).length > 0 && (
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
                          <span style={{ fontSize: '0.72rem', fontWeight: 700, padding: '2px 8px', borderRadius: 999,
                            background: c.bg, border: `1px solid ${c.border}`, color: c.text }}>{tier}</span>
                          <div style={{ display: 'flex', gap: '0.75rem', fontSize: '0.78rem' }}>
                            <span style={{ color: c.text, fontWeight: 700 }}>{stats.winRate}</span>
                          </div>
                        </div>
                        <div style={{ height: 4, borderRadius: 2, background: 'var(--border)', overflow: 'hidden' }}>
                          <motion.div initial={{ width: 0 }} animate={{ width: `${winPct * 100}%` }}
                            transition={{ delay: 0.3, duration: 0.6, ease: 'easeOut' }}
                            style={{ height: '100%', background: c.text, borderRadius: 2 }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </motion.div>
            )}

            {monthly.length > 0 && (
              <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25, duration: 0.4 }}
                style={{ padding: '1.25rem', borderRadius: 12, border: '1px solid var(--border)', background: 'var(--bg-card)' }}>
                <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '1rem' }}>Monthly ROI</p>
                <div style={{ display: 'flex', gap: '0.25rem', alignItems: 'flex-end', justifyContent: 'space-between', overflowX: 'auto' }}>
                  {monthly.slice(-12).map((m, i) => <MonthBar key={m.month} {...m} maxRoi={maxRoi} index={i} />)}
                </div>
              </motion.div>
            )}
          </div>

          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35, duration: 0.4 }}
            style={{ padding: '1.25rem', borderRadius: 12, border: '1px solid var(--border)', background: 'var(--bg-card)', marginBottom: '1.25rem' }}>
            <PnlCurve data={cumulative_pnl} />
          </motion.div>

          {data?.recent_bets?.length > 0 && (
            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4, duration: 0.4 }}
              style={{ marginBottom: '1.25rem' }}>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.6rem' }}>
                This Month's Bets
              </p>
              <div style={{ borderRadius: 10, border: '1px solid var(--border)', overflow: 'hidden' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
                  <thead>
                    <tr style={{ background: 'var(--bg-secondary)' }}>
                      {['Date', 'Batter', 'Pick', 'Line', 'Actual H', 'Result', 'P&L'].map(h => (
                        <th key={h} style={{ padding: '0.45rem 0.75rem', fontSize: '0.68rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', borderBottom: '1px solid var(--border)', textAlign: 'left', whiteSpace: 'nowrap' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.recent_bets.map((r, i) => {
                      const win  = r.outcome === 'WIN';
                      const loss = r.outcome === 'LOSS';
                      return (
                        <tr key={i} style={{ borderTop: i > 0 ? '1px solid var(--border)' : 'none', background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)' }}>
                          <td style={{ padding: '0.45rem 0.75rem', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{r.date}</td>
                          <td style={{ padding: '0.45rem 0.75rem', fontWeight: 600, color: 'var(--text-primary)' }}>{r.batter_name}</td>
                          <td style={{ padding: '0.45rem 0.75rem', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{r.recommendation} {r.line}</td>
                          <td style={{ padding: '0.45rem 0.75rem', color: 'var(--text-muted)' }}>{r.line ?? '—'}</td>
                          <td style={{ padding: '0.45rem 0.75rem', fontWeight: 600, color: 'var(--text-primary)' }}>{r.actual_hits ?? '—'}</td>
                          <td style={{ padding: '0.45rem 0.75rem' }}>
                            <span style={{
                              fontSize: '0.7rem', fontWeight: 700, padding: '2px 7px', borderRadius: 999,
                              background: win ? 'rgba(0,200,83,0.12)' : loss ? 'rgba(239,68,68,0.1)' : 'rgba(139,148,158,0.12)',
                              color: win ? 'var(--accent-green)' : loss ? '#ef4444' : 'var(--text-muted)',
                              border: `1px solid ${win ? 'rgba(0,200,83,0.25)' : loss ? 'rgba(239,68,68,0.25)' : 'rgba(139,148,158,0.2)'}`,
                            }}>
                              {r.outcome || 'PENDING'}
                            </span>
                          </td>
                          <td style={{ padding: '0.45rem 0.75rem', fontWeight: 700, color: r.pnl >= 0 ? 'var(--accent-green)' : '#ef4444', whiteSpace: 'nowrap' }}>
                            {r.pnl >= 0 ? '+' : ''}${Math.abs(r.pnl).toFixed(0)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </motion.div>
          )}

          <div style={{ padding: '0.75rem 1rem', borderRadius: 8, background: ACCENT_BG, border: `1px solid ${ACCENT_BORDER}`, fontSize: '0.78rem', color: 'var(--text-muted)', lineHeight: 1.6 }}>
            Hit props model · 2025 season · ${bankroll} bankroll · {kelly_frac * 100}% Kelly · HIGH confidence only · live bets appended as they settle.
          </div>
        </>
      )}
    </div>
  );
}
