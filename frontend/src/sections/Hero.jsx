import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { ArrowRight, Zap, ExternalLink } from 'lucide-react';
import { Link } from 'react-router-dom';

const floatVariants = {
  initial: { y: 0 },
  animate: {
    y: [-5, 5, -5],
    transition: { duration: 5, repeat: Infinity, ease: 'easeInOut' },
  },
};

const SAMPLE_PICK = {
  pitcher_name:    'Paul Skenes',
  recommendation:  'OVER',
  line:            7.5,
  over_odds:       -118,
  line_source:     'DraftKings',
  confidence:      'HIGH',
  edge_pct_display:'+9.2%',
  edge_pct:        0.092,
  model_prob_over: 0.72,
  implied_prob_over: 0.628,
  matchup:         'vs CHC',
  predicted_ks:    8.1,
};

const CONF_COLORS = {
  HIGH:   { bg: 'rgba(0,200,83,0.10)',   border: 'rgba(0,200,83,0.28)',   text: '#00c853' },
  MEDIUM: { bg: 'rgba(245,158,11,0.10)', border: 'rgba(245,158,11,0.28)', text: '#f59e0b' },
  LOW:    { bg: 'rgba(139,148,158,0.10)',border: 'rgba(139,148,158,0.28)', text: '#8b949e' },
};

function MiniPickCard({ pick, isLive }) {
  const conf      = CONF_COLORS[pick.confidence] ?? CONF_COLORS.LOW;
  const edgeVal   = typeof pick.edge_pct === 'number' ? pick.edge_pct : 0;
  const edgeColor = edgeVal >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
  const modelPct  = Math.round((pick.model_prob_over ?? 0) * 100);
  const impliedPct = Math.round((pick.implied_prob_over ?? 0) * 100);

  return (
    <motion.div
      variants={floatVariants}
      initial="initial"
      animate="animate"
      style={{
        marginTop: '3rem',
        padding: '1.25rem 1.5rem',
        borderRadius: 14,
        border: '1px solid var(--border-glow)',
        background: 'var(--bg-card)',
        boxShadow: '0 0 40px rgba(29,155,240,0.08)',
        maxWidth: 400,
        width: '100%',
      }}
    >
      {/* Header row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.85rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <span style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)' }}>
            {pick.pitcher_name}
          </span>
          <span style={{
            fontSize: '0.65rem', fontWeight: 700, padding: '2px 7px', borderRadius: 999,
            background: conf.bg, border: `1px solid ${conf.border}`, color: conf.text,
            textTransform: 'uppercase', letterSpacing: '0.05em',
          }}>
            {pick.confidence}
          </span>
        </div>
        <span style={{
          fontSize: '0.68rem', fontWeight: 700, padding: '2px 8px', borderRadius: 999,
          background: isLive ? 'rgba(0,200,83,0.12)' : 'rgba(139,148,158,0.12)',
          color: isLive ? 'var(--accent-green)' : 'var(--text-muted)',
          border: `1px solid ${isLive ? 'rgba(0,200,83,0.25)' : 'rgba(139,148,158,0.2)'}`,
        }}>
          {isLive ? 'LIVE' : 'SAMPLE'}
        </span>
      </div>

      {/* Pick row */}
      <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '0.3rem' }}>
        <span style={{ color: 'var(--accent-green)', fontWeight: 700 }}>
          {pick.recommendation} {pick.line}
        </span>
        <span style={{ color: 'var(--text-muted)', marginLeft: '0.3rem' }}>
          ({pick.over_odds > 0 ? '+' : ''}{pick.over_odds})
        </span>
        <span style={{ color: 'var(--text-muted)', marginLeft: '0.5rem' }}>· {pick.matchup}</span>
      </div>

      {/* Book badge */}
      {pick.line_source && (
        <div style={{ marginBottom: '0.85rem' }}>
          <span style={{
            fontSize: '0.68rem', color: 'var(--accent-blue)', fontWeight: 600,
            padding: '2px 8px', borderRadius: 6,
            border: '1px solid rgba(29,155,240,0.25)',
            background: 'rgba(29,155,240,0.07)',
            display: 'inline-flex', alignItems: 'center', gap: '0.2rem',
          }}>
            {pick.line_source} <ExternalLink size={9} />
          </span>
        </div>
      )}

      {/* Model prob bar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.85rem' }}>
        <div style={{ flex: 1, height: 3, borderRadius: 3, background: 'var(--border)', overflow: 'hidden', maxWidth: 160 }}>
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${modelPct}%` }}
            transition={{ delay: 1, duration: 0.8, ease: 'easeOut' }}
            style={{ height: '100%', background: `linear-gradient(90deg, ${edgeColor}, var(--accent-blue))`, borderRadius: 3 }}
          />
        </div>
        <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
          {modelPct}% · implied {impliedPct}%
        </span>
      </div>

      {/* Edge + Ks */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <div>
          <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginBottom: 2 }}>proj Ks</div>
          <div style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--text-secondary)', fontFamily: 'Space Grotesk' }}>
            {pick.predicted_ks}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginBottom: 2 }}>edge vs market</div>
          <div style={{ fontSize: '1.6rem', fontWeight: 900, color: edgeColor, fontFamily: 'Space Grotesk', lineHeight: 1 }}>
            {pick.edge_pct_display}
          </div>
        </div>
      </div>
    </motion.div>
  );
}

export default function Hero() {
  const [stats, setStats]     = useState(null);
  const [topPick, setTopPick] = useState(null);
  const [pickLive, setPickLive] = useState(false);

  useEffect(() => {
    fetch('/api/live-record')
      .then(r => r.json())
      .then(data => {
        const resolved = (data.records || []).filter(r => r.outcome);
        if (resolved.length >= 10) {
          setStats({
            winRate: `${data.win_rate?.toFixed(1) ?? '—'}%`,
            roi:     data.roi != null ? `${data.roi >= 0 ? '+' : ''}${data.roi.toFixed(1)}%` : '—',
            bets:    `${resolved.length}+`,
          });
        }
      })
      .catch(() => {});

    fetch('/api/picks/today')
      .then(r => r.json())
      .then(data => {
        const picks = (data.picks || []).filter(
          p => p.has_line && p.recommendation !== 'PASS' && p.edge_pct != null
        );
        if (!picks.length) return;
        const top = picks.reduce((best, p) =>
          Math.abs(p.edge_pct ?? 0) > Math.abs(best.edge_pct ?? 0) ? p : best
        , picks[0]);
        setTopPick(top);
        setPickLive(true);
      })
      .catch(() => {});
  }, []);

  const displayPick = topPick ?? SAMPLE_PICK;

  const statItems = stats ? [
    { label: 'Model Win Rate', value: stats.winRate, color: 'var(--accent-green)' },
    { label: 'Model ROI',      value: stats.roi,     color: 'var(--accent-amber)' },
    { label: 'Picks Logged',   value: stats.bets,    color: 'var(--accent-blue)'  },
  ] : [
    { label: 'Model Accuracy', value: '54%+',  color: 'var(--accent-green)' },
    { label: 'Avg Edge Found', value: '8–12%', color: 'var(--accent-amber)' },
    { label: 'Games Analyzed', value: '6,000+', color: 'var(--accent-blue)' },
  ];

  return (
    <section style={{
      minHeight: '100vh',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '6rem 1.5rem 4rem',
      position: 'relative',
      overflow: 'hidden',
    }}>
      {/* Background glow orbs */}
      <div style={{
        position: 'absolute', top: '15%', left: '20%',
        width: 500, height: 500,
        background: 'radial-gradient(circle, rgba(29,155,240,0.08) 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />
      <div style={{
        position: 'absolute', bottom: '20%', right: '15%',
        width: 400, height: 400,
        background: 'radial-gradient(circle, rgba(0,200,83,0.06) 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />

      {/* Badge */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1, duration: 0.5 }}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
          padding: '0.35rem 0.85rem', borderRadius: 999,
          border: '1px solid rgba(29,155,240,0.3)',
          background: 'rgba(29,155,240,0.08)',
          fontSize: '0.8rem', color: 'var(--accent-blue)',
          fontWeight: 600, marginBottom: '1.5rem', letterSpacing: '0.02em',
        }}
      >
        <Zap size={13} />
        ML-Powered Baseball Prop Edges
      </motion.div>

      {/* Headline */}
      <motion.h1
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2, duration: 0.6 }}
        style={{
          fontSize: 'clamp(2.4rem, 6vw, 4.2rem)', fontWeight: 800,
          letterSpacing: '-2px', lineHeight: 1.1, textAlign: 'center',
          maxWidth: 800, marginBottom: '1.25rem',
        }}
      >
        Find Your Edge in{' '}
        <span style={{
          background: 'linear-gradient(90deg, #1d9bf0, #00c853)',
          WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
        }}>
          Baseball Props
        </span>
      </motion.h1>

      {/* Subheadline */}
      <motion.p
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3, duration: 0.6 }}
        style={{
          fontSize: 'clamp(1rem, 2vw, 1.15rem)', color: 'var(--text-secondary)',
          maxWidth: 560, textAlign: 'center', lineHeight: 1.7, marginBottom: '2.5rem',
        }}
      >
        StrikeEdge uses machine learning to surface statistically significant edges
        in MLB pitcher strikeout props. Beat the books with data, not gut feelings.
      </motion.p>

      {/* CTA Buttons */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4, duration: 0.6 }}
        style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', justifyContent: 'center' }}
      >
        <Link to="/login" style={{ textDecoration: 'none' }}>
          <motion.button
            whileHover={{ scale: 1.04, boxShadow: '0 0 30px rgba(29,155,240,0.3)' }}
            whileTap={{ scale: 0.97 }}
            style={{
              padding: '0.8rem 1.8rem', borderRadius: 10, border: 'none',
              background: 'linear-gradient(135deg, #1d9bf0, #0066cc)',
              color: '#fff', fontSize: '0.95rem', fontWeight: 700,
              cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.4rem',
            }}
          >
            Start for Free <ArrowRight size={16} />
          </motion.button>
        </Link>
        <Link to="/login" style={{ textDecoration: 'none' }}>
          <motion.button
            whileHover={{ scale: 1.04 }}
            whileTap={{ scale: 0.97 }}
            style={{
              padding: '0.8rem 1.8rem', borderRadius: 10,
              border: '1px solid var(--border)', background: 'var(--bg-card)',
              color: 'var(--text-primary)', fontSize: '0.95rem', fontWeight: 500, cursor: 'pointer',
            }}
          >
            See Today's Picks
          </motion.button>
        </Link>
      </motion.div>

      {/* Stats strip */}
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.6, duration: 0.6 }}
        style={{
          display: 'flex', gap: '2.5rem', flexWrap: 'wrap',
          justifyContent: 'center', marginTop: '4rem',
          padding: '1.5rem 2.5rem', borderRadius: 16,
          border: '1px solid var(--border)', background: 'var(--bg-card)',
        }}
      >
        {statItems.map(({ label, value, color }) => (
          <div key={label} style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '1.8rem', fontWeight: 800, color, fontFamily: 'Space Grotesk' }}>
              {value}
            </div>
            <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: 2, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              {label}
            </div>
          </div>
        ))}
      </motion.div>

      {/* Floating pick card */}
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.75, duration: 0.6 }}
        style={{ width: '100%', display: 'flex', justifyContent: 'center' }}
      >
        <MiniPickCard pick={displayPick} isLive={pickLive} />
      </motion.div>
    </section>
  );
}
