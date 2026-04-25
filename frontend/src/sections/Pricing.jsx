import { motion } from 'framer-motion';
import { Check } from 'lucide-react';

const plans = [
  {
    name: 'Free',
    price: '$0',
    period: 'forever',
    desc: 'Get a feel for the platform. Limited picks daily.',
    features: [
      '3 prop picks per day',
      'K-rate prop model only',
      'Edge % visible',
      'Community Discord access',
    ],
    cta: 'Start Free',
    highlight: false,
    color: 'var(--border)',
  },
  {
    name: 'Pro',
    price: '$29',
    period: '/month',
    desc: 'Full access to all models and real-time alerts.',
    features: [
      'Unlimited daily picks',
      'All prop models (K, H, RBI, BB)',
      'Real-time edge alerts',
      'Line movement tracking',
      'Kelly sizing recommendations',
      'Historical model performance',
    ],
    cta: 'Get Pro Access',
    highlight: true,
    color: 'var(--accent-blue)',
  },
  {
    name: 'Sharp',
    price: '$79',
    period: '/month',
    desc: 'For professional bettors. API access + custom alerts.',
    features: [
      'Everything in Pro',
      'REST API access',
      'Custom model parameters',
      'Slack/webhook alerts',
      'Dedicated support',
      'Early beta feature access',
    ],
    cta: 'Go Sharp',
    highlight: false,
    color: 'var(--accent-amber)',
  },
];

export default function Pricing() {
  return (
    <section id="pricing" style={{ padding: '6rem 1.5rem' }}>
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>
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
            Pricing
          </div>
          <h2 style={{ fontSize: 'clamp(1.8rem, 4vw, 2.6rem)', fontWeight: 800, letterSpacing: '-1px', marginBottom: '0.75rem' }}>
            Simple, transparent pricing
          </h2>
          <p style={{ color: 'var(--text-secondary)', maxWidth: 500, margin: '0 auto', fontSize: '1rem' }}>
            No subscriptions to picks-sellers. Just data, models, and edge.
          </p>
        </motion.div>

        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: '1.25rem',
          alignItems: 'start',
        }}>
          {plans.map((plan, i) => (
            <motion.div
              key={plan.name}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.1, duration: 0.5 }}
              whileHover={{ y: -4 }}
              style={{
                padding: '2rem',
                borderRadius: 16,
                border: `1px solid ${plan.highlight ? 'var(--accent-blue)' : 'var(--border)'}`,
                background: plan.highlight ? 'linear-gradient(160deg, #0d1e30, #0d1117)' : 'var(--bg-card)',
                position: 'relative',
                boxShadow: plan.highlight ? '0 0 40px rgba(29,155,240,0.12)' : 'none',
              }}
            >
              {plan.highlight && (
                <div style={{
                  position: 'absolute', top: -12, left: '50%', transform: 'translateX(-50%)',
                  padding: '3px 14px',
                  borderRadius: 999,
                  background: 'linear-gradient(90deg, #1d9bf0, #0066cc)',
                  fontSize: '0.72rem', fontWeight: 800,
                  color: '#fff', letterSpacing: '0.05em', textTransform: 'uppercase',
                  whiteSpace: 'nowrap',
                }}>
                  Most Popular
                </div>
              )}
              <div style={{ marginBottom: '1.5rem' }}>
                <div style={{ fontWeight: 700, fontSize: '0.9rem', color: plan.color, marginBottom: '0.4rem', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
                  {plan.name}
                </div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.25rem', marginBottom: '0.5rem' }}>
                  <span style={{ fontSize: '2.4rem', fontWeight: 900, fontFamily: 'Space Grotesk, sans-serif' }}>{plan.price}</span>
                  <span style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>{plan.period}</span>
                </div>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>{plan.desc}</p>
              </div>
              <ul style={{ listStyle: 'none', marginBottom: '1.75rem', display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
                {plan.features.map(feat => (
                  <li key={feat} style={{ display: 'flex', gap: '0.6rem', alignItems: 'flex-start', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                    <Check size={14} color="var(--accent-green)" style={{ marginTop: 3, flexShrink: 0 }} />
                    {feat}
                  </li>
                ))}
              </ul>
              <motion.button
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.97 }}
                style={{
                  width: '100%',
                  padding: '0.75rem',
                  borderRadius: 10,
                  border: plan.highlight ? 'none' : '1px solid var(--border)',
                  background: plan.highlight ? 'linear-gradient(135deg, #1d9bf0, #0066cc)' : 'transparent',
                  color: plan.highlight ? '#fff' : 'var(--text-primary)',
                  fontSize: '0.9rem',
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
              >
                {plan.cta}
              </motion.button>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
