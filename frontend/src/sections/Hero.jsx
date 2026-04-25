import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { ArrowRight, Zap } from 'lucide-react';
import { Link } from 'react-router-dom';

const floatVariants = {
  initial: { y: 0 },
  animate: {
    y: [-6, 6, -6],
    transition: { duration: 5, repeat: Infinity, ease: 'easeInOut' },
  },
};

export default function Hero() {
  const [stats, setStats]     = useState({ winRate: '54.0%', edgeAvg: '+22.3%', bets: '457' });
  const [topPick, setTopPick] = useState(null);

  useEffect(() => {
    // Live record for win rate
    fetch('/api/live-record')
      .then(r => r.json())
      .then(data => {
        const resolved = (data.records || []).filter(r => r.outcome);
        if (resolved.length >= 5) {
          setStats({
            winRate: `${data.win_rate?.toFixed(1) ?? '54.0'}%`,
            edgeAvg: data.roi != null ? `${data.roi >= 0 ? '+' : ''}${data.roi.toFixed(1)}%` : '+22.3%',
            bets:    `${resolved.length}+`,
          });
        }
      })
      .catch(() => {});

    // Today's picks for the top edge card
    fetch('/api/picks/today')
      .then(r => r.json())
      .then(data => {
        const picks = data.picks || [];
        if (!picks.length) return;
        const top = picks.reduce((best, p) =>
          Math.abs(p.edge ?? 0) > Math.abs(best.edge ?? 0) ? p : best
        , picks[0]);
        setTopPick(top);
      })
      .catch(() => {});
  }, []);

  const statItems = [
    { label: 'Backtest Win Rate',  value: stats.winRate,  color: 'var(--accent-green)' },
    { label: 'Backtest ROI',       value: stats.edgeAvg,  color: 'var(--accent-amber)' },
    { label: 'Bets Analyzed',      value: stats.bets,     color: 'var(--accent-blue)'  },
  ];

  const edgePct   = topPick ? Math.abs(topPick.edge ?? 0) * 100 : null;
  const barWidth  = edgePct != null ? Math.min(edgePct * 3, 95) : 73;
  const probPct   = topPick ? Math.round((topPick.model_prob_over ?? 0.65) * 100) : null;

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
          padding: '0.35rem 0.85rem',
          borderRadius: 999,
          border: '1px solid rgba(29,155,240,0.3)',
          background: 'rgba(29,155,240,0.08)',
          fontSize: '0.8rem',
          color: 'var(--accent-blue)',
          fontWeight: 600,
          marginBottom: '1.5rem',
          letterSpacing: '0.02em',
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
          fontSize: 'clamp(2.4rem, 6vw, 4.2rem)',
          fontWeight: 800,
          letterSpacing: '-2px',
          lineHeight: 1.1,
          textAlign: 'center',
          maxWidth: 800,
          marginBottom: '1.25rem',
        }}
      >
        Find Your Edge in{' '}
        <span style={{
          background: 'linear-gradient(90deg, #1d9bf0, #00c853)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
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
          fontSize: 'clamp(1rem, 2vw, 1.15rem)',
          color: 'var(--text-secondary)',
          maxWidth: 580,
          textAlign: 'center',
          lineHeight: 1.7,
          marginBottom: '2.5rem',
        }}
      >
        mlbet uses machine learning to surface statistically significant edges
        in pitcher strikeout props. Beat the books with data, not gut feelings.
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
              padding: '0.8rem 1.8rem',
              borderRadius: 10,
              border: 'none',
              background: 'linear-gradient(135deg, #1d9bf0, #0066cc)',
              color: '#fff',
              fontSize: '0.95rem',
              fontWeight: 700,
              cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: '0.4rem',
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
              padding: '0.8rem 1.8rem',
              borderRadius: 10,
              border: '1px solid var(--border)',
              background: 'var(--bg-card)',
              color: 'var(--text-primary)',
              fontSize: '0.95rem',
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            See Today's Picks
          </motion.button>
        </Link>
      </motion.div>

      {/* Stats strip — real backtest numbers */}
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.6, duration: 0.6 }}
        style={{
          display: 'flex', gap: '2.5rem', flexWrap: 'wrap',
          justifyContent: 'center', marginTop: '4rem',
          padding: '1.5rem 2.5rem',
          borderRadius: 16,
          border: '1px solid var(--border)',
          background: 'var(--bg-card)',
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

      {/* Floating prop card — today's actual top pick or placeholder */}
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
          display: 'flex', flexDirection: 'column', gap: '0.75rem',
          maxWidth: 380,
          width: '100%',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Today's Top Edge
          </span>
          <span style={{
            fontSize: '0.72rem', fontWeight: 700, padding: '2px 8px',
            borderRadius: 999, background: 'rgba(0,200,83,0.12)',
            color: 'var(--accent-green)', border: '1px solid rgba(0,200,83,0.25)',
          }}>
            {topPick ? 'LIVE' : 'SAMPLE'}
          </span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ fontWeight: 600, fontSize: '1rem', color: 'var(--text-primary)' }}>
              {topPick ? topPick.pitcher_name : 'Load Today\'s Picks'}
            </div>
            <div style={{ fontSize: '0.83rem', color: 'var(--text-secondary)', marginTop: 2 }}>
              {topPick
                ? `${topPick.recommendation} ${topPick.line} Strikeouts · ${topPick.matchup ?? ''}`
                : 'Visit the dashboard to see today\'s slate'}
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '1.3rem', fontWeight: 800, color: 'var(--accent-green)' }}>
              {edgePct != null ? `${edgePct >= 0 ? '+' : ''}${edgePct.toFixed(1)}%` : '—'}
            </div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>edge vs market</div>
          </div>
        </div>
        <div style={{ height: 4, borderRadius: 4, background: 'var(--border)', overflow: 'hidden' }}>
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${barWidth}%` }}
            transition={{ delay: 1, duration: 1, ease: 'easeOut' }}
            style={{ height: '100%', background: 'linear-gradient(90deg, #1d9bf0, #00c853)', borderRadius: 4 }}
          />
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Model confidence</span>
          <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--accent-blue)' }}>
            {probPct != null ? `${probPct}%` : '—'}
          </span>
        </div>
      </motion.div>
    </section>
  );
}
