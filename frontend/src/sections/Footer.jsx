import { TrendingUp } from 'lucide-react';

export default function Footer() {
  return (
    <footer style={{
      borderTop: '1px solid var(--border)',
      padding: '2.5rem 1.5rem',
      background: 'var(--bg-secondary)',
    }}>
      <div style={{
        maxWidth: 1100, margin: '0 auto',
        display: 'flex', flexWrap: 'wrap',
        justifyContent: 'space-between', alignItems: 'center',
        gap: '1rem',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <div style={{
            width: 28, height: 28, borderRadius: 7,
            background: 'linear-gradient(135deg, #1d9bf0, #0066cc)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <TrendingUp size={15} color="#fff" />
          </div>
          <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontWeight: 700, fontSize: '1rem' }}>
            ml<span style={{ color: 'var(--accent-blue)' }}>bet</span>
          </span>
        </div>
        <div style={{ display: 'flex', gap: '1.5rem', flexWrap: 'wrap' }}>
          {['Privacy', 'Terms', 'Responsible Gambling', 'Contact'].map(link => (
            <a
              key={link}
              href="#"
              style={{ fontSize: '0.8rem', color: 'var(--text-muted)', textDecoration: 'none' }}
              onMouseEnter={e => e.target.style.color = 'var(--text-secondary)'}
              onMouseLeave={e => e.target.style.color = 'var(--text-muted)'}
            >
              {link}
            </a>
          ))}
        </div>
        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
          © 2026 mlbet. For entertainment purposes.
        </div>
      </div>
      <div style={{ maxWidth: 1100, margin: '1.5rem auto 0', paddingTop: '1.5rem', borderTop: '1px solid var(--border)' }}>
        <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', lineHeight: 1.6 }}>
          mlbet provides data-driven analysis and is not a licensed gambling operator. Please gamble responsibly.
          If you or someone you know has a gambling problem, call 1-800-GAMBLER.
        </p>
      </div>
    </footer>
  );
}
