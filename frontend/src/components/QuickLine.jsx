import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Zap, Loader2, AlertCircle } from 'lucide-react';
import { api } from '../api/client';
import { PITCHER_ROSTER } from '../data/mockData';

/*
 * Parses inputs like:
 *   "Cole Over 7.5 -115"
 *   "Gerrit Cole Over 7.5"
 *   "strider u 8.5 -110"
 *   "glasnow over 9 -120"
 */
function parseLine(raw) {
  const str = raw.trim();
  const overMatch = str.match(/\b(over|o)\b/i);
  const underMatch = str.match(/\b(under|u)\b/i);
  if (!overMatch && !underMatch) return null;

  const direction = overMatch ? 'over' : 'under';
  const pivot = overMatch ? overMatch.index : underMatch.index;

  const namePart = str.slice(0, pivot).trim();
  const rest = str.slice(pivot + (overMatch?.[0] ?? underMatch?.[0]).length).trim();

  const lineMatch = rest.match(/(\d+\.?\d*)/);
  const oddsMatch = rest.match(/([+-]\d{3,})/);
  if (!lineMatch) return null;

  return {
    nameQuery:   namePart,
    direction,
    line:        parseFloat(lineMatch[1]),
    over_odds:   oddsMatch ? parseInt(oddsMatch[1]) : -115,
  };
}

function findPitcher(query) {
  if (!query) return null;
  const q = query.toLowerCase();
  return PITCHER_ROSTER.find(p =>
    p.name.toLowerCase().includes(q) ||
    p.last.toLowerCase().includes(q)
  ) ?? null;
}

export default function QuickLine() {
  const [input, setInput]         = useState('');
  const [loading, setLoading]     = useState(false);
  const [result, setResult]       = useState(null);
  const [parseErr, setParseErr]   = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    setResult(null);
    setParseErr(null);

    const parsed = parseLine(input);
    if (!parsed) { setParseErr('Try: "Cole Over 7.5 -115"'); return; }

    const pitcher = findPitcher(parsed.nameQuery);
    if (!pitcher) { setParseErr(`Pitcher not found for "${parsed.nameQuery}"`); return; }

    setLoading(true);
    try {
      const res = await api.predict({
        pitcher_name:  pitcher.name,
        last_name:     pitcher.last,
        first_name:    pitcher.first,
        opponent_team: 'OPP',
        park_team:     pitcher.team,
        is_home:       true,
        days_rest:     5,
        line:          parsed.line,
        over_odds:     parsed.direction === 'over' ? parsed.over_odds : -parsed.over_odds,
      });
      setResult({ ...res, pitcher, parsed });
    } catch (e) {
      setParseErr(e.message);
    } finally {
      setLoading(false);
    }
  };

  const edgeColor = result
    ? result.edge_pct >= 0 ? 'var(--accent-green)' : 'var(--accent-red)'
    : 'var(--accent-blue)';

  return (
    <div style={{
      marginBottom: '1.75rem',
      padding: '1rem 1.25rem',
      borderRadius: 12,
      border: '1px solid var(--border)',
      background: 'var(--bg-card)',
    }}>
      <form onSubmit={submit} style={{ display: 'flex', gap: '0.6rem', alignItems: 'center', flexWrap: 'wrap' }}>
        <Zap size={16} color="var(--accent-amber)" style={{ flexShrink: 0 }} />
        <input
          value={input}
          onChange={e => { setInput(e.target.value); setResult(null); setParseErr(null); }}
          placeholder='Paste a line: "Cole Over 7.5 -115"'
          style={{
            flex: 1, minWidth: 220,
            padding: '0.5rem 0.75rem', borderRadius: 8,
            border: `1px solid ${parseErr ? 'rgba(239,68,68,0.5)' : 'var(--border)'}`,
            background: 'var(--bg-secondary)', color: 'var(--text-primary)',
            fontSize: '0.875rem', outline: 'none',
          }}
          onFocus={e => e.target.style.borderColor = 'var(--border-glow)'}
          onBlur={e  => e.target.style.borderColor = parseErr ? 'rgba(239,68,68,0.5)' : 'var(--border)'}
        />
        <motion.button
          type="submit"
          whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.97 }}
          disabled={loading || !input.trim()}
          style={{
            display: 'flex', alignItems: 'center', gap: '0.35rem',
            padding: '0.5rem 1rem', borderRadius: 8, border: 'none',
            background: 'linear-gradient(135deg, #1d9bf0, #0066cc)',
            color: '#fff', fontWeight: 700, fontSize: '0.82rem',
            cursor: loading || !input.trim() ? 'not-allowed' : 'pointer',
            opacity: !input.trim() ? 0.5 : 1,
            whiteSpace: 'nowrap',
          }}
        >
          {loading ? <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} /> : <Zap size={13} />}
          {loading ? 'Analyzing…' : 'Check Edge'}
        </motion.button>

        {/* Parse error */}
        {parseErr && (
          <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            style={{ fontSize: '0.78rem', color: 'var(--accent-red)', display: 'flex', alignItems: 'center', gap: 4 }}
          >
            <AlertCircle size={12} /> {parseErr}
          </motion.span>
        )}
      </form>

      {/* Inline result */}
      <AnimatePresence>
        {result && (
          <motion.div
            key="result"
            initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
            style={{ overflow: 'hidden' }}
          >
            <div style={{
              marginTop: '0.85rem', paddingTop: '0.85rem',
              borderTop: '1px solid var(--border)',
              display: 'flex', alignItems: 'center', gap: '1.5rem', flexWrap: 'wrap',
            }}>
              <div>
                <span style={{ fontSize: '0.9rem', fontWeight: 700, color: 'var(--text-primary)' }}>{result.pitcher.name}</span>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginLeft: 8 }}>
                  {result.parsed.direction === 'over' ? 'Over' : 'Under'} {result.parsed.line} K
                </span>
              </div>
              <div style={{ display: 'flex', gap: '1.25rem', flexWrap: 'wrap' }}>
                {[
                  { label: 'Projected', value: `${result.predicted_ks.toFixed(1)} K` },
                  { label: 'Model P',   value: `${(result.model_prob_over * 100).toFixed(1)}%`, color: 'var(--accent-blue)' },
                  { label: 'Implied P', value: `${(result.implied_prob_over * 100).toFixed(1)}%`, color: 'var(--text-muted)' },
                ].map(({ label, value, color = 'var(--text-secondary)' }) => (
                  <div key={label}>
                    <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>{label}</div>
                    <div style={{ fontSize: '0.9rem', fontWeight: 700, color }}>{value}</div>
                  </div>
                ))}
              </div>
              <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
                <div style={{ fontSize: '1.6rem', fontWeight: 900, color: edgeColor, fontFamily: 'Space Grotesk, sans-serif', lineHeight: 1 }}>
                  {result.edge_pct_display}
                </div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>edge</div>
                <div style={{ fontSize: '0.8rem', fontWeight: 700, color: edgeColor, marginTop: 2 }}>{result.recommendation}</div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
