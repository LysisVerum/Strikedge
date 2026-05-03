import { motion, AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';

function StatRow({ label, value, format, color = 'var(--text-primary)' }) {
  const display = value == null ? '—' : format ? format(value) : value;
  const missing = value == null;
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.45rem 0', borderBottom: '1px solid var(--border)' }}>
      <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{label}</span>
      <span style={{ fontSize: '0.82rem', fontWeight: 700, color: missing ? 'var(--text-muted)' : color, fontFamily: 'Space Grotesk, sans-serif' }}>
        {display}
      </span>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div style={{ marginBottom: '1.25rem' }}>
      <p style={{ fontSize: '0.68rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '0.5rem' }}>
        {title}
      </p>
      {children}
    </div>
  );
}

export default function PitcherCard({ pick, onClose }) {
  const f = pick.features ?? {};
  const hasFeatures = pick.features != null;

  const statcastMissing = hasFeatures && f.ff == null && f.velo == null && f.swstr == null;
  const allFeaturesMissing = hasFeatures && statcastMissing && f.k5 == null && f.fip == null;

  const pct = (v) => v != null ? `${(v * 100).toFixed(1)}%` : null;
  const mph = (v) => v != null ? `${v.toFixed(1)} mph` : null;
  const rpm = (v) => v != null ? `${Math.round(v)} rpm` : null;
  const ip  = (v) => v != null ? v.toFixed(1) : null;

  return (
    <AnimatePresence>
      {/* Backdrop */}
      <motion.div
        key="backdrop"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0,
          background: 'rgba(0,0,0,0.6)',
          backdropFilter: 'blur(3px)',
          zIndex: 100,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          padding: '1rem',
        }}
      >
        {/* Card */}
        <motion.div
          key="card"
          initial={{ opacity: 0, scale: 0.93, y: 16 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.93, y: 16 }}
          transition={{ duration: 0.22, ease: 'easeOut' }}
          onClick={e => e.stopPropagation()}
          style={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            borderRadius: 16,
            width: '100%',
            maxWidth: 400,
            maxHeight: '85vh',
            overflowY: 'auto',
            padding: '1.5rem',
            position: 'relative',
            boxShadow: '0 24px 80px rgba(0,0,0,0.5)',
          }}
        >
          {/* Close */}
          <button
            onClick={onClose}
            style={{
              position: 'absolute', top: '1rem', right: '1rem',
              background: 'var(--bg-secondary)', border: '1px solid var(--border)',
              borderRadius: 8, padding: '4px 6px', cursor: 'pointer',
              display: 'flex', alignItems: 'center', color: 'var(--text-muted)',
            }}
          >
            <X size={14} />
          </button>

          {/* Header */}
          <div style={{ marginBottom: '1.5rem', paddingRight: '2rem' }}>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-primary)', marginBottom: '0.3rem' }}>
              {pick.pitcher_name}
            </h2>
            <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>{pick.matchup}</div>
            {pick.line_source && pick.line_source !== 'model' && (
              <span style={{
                fontSize: '0.68rem', fontWeight: 700, padding: '2px 8px', borderRadius: 6,
                background: 'rgba(29,155,240,0.08)', border: '1px solid rgba(29,155,240,0.25)',
                color: 'var(--accent-blue)',
              }}>
                {pick.line_source}
              </span>
            )}
            {(!pick.line_source || pick.line_source === 'model') && (
              <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>model-projected line</span>
            )}
          </div>

          {/* Warnings */}
          {allFeaturesMissing && (
            <div style={{ marginBottom: '1rem', padding: '0.6rem 0.85rem', borderRadius: 8, background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', fontSize: '0.75rem', color: '#ef4444' }}>
              No qualifying start history found — model using learned defaults only. Treat with caution.
            </div>
          )}
          {!allFeaturesMissing && statcastMissing && (
            <div style={{ marginBottom: '1rem', padding: '0.6rem 0.85rem', borderRadius: 8, background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.25)', fontSize: '0.75rem', color: '#f59e0b' }}>
              Pitch arsenal data unavailable — K-rate and FIP features are real, Statcast columns will update overnight.
            </div>
          )}

          {/* K Rate */}
          <Section title="K Rate Trend">
            <StatRow label="Last 5 starts"  value={f.k5}  format={pct} color="var(--accent-blue)" />
            <StatRow label="Last 15 starts" value={f.k15} format={pct} color="var(--accent-blue)" />
            <StatRow label="Season"         value={f.ks}  format={pct} color="var(--text-secondary)" />
            <StatRow label="Avg IP / start" value={f.ip5} format={ip}  color="var(--text-secondary)" />
          </Section>

          {/* Pitcher Quality */}
          <Section title="Pitcher Quality">
            <StatRow label="FIP (last 15 starts)" value={f.fip} color={f.fip != null ? (f.fip < 3.5 ? 'var(--accent-green)' : f.fip < 4.5 ? 'var(--accent-amber)' : 'var(--accent-red)') : undefined} />
          </Section>

          {/* Pitch Arsenal */}
          <Section title="Pitch Arsenal">
            <StatRow label="Four-seam FB usage"  value={f.ff}    format={pct} color="#1d9bf0" />
            <StatRow label="FB velocity"          value={f.velo}  format={mph} color="var(--accent-green)" />
            <StatRow label="FB spin rate"         value={f.spin}  format={rpm} color="var(--text-secondary)" />
            <StatRow label="Swinging strike rate" value={f.swstr} format={pct} color="#a855f7" />
            <StatRow label="Whiff rate"           value={f.whiff} format={pct} color="#a855f7" />
            <StatRow label="CSW%"                 value={f.csw}   format={pct} color="#a855f7" />
          </Section>

          {/* Matchup Context */}
          <Section title="Matchup Context">
            <StatRow label="Opp team K%"       value={f.opp}          format={pct} color="var(--accent-amber)" />
            <StatRow label="Opp lineup K%"     value={f.lineup_opp}   format={pct} color="var(--accent-amber)" />
            <StatRow label="Matchup K score"   value={f.matchup_score} format={pct} color="var(--text-secondary)" />
            <StatRow label="Umpire K rate"     value={f.umpire}       format={pct} color="var(--text-muted)" />
          </Section>

          {/* Model Output */}
          <Section title="Model Output">
            <StatRow label="Projected Ks"   value={pick.predicted_ks} color="var(--text-primary)" />
            <StatRow label="Model P(Over)"  value={pick.model_prob_over}  format={pct} color="var(--accent-blue)" />
            <StatRow label="Implied P(Over)" value={pick.implied_prob_over} format={pct} color="var(--text-muted)" />
            <StatRow
              label="Edge"
              value={pick.edge_pct_display}
              color={(pick.edge_pct ?? 0) >= 0 ? 'var(--accent-green)' : 'var(--accent-red)'}
            />
          </Section>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
