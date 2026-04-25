import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, Loader2, X } from 'lucide-react';
import { PITCHER_ROSTER } from '../data/mockData';
import { api } from '../api/client';

const TEAMS = ['NYY','ATL','SF','MIN','BAL','PHI','SD','LAD','MIL','MIA','PIT','HOU','DET','SEA'];
const PARKS = TEAMS;

function ResultCard({ result }) {
  const edgeColor = result.edge_pct >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
      style={{
        marginTop: '1rem', padding: '1.25rem',
        borderRadius: 12, border: `1px solid ${edgeColor}40`,
        background: 'var(--bg-secondary)',
        display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '1rem',
      }}
    >
      <Stat label="Predicted Ks"   value={result.predicted_ks.toFixed(1)} />
      <Stat label="Line"           value={result.line} />
      <Stat label="Model P(Over)"  value={`${(result.model_prob_over * 100).toFixed(1)}%`} color="var(--accent-blue)" />
      <Stat label="Implied P"      value={`${(result.implied_prob_over * 100).toFixed(1)}%`} color="var(--text-muted)" />
      <Stat label="Edge"           value={result.edge_pct_display} color={edgeColor} />
      <Stat label="Recommendation" value={result.recommendation}  color={edgeColor} />
    </motion.div>
  );
}

function Stat({ label, value, color = 'var(--text-primary)' }) {
  return (
    <div>
      <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 3 }}>{label}</div>
      <div style={{ fontSize: '1.15rem', fontWeight: 800, color, fontFamily: 'Space Grotesk, sans-serif' }}>{value}</div>
    </div>
  );
}

export default function PitcherSearch() {
  const [query, setQuery]       = useState('');
  const [results, setResults]   = useState([]);
  const [selected, setSelected] = useState(null);
  const [showDrop, setShowDrop] = useState(false);
  const [form, setForm]         = useState({ opponent_team: 'BOS', park_team: '', is_home: true, days_rest: 5, line: 7.5, over_odds: -115 });
  const [loading, setLoading]   = useState(false);
  const [prediction, setPrediction] = useState(null);
  const [err, setErr]           = useState(null);
  const ref                     = useRef(null);

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setShowDrop(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const onQuery = (v) => {
    setQuery(v);
    setPrediction(null);
    if (v.length < 2) { setResults([]); setShowDrop(false); return; }
    const hits = PITCHER_ROSTER.filter(p => p.name.toLowerCase().includes(v.toLowerCase())).slice(0, 6);
    setResults(hits);
    setShowDrop(hits.length > 0);
  };

  const pick = (pitcher) => {
    setSelected(pitcher);
    setQuery(pitcher.name);
    setShowDrop(false);
    setForm(f => ({ ...f, park_team: pitcher.team }));
    setPrediction(null);
  };

  const clear = () => { setQuery(''); setSelected(null); setPrediction(null); setResults([]); };

  const submit = async (e) => {
    e.preventDefault();
    if (!selected) return;
    setLoading(true); setErr(null); setPrediction(null);
    try {
      const res = await api.predict({
        pitcher_name:  selected.name,
        last_name:     selected.last,
        first_name:    selected.first,
        opponent_team: form.opponent_team,
        park_team:     form.park_team || selected.team,
        is_home:       form.is_home,
        days_rest:     parseInt(form.days_rest),
        line:          parseFloat(form.line),
        over_odds:     parseInt(form.over_odds),
      });
      setPrediction(res);
    } catch (e) { setErr(e.message); }
    finally { setLoading(false); }
  };

  const s = (k) => (e) => setForm(f => ({
    ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value,
  }));

  const fieldStyle = {
    padding: '0.45rem 0.65rem', borderRadius: 7, border: '1px solid var(--border)',
    background: 'var(--bg-primary)', color: 'var(--text-primary)',
    fontSize: '0.82rem', outline: 'none', width: '100%', boxSizing: 'border-box',
  };

  return (
    <div style={{
      padding: '1.5rem', borderRadius: 12,
      border: '1px solid var(--border-glow)', background: 'var(--bg-card)',
      marginBottom: '1.5rem',
    }}>
      <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.85rem' }}>
        Pitcher Lookup
      </p>

      <form onSubmit={submit}>
        {/* Search input */}
        <div ref={ref} style={{ position: 'relative', marginBottom: '0.85rem' }}>
          <div style={{ position: 'relative' }}>
            <Search size={15} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none' }} />
            <input
              value={query}
              onChange={e => onQuery(e.target.value)}
              placeholder="Search pitcher…"
              onFocus={() => results.length && setShowDrop(true)}
              style={{ ...fieldStyle, paddingLeft: 32, paddingRight: query ? 32 : 10 }}
            />
            {query && (
              <button type="button" onClick={clear} style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', display: 'flex', padding: 0 }}>
                <X size={14} />
              </button>
            )}
          </div>

          <AnimatePresence>
            {showDrop && (
              <motion.div
                initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 4 }}
                style={{
                  position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 50, marginTop: 4,
                  borderRadius: 10, border: '1px solid var(--border)', background: 'var(--bg-card)',
                  boxShadow: '0 8px 24px rgba(0,0,0,0.4)', overflow: 'hidden',
                }}
              >
                {results.map(p => (
                  <div
                    key={p.name}
                    onClick={() => pick(p)}
                    style={{
                      padding: '0.6rem 0.85rem', cursor: 'pointer',
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                      borderBottom: '1px solid var(--border)',
                    }}
                    onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-card-hover)'}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                  >
                    <div>
                      <div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-primary)' }}>{p.name}</div>
                      <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{p.team} · {p.hand}HP</div>
                    </div>
                    <div style={{ fontSize: '0.78rem', color: 'var(--accent-blue)', fontWeight: 700 }}>{p.k9} K/9</div>
                  </div>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Compact params row */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))', gap: '0.6rem', marginBottom: '0.85rem' }}>
          <div>
            <label style={{ fontSize: '0.65rem', color: 'var(--text-muted)', display: 'block', marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.07em' }}>Opponent</label>
            <select value={form.opponent_team} onChange={s('opponent_team')} style={fieldStyle}>
              {TEAMS.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: '0.65rem', color: 'var(--text-muted)', display: 'block', marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.07em' }}>Park</label>
            <select value={form.park_team} onChange={s('park_team')} style={fieldStyle}>
              {PARKS.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: '0.65rem', color: 'var(--text-muted)', display: 'block', marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.07em' }}>K/U Line</label>
            <input type="number" step="0.5" value={form.line} onChange={s('line')} style={fieldStyle} />
          </div>
          <div>
            <label style={{ fontSize: '0.65rem', color: 'var(--text-muted)', display: 'block', marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.07em' }}>Odds</label>
            <input type="number" value={form.over_odds} onChange={s('over_odds')} style={fieldStyle} />
          </div>
          <div>
            <label style={{ fontSize: '0.65rem', color: 'var(--text-muted)', display: 'block', marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.07em' }}>Rest</label>
            <input type="number" min="1" max="10" value={form.days_rest} onChange={s('days_rest')} style={fieldStyle} />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}>
            <label style={{ fontSize: '0.65rem', color: 'var(--text-muted)', display: 'block', marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.07em' }}>Home</label>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', height: 30 }}>
              <input type="checkbox" checked={form.is_home} onChange={s('is_home')} style={{ accentColor: 'var(--accent-blue)', width: 15, height: 15 }} />
              <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Yes</span>
            </div>
          </div>
        </div>

        {err && <div style={{ fontSize: '0.78rem', color: 'var(--accent-red)', marginBottom: '0.6rem' }}>{err}</div>}

        <motion.button
          type="submit"
          whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}
          disabled={!selected || loading}
          style={{
            display: 'flex', alignItems: 'center', gap: '0.4rem',
            padding: '0.55rem 1.2rem', borderRadius: 8, border: 'none',
            background: selected ? 'linear-gradient(135deg, #1d9bf0, #0066cc)' : 'var(--border)',
            color: selected ? '#fff' : 'var(--text-muted)',
            fontWeight: 700, fontSize: '0.82rem',
            cursor: selected && !loading ? 'pointer' : 'not-allowed',
          }}
        >
          {loading && <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} />}
          {loading ? 'Calculating…' : 'Get Edge'}
        </motion.button>
      </form>

      {prediction && <ResultCard result={prediction} />}
    </div>
  );
}
