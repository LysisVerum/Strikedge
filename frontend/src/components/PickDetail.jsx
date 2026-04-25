import { motion } from 'framer-motion';

function StatBar({ label, value, max, color = 'var(--accent-blue)', format = (v) => `${(v * 100).toFixed(1)}%` }) {
  const missing = value == null || isNaN(value);
  const pct = missing ? 0 : Math.min((value / max) * 100, 100);
  return (
    <div style={{ marginBottom: '0.6rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{label}</span>
        <span style={{ fontSize: '0.75rem', fontWeight: 700, color: missing ? 'var(--text-muted)' : color }}>
          {missing ? '—' : format(value)}
        </span>
      </div>
      <div style={{ height: 5, borderRadius: 3, background: 'var(--border)', overflow: 'hidden' }}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
          style={{ height: '100%', background: missing ? 'var(--border)' : color, borderRadius: 3 }}
        />
      </div>
    </div>
  );
}

function Chip({ label, value, color = 'var(--text-secondary)' }) {
  return (
    <div style={{
      padding: '0.4rem 0.75rem', borderRadius: 8,
      border: '1px solid var(--border)', background: 'var(--bg-secondary)',
      display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2,
    }}>
      <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>{label}</span>
      <span style={{ fontSize: '0.9rem', fontWeight: 700, color }}>{value}</span>
    </div>
  );
}

export default function PickDetail({ pick }) {
  const f = pick.features ?? {};
  const edgeColor = (pick.edge_pct ?? 0) >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
  const hasLine   = pick.has_line;

  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: 'auto' }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.28 }}
      style={{ overflow: 'hidden' }}
    >
      <div style={{
        padding: '1.25rem 1.5rem 1.5rem',
        borderTop: '1px solid var(--border)',
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
        gap: '1.5rem',
      }}>

        {/* K Rate trend */}
        <div>
          <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.75rem' }}>K Rate Trend</p>
          <StatBar label="Last 5 starts"  value={f.k5}  max={0.45} color="var(--accent-blue)" />
          <StatBar label="Last 15 starts" value={f.k15} max={0.45} color="var(--accent-blue)" />
          <StatBar label="Season"         value={f.ks}  max={0.45} color="var(--text-secondary)" />
          <div style={{ marginTop: '0.5rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            Avg IP / start: <span style={{ color: f.ip5 ? 'var(--text-primary)' : 'var(--text-muted)', fontWeight: 600 }}>
              {f.ip5 != null ? f.ip5.toFixed(1) : '—'}
            </span>
          </div>
        </div>

        {/* Pitch mix */}
        <div>
          <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.75rem' }}>Pitch Mix</p>
          <StatBar label="Four-seam FB" value={f.ff} max={0.9} color="#1d9bf0" />
          <StatBar label="Slider"       value={f.sl} max={0.9} color="#a855f7" />
          <StatBar label="Changeup"     value={f.ch} max={0.9} color="#f59e0b" />
          <StatBar label="Curveball"    value={f.cb} max={0.9} color="#00c853" />
          <div style={{ marginTop: '0.5rem', fontSize: '0.75rem', color: 'var(--text-muted)', display: 'flex', gap: '1rem' }}>
            <span>Velo: <span style={{ color: f.velo ? 'var(--text-primary)' : 'var(--text-muted)', fontWeight: 600 }}>{f.velo ? `${f.velo.toFixed(1)} mph` : '—'}</span></span>
            <span>Spin: <span style={{ color: f.spin ? 'var(--text-primary)' : 'var(--text-muted)', fontWeight: 600 }}>{f.spin ? `${Math.round(f.spin)}` : '—'}</span></span>
          </div>
          {f.ff == null && (
            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: '0.4rem', fontStyle: 'italic' }}>
              Statcast data unavailable for this pitcher
            </div>
          )}
        </div>

        {/* Context + Model math */}
        <div>
          <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.75rem' }}>Game Context</p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', marginBottom: '1rem' }}>
            <Chip label="Days Rest"   value={f.rest != null ? f.rest : '—'} />
            <Chip label="Home / Away" value={f.home ? 'Home' : 'Away'} />
            <Chip label="Opp K%"      value={f.opp ? `${(f.opp * 100).toFixed(1)}%` : '—'} color="var(--accent-amber)" />
            <Chip
              label="Park Factor"
              value={f.park != null ? (f.park >= 0 ? `+${f.park.toFixed(2)}` : f.park.toFixed(2)) : '—'}
              color={f.park >= 0 ? 'var(--accent-green)' : 'var(--accent-red)'}
            />
          </div>

          <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.6rem' }}>Model Output</p>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82rem', marginBottom: 4 }}>
            <span style={{ color: 'var(--text-secondary)' }}>Predicted Ks</span>
            <span style={{ fontWeight: 700 }}>{pick.predicted_ks}</span>
          </div>
          {hasLine ? (
            <>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82rem', marginBottom: 4 }}>
                <span style={{ color: 'var(--text-secondary)' }}>Model P(Over)</span>
                <span style={{ fontWeight: 700, color: 'var(--accent-blue)' }}>
                  {pick.model_prob_over != null ? `${(pick.model_prob_over * 100).toFixed(1)}%` : '—'}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82rem', marginBottom: 4 }}>
                <span style={{ color: 'var(--text-secondary)' }}>Implied P(Over)</span>
                <span style={{ fontWeight: 700, color: 'var(--text-muted)' }}>
                  {pick.implied_prob_over != null ? `${(pick.implied_prob_over * 100).toFixed(1)}%` : '—'}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem', marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--border)' }}>
                <span style={{ color: 'var(--text-secondary)', fontWeight: 600 }}>Edge</span>
                <span style={{ fontWeight: 800, color: edgeColor }}>{pick.edge_pct_display}</span>
              </div>
            </>
          ) : (
            <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--border)' }}>
              No sportsbook line posted yet — edge calculation unavailable.
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}
