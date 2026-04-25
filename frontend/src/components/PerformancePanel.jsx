import { useEffect, useState, useMemo } from 'react';
import { motion } from 'framer-motion';
import { api } from '../api/client';

const TIER_COLORS = {
  HIGH:   { text: '#00c853', bg: 'rgba(0,200,83,0.10)',   border: 'rgba(0,200,83,0.25)' },
  MEDIUM: { text: '#f59e0b', bg: 'rgba(245,158,11,0.10)', border: 'rgba(245,158,11,0.25)' },
  LOW:    { text: '#8b949e', bg: 'rgba(139,148,158,0.10)',border: 'rgba(139,148,158,0.25)' },
};
const OUT_COLORS = {
  WIN:  { text: '#00c853', bg: 'rgba(0,200,83,0.12)'   },
  LOSS: { text: '#ef4444', bg: 'rgba(239,68,68,0.12)'  },
  PUSH: { text: '#8b949e', bg: 'rgba(139,148,158,0.12)'},
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

function PnlCurve({ data, monthly }) {
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

const SORT_OPTS = [
  { key: 'date',          label: 'Date' },
  { key: 'pitcher_name',  label: 'Pitcher' },
  { key: 'edge',          label: 'Edge' },
  { key: 'bet',           label: 'Bet $' },
  { key: 'pnl',           label: 'P&L' },
  { key: 'predicted',     label: 'Pred K' },
  { key: 'actual',        label: 'Actual K' },
];

function BetLog({ records }) {
  const [sort, setSort]       = useState({ key: 'date', dir: -1 });
  const [filter, setFilter]   = useState('ALL');
  const [tierFilter, setTier] = useState('ALL');
  const [page, setPage]       = useState(0);
  const PAGE = 50;

  const filtered = useMemo(() => {
    let r = records;
    if (filter !== 'ALL')     r = r.filter(x => x.outcome === filter);
    if (tierFilter !== 'ALL') r = r.filter(x => x.confidence === tierFilter);
    return [...r].sort((a, b) => {
      const av = a[sort.key], bv = b[sort.key];
      if (typeof av === 'string') return sort.dir * av.localeCompare(bv);
      return sort.dir * (av - bv);
    });
  }, [records, filter, tierFilter, sort]);

  const page_records = filtered.slice(page * PAGE, (page + 1) * PAGE);
  const pages = Math.ceil(filtered.length / PAGE);

  const toggleSort = key => setSort(s => ({ key, dir: s.key === key ? -s.dir : -1 }));

  const thStyle = key => ({
    padding: '0.5rem 0.75rem', fontSize: '0.7rem', fontWeight: 700,
    color: sort.key === key ? 'var(--accent-blue)' : 'var(--text-muted)',
    textTransform: 'uppercase', letterSpacing: '0.06em',
    cursor: 'pointer', whiteSpace: 'nowrap', userSelect: 'none',
    borderBottom: '1px solid var(--border)',
    background: 'var(--bg-card)',
  });

  return (
    <div>
      {/* Filters */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.85rem', flexWrap: 'wrap', alignItems: 'center' }}>
        {['ALL','WIN','LOSS','PUSH'].map(f => (
          <button key={f} onClick={() => { setFilter(f); setPage(0); }} style={{
            padding: '3px 12px', borderRadius: 999, fontSize: '0.72rem', fontWeight: 700,
            cursor: 'pointer', border: '1px solid',
            background: filter === f ? (f === 'WIN' ? 'rgba(0,200,83,0.15)' : f === 'LOSS' ? 'rgba(239,68,68,0.15)' : 'var(--bg-secondary)') : 'transparent',
            borderColor: filter === f ? (f === 'WIN' ? '#00c853' : f === 'LOSS' ? '#ef4444' : 'var(--border)') : 'var(--border)',
            color: filter === f ? (f === 'WIN' ? '#00c853' : f === 'LOSS' ? '#ef4444' : 'var(--text-secondary)') : 'var(--text-muted)',
          }}>{f}</button>
        ))}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: '0.4rem' }}>
          {['ALL','HIGH','MEDIUM','LOW'].map(t => {
            const c = TIER_COLORS[t] ?? { text: 'var(--text-muted)', bg: 'transparent', border: 'var(--border)' };
            return (
              <button key={t} onClick={() => { setTier(t); setPage(0); }} style={{
                padding: '3px 10px', borderRadius: 999, fontSize: '0.68rem', fontWeight: 700,
                cursor: 'pointer', border: `1px solid ${tierFilter === t ? c.border : 'var(--border)'}`,
                background: tierFilter === t ? c.bg : 'transparent',
                color: tierFilter === t ? c.text : 'var(--text-muted)',
              }}>{t}</button>
            );
          })}
        </div>
      </div>

      <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
        {filtered.length} bets
      </div>

      {/* Table */}
      <div style={{ overflowX: 'auto', borderRadius: 10, border: '1px solid var(--border)' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
          <thead>
            <tr>
              {SORT_OPTS.map(o => (
                <th key={o.key} onClick={() => toggleSort(o.key)} style={thStyle(o.key)}>
                  {o.label} {sort.key === o.key ? (sort.dir === -1 ? '↓' : '↑') : ''}
                </th>
              ))}
              <th style={{ ...thStyle('rec'), cursor: 'default' }}>Rec</th>
              <th style={{ ...thStyle('confidence'), cursor: 'default' }}>Conf</th>
              <th style={{ ...thStyle('outcome'), cursor: 'default' }}>Result</th>
            </tr>
          </thead>
          <tbody>
            {page_records.map((r, i) => {
              const oc = OUT_COLORS[r.outcome] ?? OUT_COLORS.PUSH;
              const tc = TIER_COLORS[r.confidence] ?? TIER_COLORS.LOW;
              return (
                <tr key={i} style={{ borderTop: '1px solid var(--border)', background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)' }}>
                  <td style={{ padding: '0.5rem 0.75rem', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{r.date}</td>
                  <td style={{ padding: '0.5rem 0.75rem', color: 'var(--text-primary)', fontWeight: 600, whiteSpace: 'nowrap' }}>{r.pitcher_name}</td>
                  <td style={{ padding: '0.5rem 0.75rem', color: Math.abs(r.edge) >= 0.12 ? 'var(--accent-green)' : 'var(--text-secondary)', fontWeight: 600 }}>
                    {(r.edge * 100).toFixed(1)}%
                  </td>
                  <td style={{ padding: '0.5rem 0.75rem', color: 'var(--text-secondary)' }}>${r.bet.toFixed(0)}</td>
                  <td style={{ padding: '0.5rem 0.75rem', fontWeight: 700, color: r.pnl > 0 ? 'var(--accent-green)' : r.pnl < 0 ? 'var(--accent-red)' : 'var(--text-muted)' }}>
                    {r.pnl >= 0 ? '+' : ''}${r.pnl.toFixed(0)}
                  </td>
                  <td style={{ padding: '0.5rem 0.75rem', color: 'var(--text-secondary)' }}>{r.predicted}</td>
                  <td style={{ padding: '0.5rem 0.75rem', color: 'var(--text-primary)', fontWeight: 600 }}>{r.actual}</td>
                  <td style={{ padding: '0.5rem 0.75rem' }}>
                    <span style={{ fontSize: '0.7rem', fontWeight: 700, padding: '2px 7px', borderRadius: 4,
                      color: r.rec === 'OVER' ? 'var(--accent-green)' : 'var(--accent-red)',
                      background: r.rec === 'OVER' ? 'rgba(0,200,83,0.10)' : 'rgba(239,68,68,0.10)' }}>
                      {r.rec}
                    </span>
                  </td>
                  <td style={{ padding: '0.5rem 0.75rem' }}>
                    <span style={{ fontSize: '0.68rem', fontWeight: 700, padding: '2px 6px', borderRadius: 999,
                      background: tc.bg, border: `1px solid ${tc.border}`, color: tc.text }}>
                      {r.confidence}
                    </span>
                  </td>
                  <td style={{ padding: '0.5rem 0.75rem' }}>
                    <span style={{ fontSize: '0.72rem', fontWeight: 700, padding: '2px 8px', borderRadius: 4,
                      background: oc.bg, color: oc.text }}>
                      {r.outcome}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {pages > 1 && (
        <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.75rem', justifyContent: 'center', alignItems: 'center' }}>
          <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
            style={{ padding: '4px 12px', borderRadius: 6, border: '1px solid var(--border)', background: 'transparent', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '0.78rem' }}>
            Prev
          </button>
          <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{page + 1} / {pages}</span>
          <button onClick={() => setPage(p => Math.min(pages - 1, p + 1))} disabled={page === pages - 1}
            style={{ padding: '4px 12px', borderRadius: 6, border: '1px solid var(--border)', background: 'transparent', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '0.78rem' }}>
            Next
          </button>
        </div>
      )}
    </div>
  );
}

const EMPTY_ROW = () => ({ pitcher_name: '', line: '', over_odds: '', under_odds: '' });

function LiveRecord() {
  const [record, setRecord]   = useState(null);
  const [rows, setRows]       = useState([EMPTY_ROW()]);
  const [submitting, setSub]  = useState(false);
  const [submitMsg, setMsg]   = useState('');
  const [submitResult, setSubmitResult] = useState(null);

  useEffect(() => {
    api.liveRecord().then(setRecord).catch(() => {});
  }, []);

  function updateRow(i, field, val) {
    setRows(prev => prev.map((r, idx) => idx === i ? { ...r, [field]: val } : r));
  }

  function addRow() { setRows(prev => [...prev, EMPTY_ROW()]); }
  function removeRow(i) { setRows(prev => prev.length === 1 ? [EMPTY_ROW()] : prev.filter((_, idx) => idx !== i)); }

  async function handleSubmit() {
    const lines = rows
      .filter(r => r.pitcher_name.trim() && r.line && r.over_odds && r.under_odds)
      .map(r => ({
        pitcher_name: r.pitcher_name.trim(),
        line:         parseFloat(r.line),
        over_odds:    parseInt(r.over_odds),
        under_odds:   parseInt(r.under_odds),
      }));
    if (!lines.length) { setMsg('Fill in at least one complete row.'); return; }
    setSub(true); setMsg(''); setSubmitResult(null);
    try {
      const res = await api.logLines({ lines });
      setSubmitResult({ logged: res.predictions || [], skipped: res.skipped || [] });
      setMsg(`Logged ${res.logged} · Skipped ${(res.skipped || []).length}`);
      setRows([EMPTY_ROW()]);
      api.liveRecord().then(setRecord).catch(() => {});
    } catch (e) {
      setMsg(`Error: ${e.message}`);
    } finally {
      setSub(false);
    }
  }

  const OUT_COLORS = { WIN: '#00c853', LOSS: '#ef4444', PUSH: '#8b949e' };

  async function handleDelete(date, pitcher_name) {
    try {
      await api.deleteLine({ date, pitcher_name });
      api.liveRecord().then(setRecord).catch(() => {});
    } catch (e) {
      console.error('Delete failed:', e);
    }
  }

  const inputStyle = {
    padding: '0.4rem 0.5rem', borderRadius: 6, border: '1px solid var(--border)',
    background: 'var(--bg-secondary)', color: 'var(--text-primary)',
    fontSize: '0.82rem', outline: 'none', width: '100%', boxSizing: 'border-box',
  };

  return (
    <div>
      {/* Submit lines */}
      <div style={{ padding: '1.25rem', borderRadius: 12, border: '1px solid var(--border)', background: 'var(--bg-card)', marginBottom: '1.25rem' }}>
        <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '1rem' }}>
          Submit Today's Lines
        </p>

        {/* Column headers */}
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 0.8fr 0.8fr 0.8fr 28px', gap: '0.5rem', marginBottom: '0.4rem' }}>
          {['Pitcher', 'Line', 'Over Odds', 'Under Odds', ''].map(h => (
            <span key={h} style={{ fontSize: '0.68rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{h}</span>
          ))}
        </div>

        {/* Rows */}
        {rows.map((row, i) => (
          <div key={i} style={{ display: 'grid', gridTemplateColumns: '2fr 0.8fr 0.8fr 0.8fr 28px', gap: '0.5rem', marginBottom: '0.4rem', alignItems: 'center' }}>
            <input style={inputStyle} placeholder="Max Fried" value={row.pitcher_name} onChange={e => updateRow(i, 'pitcher_name', e.target.value)} />
            <input style={inputStyle} placeholder="5.5" type="number" step="0.5" value={row.line} onChange={e => updateRow(i, 'line', e.target.value)} />
            <input style={inputStyle} placeholder="+106" value={row.over_odds} onChange={e => updateRow(i, 'over_odds', e.target.value)} />
            <input style={inputStyle} placeholder="-140" value={row.under_odds} onChange={e => updateRow(i, 'under_odds', e.target.value)} />
            <button onClick={() => removeRow(i)} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '1rem', padding: 0, lineHeight: 1 }}
              onMouseEnter={e => e.currentTarget.style.color = '#ef4444'}
              onMouseLeave={e => e.currentTarget.style.color = 'var(--text-muted)'}>✕</button>
          </div>
        ))}

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginTop: '0.75rem' }}>
          <button onClick={addRow} style={{ padding: '5px 14px', borderRadius: 7, border: '1px solid var(--border)', background: 'transparent', color: 'var(--text-muted)', fontSize: '0.78rem', cursor: 'pointer' }}>
            + Add Row
          </button>
          <button onClick={handleSubmit} disabled={submitting} style={{
            padding: '7px 18px', borderRadius: 8, border: 'none', fontWeight: 700,
            fontSize: '0.82rem', cursor: 'pointer',
            background: 'var(--accent-blue)', color: '#fff', opacity: submitting ? 0.6 : 1,
          }}>
            {submitting ? 'Logging...' : 'Log Predictions'}
          </button>
          {submitMsg && <span style={{ fontSize: '0.78rem', color: submitMsg.startsWith('Error') ? 'var(--accent-red)' : 'var(--accent-green)' }}>{submitMsg}</span>}
        </div>

        {submitResult && (
          <div style={{ marginTop: '0.85rem', display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
            {submitResult.logged.map(p => (
              <div key={p.pitcher_name} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.4rem 0.6rem', borderRadius: 6, background: 'rgba(0,200,83,0.08)', border: '1px solid rgba(0,200,83,0.2)', fontSize: '0.78rem' }}>
                <span style={{ fontWeight: 600 }}>{p.pitcher_name}</span>
                <span style={{ display: 'flex', gap: '0.75rem', color: 'var(--text-muted)' }}>
                  <span>Pred: <b style={{ color: 'var(--text-primary)' }}>{p.predicted_ks}</b>K</span>
                  <span>Line: <b style={{ color: 'var(--text-primary)' }}>{p.line}</b></span>
                  <span style={{ color: p.recommendation === 'OVER' ? 'var(--accent-green)' : 'var(--accent-red)', fontWeight: 700 }}>{p.recommendation}</span>
                  <span style={{ color: 'var(--accent-green)', fontWeight: 600 }}>{p.confidence}</span>
                </span>
              </div>
            ))}
            {submitResult.skipped.map(p => (
              <div key={p.pitcher_name} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.4rem 0.6rem', borderRadius: 6, background: 'rgba(239,68,68,0.07)', border: '1px solid rgba(239,68,68,0.2)', fontSize: '0.78rem', opacity: 0.75 }}>
                <span style={{ fontWeight: 600 }}>{p.pitcher_name}</span>
                <span style={{ display: 'flex', gap: '0.75rem', color: 'var(--text-muted)' }}>
                  <span>Pred: <b style={{ color: 'var(--text-primary)' }}>{p.predicted_ks}</b>K</span>
                  <span>Line: <b style={{ color: 'var(--text-primary)' }}>{p.line}</b></span>
                  <span style={{ color: '#8b949e', fontWeight: 600 }}>NO BET</span>
                  <span style={{ color: 'var(--text-muted)', fontSize: '0.72rem' }}>edge {(p.edge * 100).toFixed(1)}%</span>
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Live record stats */}
      {record && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '0.85rem', marginBottom: '1.25rem' }}>
            <StatBox label="Win Rate"   value={`${record.win_rate}%`}  color="var(--accent-green)" delay={0} />
            <StatBox label="ROI"        value={`${record.roi >= 0 ? '+' : ''}${record.roi}%`} color={record.roi >= 0 ? 'var(--accent-green)' : 'var(--accent-red)'} delay={0.05} />
            <StatBox label="P&L"        value={`${record.pnl >= 0 ? '+$' : '-$'}${Math.abs(record.pnl).toFixed(0)}`} color={record.pnl >= 0 ? 'var(--accent-green)' : 'var(--accent-red)'} delay={0.1} />
            <StatBox label="Record"     value={`${record.wins}W-${record.losses}L`} sub={`${record.pushes} push · ${record.pending} pending`} delay={0.15} />
          </div>

          {/* Recent bets */}
          {record.records.length > 0 && (
            <div style={{ borderRadius: 10, border: '1px solid var(--border)', overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
                <thead>
                  <tr>
                    {['Date','Pitcher','Conf','Rec','Line','Odds','Pred K','Actual','Result',''].map(h => (
                      <th key={h} style={{ padding: '0.5rem 0.75rem', fontSize: '0.7rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', borderBottom: '1px solid var(--border)', background: 'var(--bg-card)', textAlign: 'left' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {[...record.records].reverse().map((r, i) => (
                    <tr key={i} style={{ borderTop: '1px solid var(--border)', background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)' }}>
                      <td style={{ padding: '0.5rem 0.75rem', color: 'var(--text-muted)' }}>{r.date}</td>
                      <td style={{ padding: '0.5rem 0.75rem', color: 'var(--text-primary)', fontWeight: 600 }}>{r.pitcher_name}</td>
                      <td style={{ padding: '0.5rem 0.75rem' }}>
                        {r.confidence && (
                          <span style={{ fontSize: '0.68rem', fontWeight: 700, padding: '2px 7px', borderRadius: 999,
                            color: TIER_COLORS[r.confidence]?.text ?? '#8b949e',
                            background: (TIER_COLORS[r.confidence]?.text ?? '#8b949e') + '18',
                            border: `1px solid ${(TIER_COLORS[r.confidence]?.text ?? '#8b949e')}30`,
                          }}>{r.confidence}</span>
                        )}
                      </td>
                      <td style={{ padding: '0.5rem 0.75rem' }}>
                        <span style={{ fontSize: '0.7rem', fontWeight: 700, padding: '2px 6px', borderRadius: 4, color: r.recommendation === 'OVER' ? 'var(--accent-green)' : 'var(--accent-red)', background: r.recommendation === 'OVER' ? 'rgba(0,200,83,0.10)' : 'rgba(239,68,68,0.10)' }}>{r.recommendation}</span>
                      </td>
                      <td style={{ padding: '0.5rem 0.75rem', color: 'var(--text-secondary)' }}>{r.line}</td>
                      <td style={{ padding: '0.5rem 0.75rem', fontWeight: 600, color: (r.bet_odds ?? r.over_odds) > 0 ? 'var(--accent-green)' : 'var(--text-muted)' }}>
                        {(() => { const o = r.bet_odds ?? r.over_odds; return o != null ? (o > 0 ? `+${o}` : o) : '—'; })()}
                      </td>
                      <td style={{ padding: '0.5rem 0.75rem', color: 'var(--text-secondary)' }}>{r.predicted_ks}</td>
                      <td style={{ padding: '0.5rem 0.75rem', color: 'var(--text-primary)', fontWeight: 600 }}>{r.actual_ks ?? '—'}</td>
                      <td style={{ padding: '0.5rem 0.75rem' }}>
                        {r.outcome
                          ? <span style={{ fontSize: '0.72rem', fontWeight: 700, padding: '2px 7px', borderRadius: 4, color: OUT_COLORS[r.outcome], background: `${OUT_COLORS[r.outcome]}18` }}>{r.outcome}</span>
                          : <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>pending</span>}
                      </td>
                      <td style={{ padding: '0.5rem 0.75rem' }}>
                        {!r.outcome && (
                          <button
                            onClick={() => handleDelete(r.date, r.pitcher_name)}
                            title="Remove prediction"
                            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', fontSize: '0.85rem', padding: '2px 4px', borderRadius: 4, lineHeight: 1 }}
                            onMouseEnter={e => e.currentTarget.style.color = '#ef4444'}
                            onMouseLeave={e => e.currentTarget.style.color = 'var(--text-muted)'}
                          >✕</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function Accuracy() {
  const [acc, setAcc] = useState(null);

  useEffect(() => { api.kAccuracy().then(setAcc).catch(() => {}); }, []);

  if (!acc) return <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>Loading...</div>;

  const resolved = acc.records.filter(r => r.actual_ks !== null);
  const pending  = acc.records.filter(r => r.actual_ks === null);

  // Simple scatter: predicted vs actual
  const W = 400, H = 200;
  const allVals = resolved.flatMap(r => [r.predicted_ks, r.actual_ks]);
  const minV = Math.max(0, Math.min(...allVals) - 1);
  const maxV = Math.max(...allVals) + 1;
  const toX = v => ((v - minV) / (maxV - minV)) * W;
  const toY = v => H - ((v - minV) / (maxV - minV)) * H;

  return (
    <div>
      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '0.85rem', marginBottom: '1.5rem' }}>
        <StatBox label="MAE" value={acc.mae != null ? `${acc.mae} K` : '—'} color="var(--accent-blue)" delay={0}
          sub={acc.resolved ? `${acc.resolved} starts` : 'no data yet'} />
        <StatBox label="RMSE" value={acc.rmse != null ? `${acc.rmse} K` : '—'} delay={0.05} />
        <StatBox label="Within 1K" value={acc.within_1 != null ? `${acc.within_1}%` : '—'} color="var(--accent-green)" delay={0.1} />
        <StatBox label="Within 2K" value={acc.within_2 != null ? `${acc.within_2}%` : '—'} color="var(--accent-green)" delay={0.15} />
      </div>

      {resolved.length > 1 && (
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
          style={{ padding: '1.25rem', borderRadius: 12, border: '1px solid var(--border)', background: 'var(--bg-card)', marginBottom: '1.25rem' }}>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.75rem' }}>
            Predicted vs Actual Ks
          </p>
          <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 200, overflow: 'visible' }}>
            {/* Perfect prediction line */}
            <line x1={toX(minV)} y1={toY(minV)} x2={toX(maxV)} y2={toY(maxV)}
              stroke="var(--border)" strokeWidth="1" strokeDasharray="4 4" />
            {resolved.map((r, i) => {
              const err = Math.abs(r.predicted_ks - r.actual_ks);
              const color = err <= 1 ? '#00c853' : err <= 2 ? '#f59e0b' : '#ef4444';
              return (
                <circle key={i} cx={toX(r.predicted_ks)} cy={toY(r.actual_ks)}
                  r={4} fill={color} fillOpacity={0.7} stroke={color} strokeWidth={1}>
                  <title>{r.pitcher_name}: pred {r.predicted_ks} / actual {r.actual_ks}</title>
                </circle>
              );
            })}
          </svg>
          <div style={{ display: 'flex', gap: '1rem', marginTop: '0.5rem', fontSize: '0.68rem', color: 'var(--text-muted)' }}>
            <span><span style={{ color: '#00c853' }}>●</span> within 1K</span>
            <span><span style={{ color: '#f59e0b' }}>●</span> within 2K</span>
            <span><span style={{ color: '#ef4444' }}>●</span> off by 2K+</span>
            <span style={{ marginLeft: 'auto' }}>dashed = perfect prediction</span>
          </div>
        </motion.div>
      )}

      {/* Table */}
      {acc.records.length > 0 && (
        <div style={{ borderRadius: 10, border: '1px solid var(--border)', overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
            <thead>
              <tr>
                {['Date','Pitcher','Predicted','Actual','Error'].map(h => (
                  <th key={h} style={{ padding: '0.5rem 0.75rem', fontSize: '0.7rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', borderBottom: '1px solid var(--border)', background: 'var(--bg-card)', textAlign: 'left' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...acc.records].reverse().map((r, i) => {
                const err = r.actual_ks != null ? Math.abs(r.predicted_ks - r.actual_ks) : null;
                const errColor = err == null ? 'var(--text-muted)' : err <= 1 ? '#00c853' : err <= 2 ? '#f59e0b' : '#ef4444';
                return (
                  <tr key={i} style={{ borderTop: '1px solid var(--border)', background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)' }}>
                    <td style={{ padding: '0.5rem 0.75rem', color: 'var(--text-muted)' }}>{r.date}</td>
                    <td style={{ padding: '0.5rem 0.75rem', color: 'var(--text-primary)', fontWeight: 600 }}>{r.pitcher_name}</td>
                    <td style={{ padding: '0.5rem 0.75rem', color: 'var(--text-secondary)' }}>{r.predicted_ks}</td>
                    <td style={{ padding: '0.5rem 0.75rem', color: 'var(--text-primary)', fontWeight: 600 }}>{r.actual_ks ?? '—'}</td>
                    <td style={{ padding: '0.5rem 0.75rem', color: errColor, fontWeight: 600 }}>
                      {err != null ? `±${err.toFixed(1)}` : 'pending'}
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

  const { overall, byTier, monthly, cumulative_pnl, bankroll, kelly_frac, split, records = [] } = data;
  const maxRoi   = Math.max(...monthly.map(m => Math.abs(m.roi)), 1);
  const roiColor = overall.roi.startsWith('+') ? 'var(--accent-green)' : 'var(--accent-red)';
  const pnlColor = overall.pnl >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';

  return (
    <div>
      {/* Tab switcher */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem' }}>
        {[['overview','Overview'],['bets','Bet Log'],['live','Live Record'],['accuracy','Accuracy']].map(([v, label]) => (
          <button key={v} onClick={() => setView(v)} style={{
            padding: '6px 16px', borderRadius: 8, fontSize: '0.82rem', fontWeight: 600,
            cursor: 'pointer', border: '1px solid',
            background: view === v ? 'rgba(29,155,240,0.12)' : 'transparent',
            borderColor: view === v ? 'rgba(29,155,240,0.4)' : 'var(--border)',
            color: view === v ? 'var(--accent-blue)' : 'var(--text-muted)',
          }}>{label}</button>
        ))}
      </div>

      {view === 'live'     && <LiveRecord />}
      {view === 'accuracy' && <Accuracy />}

      {view === 'overview' && (
        <>
          {/* Stats */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '0.85rem', marginBottom: '2rem' }}>
            <StatBox label="Win Rate" value={overall.winRate} color="var(--accent-green)" delay={0} />
            <StatBox label="ROI"      value={overall.roi}     color={roiColor}            delay={0.05} />
            <StatBox label="P&L"      value={`${overall.pnl >= 0 ? '+$' : '-$'}${Math.abs(overall.pnl).toFixed(0)}`} color={pnlColor} delay={0.1} />
            <StatBox label="Total Bets" value={overall.bets} sub={`${overall.wins}W · ${overall.losses}L · ${overall.pushes}P`} delay={0.15} />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.25rem', marginBottom: '1.25rem' }}>
            {/* Tier breakdown */}
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

            {/* Monthly bars */}
            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25, duration: 0.4 }}
              style={{ padding: '1.25rem', borderRadius: 12, border: '1px solid var(--border)', background: 'var(--bg-card)' }}>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '1rem' }}>Monthly ROI</p>
              <div style={{ display: 'flex', gap: '0.25rem', alignItems: 'flex-end', justifyContent: 'space-between', overflowX: 'auto' }}>
                {monthly.slice(-12).map((m, i) => <MonthBar key={m.month} {...m} maxRoi={maxRoi} index={i} />)}
              </div>
            </motion.div>
          </div>

          {/* P&L curve */}
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35, duration: 0.4 }}
            style={{ padding: '1.25rem', borderRadius: 12, border: '1px solid var(--border)', background: 'var(--bg-card)', marginBottom: '1.25rem' }}>
            <PnlCurve data={cumulative_pnl} monthly={monthly} />
          </motion.div>

          <div style={{ padding: '0.75rem 1rem', borderRadius: 8, background: 'rgba(29,155,240,0.06)', border: '1px solid rgba(29,155,240,0.15)', fontSize: '0.78rem', color: 'var(--text-muted)', lineHeight: 1.6 }}>
            Walk-forward backtest · 2024 season · ${bankroll} bankroll · {kelly_frac * 100}% Kelly · real DraftKings/FanDuel lines (150 dates) · model never trained on 2024 data.
          </div>
        </>
      )}

      {view === 'bets' && <BetLog records={records} />}
    </div>
  );
}
