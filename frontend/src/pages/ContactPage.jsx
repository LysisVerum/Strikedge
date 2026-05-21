import { Link } from 'react-router-dom';
import { TrendingUp, Mail } from 'lucide-react';

function LegalNav() {
  return (
    <nav style={{
      position: 'fixed', top: 0, left: 0, right: 0, zIndex: 100,
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '0 2rem', height: '60px',
      background: 'rgba(8,12,16,0.9)', backdropFilter: 'blur(12px)',
      borderBottom: '1px solid var(--border)',
    }}>
      <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', textDecoration: 'none' }}>
        <div style={{ width: 26, height: 26, borderRadius: 6, background: 'linear-gradient(135deg,#1d9bf0,#0066cc)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <TrendingUp size={14} color="#fff" />
        </div>
        <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)' }}>
          Strike<span style={{ color: 'var(--accent-blue)' }}>Edge</span>
        </span>
      </Link>
    </nav>
  );
}

export default function ContactPage() {
  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-primary)' }}>
      <LegalNav />
      <div style={{ maxWidth: 520, margin: '0 auto', padding: '5.5rem 1.5rem 4rem' }}>
        <h1 style={{ fontSize: '2rem', fontWeight: 800, letterSpacing: '-0.5px', marginBottom: '0.5rem' }}>Contact</h1>
        <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', lineHeight: 1.7, marginBottom: '2.5rem' }}>
          Have a question, feedback, or issue with your subscription? We'd love to hear from you.
        </p>

        <div style={{ borderRadius: 14, border: '1px solid var(--border)', background: 'var(--bg-card)', padding: '1.5rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
            <Mail size={18} color="var(--accent-blue)" />
            <span style={{ fontWeight: 600, fontSize: '0.95rem' }}>Email us</span>
          </div>
          <a
            href="mailto:nich8804@gmail.com"
            style={{ fontSize: '0.9rem', color: 'var(--accent-blue)', textDecoration: 'none' }}
          >
            nich8804@gmail.com
          </a>
          <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginTop: '0.75rem', lineHeight: 1.6 }}>
            We typically respond within 24 hours. For subscription or billing issues, include the email address on your account.
          </p>
        </div>
      </div>
    </div>
  );
}
