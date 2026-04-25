import { useState } from 'react';
import { motion } from 'framer-motion';
import { Loader2 } from 'lucide-react';
import { api } from '../api/client';

const FIELD_STYLE = {
  width: '100%',
  padding: '0.55rem 0.75rem',
  borderRadius: 8,
  border: '1px solid var(--border)',
  background: 'var(--bg-secondary)',
  color: 'var(--text-primary)',
  fontSize: '0.875rem',
  outline: 'none',
  boxSizing: 'border-box',
};

const LABEL_STYLE = {
  display: 'block',
  fontSize: '0.75rem',
  color: 'var(--text-muted)',
  marginBottom: '0.3rem',
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
};

const DEFAULT = {
  pitcher_name: '', last_name: '', first_name: '',
  opponent_team: '', park_team: '',
  is_home: true, days_rest: 5,
  line: 7.5, over_odds: -115,
  k_pct_last5: '', k_pct_last15: '', k_pct_season: '',
  avg_ip_last5: '', opp_k_pct: '',
};

export default function PredictForm({ onResult }) {
  const [form, setForm] = useState(DEFAULT);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  const set = (k) => (e) => {
    const v = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
    setForm(f => ({ ...f, [k]: v }));
  };

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setErr(null);
    try {
      const body = {
        ...form,
        days_rest: parseInt(form.days_rest, 10),
        line: parseFloat(form.line),
        over_odds: parseInt(form.over_odds, 10),
        k_pct_last5:  form.k_pct_last5  ? parseFloat(form.k_pct_last5)  : null,
        k_pct_last15: form.k_pct_last15 ? parseFloat(form.k_pct_last15) : null,
        k_pct_season: form.k_pct_season ? parseFloat(form.k_pct_season) : null,
        avg_ip_last5: form.avg_ip_last5 ? parseFloat(form.avg_ip_last5) : null,
        opp_k_pct:    form.opp_k_pct    ? parseFloat(form.opp_k_pct)    : null,
      };
      const result = await api.predict(body);
      onResult(result);
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={submit} style={{
      padding: '1.5rem',
      borderRadius: 12,
      border: '1px solid var(--border-glow)',
      background: 'var(--bg-card)',
    }}>
      <div style={{ marginBottom: '1.25rem' }}>
        <h3 style={{ fontWeight: 700, fontSize: '0.95rem', marginBottom: '0.3rem' }}>Custom Prediction</h3>
        <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
          Leave K-rate fields blank to auto-fetch from pybaseball.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '0.85rem', marginBottom: '1rem' }}>
        <Field label="Full Name" value={form.pitcher_name} onChange={set('pitcher_name')} placeholder="Gerrit Cole" required />
        <Field label="Last Name" value={form.last_name}    onChange={set('last_name')}    placeholder="Cole"        required />
        <Field label="First Name" value={form.first_name}  onChange={set('first_name')}   placeholder="Gerrit"      required />
        <Field label="Opponent Team" value={form.opponent_team} onChange={set('opponent_team')} placeholder="BOS" required />
        <Field label="Park (home team)" value={form.park_team} onChange={set('park_team')} placeholder="NYY" required />
        <Field label="K/U Line" type="number" step="0.5" value={form.line} onChange={set('line')} required />
        <Field label="Over Odds (American)" type="number" value={form.over_odds} onChange={set('over_odds')} required />
        <Field label="Days Rest" type="number" min="1" max="10" value={form.days_rest} onChange={set('days_rest')} required />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '0.85rem', marginBottom: '1.25rem' }}>
        <Field label="K% Last 5 (0–1)" type="number" step="0.01" value={form.k_pct_last5}  onChange={set('k_pct_last5')}  placeholder="0.31" />
        <Field label="K% Last 15 (0–1)" type="number" step="0.01" value={form.k_pct_last15} onChange={set('k_pct_last15')} placeholder="0.29" />
        <Field label="K% Season (0–1)"  type="number" step="0.01" value={form.k_pct_season} onChange={set('k_pct_season')} placeholder="0.28" />
        <Field label="Avg IP Last 5"    type="number" step="0.1"  value={form.avg_ip_last5}  onChange={set('avg_ip_last5')}  placeholder="6.1" />
        <Field label="Opp K% (0–1)"     type="number" step="0.01" value={form.opp_k_pct}     onChange={set('opp_k_pct')}     placeholder="0.24" />
        <div>
          <label style={LABEL_STYLE}>Home Game</label>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', height: 36 }}>
            <input type="checkbox" checked={form.is_home} onChange={set('is_home')} style={{ width: 16, height: 16, accentColor: 'var(--accent-blue)' }} />
            <span style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Yes</span>
          </div>
        </div>
      </div>

      {err && (
        <div style={{ padding: '0.6rem 0.9rem', borderRadius: 8, background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', color: 'var(--accent-red)', fontSize: '0.82rem', marginBottom: '1rem' }}>
          {err}
        </div>
      )}

      <motion.button
        type="submit"
        whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}
        disabled={loading}
        style={{
          display: 'flex', alignItems: 'center', gap: '0.5rem',
          padding: '0.65rem 1.4rem', borderRadius: 8, border: 'none',
          background: 'linear-gradient(135deg, #1d9bf0, #0066cc)',
          color: '#fff', fontWeight: 700, fontSize: '0.875rem',
          cursor: loading ? 'not-allowed' : 'pointer', opacity: loading ? 0.7 : 1,
        }}
      >
        {loading && <Loader2 size={15} style={{ animation: 'spin 1s linear infinite' }} />}
        {loading ? 'Predicting…' : 'Get Edge'}
      </motion.button>
    </form>
  );
}

function Field({ label, ...props }) {
  return (
    <div>
      <label style={LABEL_STYLE}>{label}</label>
      <input style={FIELD_STYLE} {...props}
        onFocus={e => e.target.style.borderColor = 'var(--border-glow)'}
        onBlur={e  => e.target.style.borderColor = 'var(--border)'}
      />
    </div>
  );
}
