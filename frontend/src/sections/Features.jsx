import { motion } from 'framer-motion';
import { Brain, BarChart2, Bell, ShieldCheck, Layers, TrendingUp } from 'lucide-react';

const features = [
  {
    icon: Brain,
    title: 'ML Prediction Engine',
    desc: 'Gradient-boosted models trained on years of Statcast data, pitch arsenal, handedness splits, and ballpark factors.',
    color: '#1d9bf0',
  },
  {
    icon: BarChart2,
    title: 'Market Edge Detector',
    desc: 'Compare our model probabilities against sportsbook lines in real-time to find the largest positive expected-value gaps.',
    color: '#00c853',
  },
  {
    icon: Bell,
    title: 'Instant Edge Alerts',
    desc: 'Get notified the moment a prop line moves in your favor or a new high-edge bet becomes available.',
    color: '#f59e0b',
  },
  {
    icon: Layers,
    title: 'Multi-Book Line Aggregation',
    desc: 'We pull lines from DraftKings, FanDuel, BetMGM, and more — always showing you the best available number.',
    color: '#a855f7',
  },
  {
    icon: TrendingUp,
    title: 'Historical Backtest Results',
    desc: 'Every model comes with full backtesting on 3+ seasons of data. No cherry-picked results.',
    color: '#1d9bf0',
  },
  {
    icon: ShieldCheck,
    title: 'Bankroll Management',
    desc: 'Kelly criterion and flat-unit recommendations built in, so you always know how much to stake.',
    color: '#00c853',
  },
];

const cardVariants = {
  hidden: { opacity: 0, y: 30 },
  visible: (i) => ({
    opacity: 1, y: 0,
    transition: { delay: i * 0.1, duration: 0.5 },
  }),
};

export default function Features() {
  return (
    <section id="features" style={{ padding: '6rem 1.5rem', maxWidth: 1100, margin: '0 auto' }}>
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ duration: 0.5 }}
        style={{ textAlign: 'center', marginBottom: '3.5rem' }}
      >
        <div style={{
          display: 'inline-block', padding: '0.3rem 0.9rem',
          borderRadius: 999, border: '1px solid var(--border)',
          background: 'var(--bg-card)', fontSize: '0.78rem',
          color: 'var(--text-muted)', textTransform: 'uppercase',
          letterSpacing: '0.1em', marginBottom: '1rem',
        }}>
          Features
        </div>
        <h2 style={{ fontSize: 'clamp(1.8rem, 4vw, 2.6rem)', fontWeight: 800, letterSpacing: '-1px', marginBottom: '0.75rem' }}>
          Built for the serious bettor
        </h2>
        <p style={{ color: 'var(--text-secondary)', maxWidth: 520, margin: '0 auto', fontSize: '1rem', lineHeight: 1.7 }}>
          Every feature is designed to give you a quantifiable advantage over the market, not just pretty charts.
        </p>
      </motion.div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
        gap: '1.25rem',
      }}>
        {features.map((f, i) => (
          <motion.div
            key={f.title}
            custom={i}
            variants={cardVariants}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            whileHover={{ y: -4, borderColor: f.color + '55' }}
            style={{
              padding: '1.75rem',
              borderRadius: 14,
              border: '1px solid var(--border)',
              background: 'var(--bg-card)',
              cursor: 'default',
              transition: 'border-color 0.25s, background 0.25s',
            }}
            onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-card-hover)'}
            onMouseLeave={e => e.currentTarget.style.background = 'var(--bg-card)'}
          >
            <div style={{
              width: 44, height: 44, borderRadius: 10,
              background: f.color + '18',
              border: `1px solid ${f.color}30`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              marginBottom: '1rem',
            }}>
              <f.icon size={20} color={f.color} />
            </div>
            <h3 style={{ fontWeight: 700, fontSize: '1rem', marginBottom: '0.5rem', color: 'var(--text-primary)' }}>
              {f.title}
            </h3>
            <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', lineHeight: 1.65 }}>
              {f.desc}
            </p>
          </motion.div>
        ))}
      </div>
    </section>
  );
}
