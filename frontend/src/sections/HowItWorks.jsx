import { motion } from 'framer-motion';
import { Database, Cpu, Target, DollarSign } from 'lucide-react';

const steps = [
  {
    icon: Database,
    num: '01',
    title: 'Data Ingestion',
    desc: 'We pull Statcast pitch data, player logs, weather, lineup, and umpire tendencies daily.',
    color: '#1d9bf0',
  },
  {
    icon: Cpu,
    num: '02',
    title: 'Model Inference',
    desc: 'Our gradient-boosted model scores each available prop across 60+ engineered features.',
    color: '#a855f7',
  },
  {
    icon: Target,
    num: '03',
    title: 'Edge Calculation',
    desc: "We compare model probability to the book's implied probability — if we see +5% or more, it surfaces.",
    color: '#f59e0b',
  },
  {
    icon: DollarSign,
    num: '04',
    title: 'You Bet with Conviction',
    desc: 'Ranked picks with confidence tier, unit sizing, and best available line — ready to act on.',
    color: '#00c853',
  },
];

export default function HowItWorks() {
  return (
    <section id="models" style={{ padding: '6rem 1.5rem', background: 'var(--bg-secondary)' }}>
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
            How It Works
          </div>
          <h2 style={{ fontSize: 'clamp(1.8rem, 4vw, 2.6rem)', fontWeight: 800, letterSpacing: '-1px', marginBottom: '0.75rem' }}>
            From raw data to bet recommendation
          </h2>
          <p style={{ color: 'var(--text-secondary)', maxWidth: 520, margin: '0 auto', fontSize: '1rem', lineHeight: 1.7 }}>
            Every pick flows through a transparent, repeatable pipeline — no black boxes.
          </p>
        </motion.div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {steps.map((step, i) => (
            <motion.div
              key={step.num}
              initial={{ opacity: 0, x: i % 2 === 0 ? -30 : 30 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.1, duration: 0.5 }}
              style={{
                display: 'flex', alignItems: 'flex-start', gap: '1.5rem',
                padding: '1.75rem',
                borderRadius: 14,
                border: '1px solid var(--border)',
                background: 'var(--bg-card)',
              }}
            >
              <div style={{
                minWidth: 52, height: 52, borderRadius: 12,
                background: step.color + '18',
                border: `1px solid ${step.color}35`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <step.icon size={22} color={step.color} />
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.4rem' }}>
                  <span style={{
                    fontSize: '0.72rem', fontWeight: 800,
                    color: step.color, letterSpacing: '0.1em',
                  }}>
                    STEP {step.num}
                  </span>
                  <h3 style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)' }}>
                    {step.title}
                  </h3>
                </div>
                <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', lineHeight: 1.65 }}>
                  {step.desc}
                </p>
              </div>
              <div style={{
                fontSize: '2.5rem', fontWeight: 900,
                color: step.color + '20',
                fontFamily: 'Space Grotesk, sans-serif',
                lineHeight: 1, alignSelf: 'center',
                userSelect: 'none',
              }}>
                {step.num}
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
