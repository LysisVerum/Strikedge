import { useState } from 'react';
import { motion } from 'framer-motion';
import { TrendingUp, Mail, ArrowRight, Zap } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function LoginPage() {
  const [email, setEmail]     = useState('');
  const [sent, setSent]       = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const res = await fetch('/api/auth/magic-link', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ email }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.description || 'Failed to send login email');
      }
      setSent(true);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '2rem 1.5rem',
      background: 'var(--bg-primary)',
    }}>
      {/* Logo */}
      <Link to="/" style={{ textDecoration: 'none', marginBottom: '2.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <div style={{
            width: 36, height: 36, borderRadius: 9,
            background: 'linear-gradient(135deg, #1d9bf0, #0066cc)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <TrendingUp size={20} color="#fff" />
          </div>
          <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontWeight: 700, fontSize: '1.3rem', color: 'var(--text-primary)' }}>
            Strike<span style={{ color: 'var(--accent-blue)' }}>Edge</span>
          </span>
        </div>
      </Link>

      {/* Card */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        style={{
          width: '100%', maxWidth: 420,
          padding: '2.5rem',
          borderRadius: 16,
          border: '1px solid var(--border)',
          background: 'var(--bg-card)',
        }}
      >
        {sent ? (
          <div style={{ textAlign: 'center' }}>
            <div style={{
              width: 56, height: 56, borderRadius: '50%', margin: '0 auto 1.25rem',
              background: 'rgba(29,155,240,0.1)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <Mail size={26} color="var(--accent-blue)" />
            </div>
            <h2 style={{ fontSize: '1.3rem', fontWeight: 700, marginBottom: '0.75rem' }}>
              Check your email
            </h2>
            <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: '1.5rem' }}>
              We sent a sign-in link to <strong style={{ color: 'var(--text-primary)' }}>{email}</strong>.
              The link expires in 15 minutes.
            </p>
            <button
              onClick={() => { setSent(false); setEmail(''); }}
              style={{
                background: 'none', border: 'none', color: 'var(--accent-blue)',
                cursor: 'pointer', fontSize: '0.9rem', fontWeight: 500,
              }}
            >
              Use a different email
            </button>
          </div>
        ) : (
          <>
            <div style={{
              display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
              padding: '0.3rem 0.75rem', borderRadius: 999,
              border: '1px solid rgba(29,155,240,0.3)',
              background: 'rgba(29,155,240,0.08)',
              fontSize: '0.78rem', color: 'var(--accent-blue)', fontWeight: 600,
              marginBottom: '1.25rem',
            }}>
              <Zap size={12} />
              No password needed
            </div>

            <h1 style={{ fontSize: '1.5rem', fontWeight: 800, marginBottom: '0.4rem' }}>
              Sign in
            </h1>
            <p style={{ color: 'var(--text-secondary)', marginBottom: '1.75rem', lineHeight: 1.5 }}>
              Enter your email and we'll send you a magic link.
            </p>

            <form onSubmit={handleSubmit}>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>
                Email address
              </label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="you@example.com"
                required
                style={{
                  width: '100%', boxSizing: 'border-box',
                  padding: '0.75rem 1rem',
                  borderRadius: 8,
                  border: '1px solid var(--border)',
                  background: 'var(--bg-primary)',
                  color: 'var(--text-primary)',
                  fontSize: '0.95rem',
                  outline: 'none',
                  marginBottom: '1rem',
                }}
              />

              {error && (
                <p style={{ color: '#f85149', fontSize: '0.85rem', marginBottom: '0.75rem' }}>
                  {error}
                </p>
              )}

              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                type="submit"
                disabled={loading}
                style={{
                  width: '100%',
                  padding: '0.8rem',
                  borderRadius: 8,
                  border: 'none',
                  background: loading ? 'rgba(29,155,240,0.4)' : 'linear-gradient(135deg, #1d9bf0, #0066cc)',
                  color: '#fff',
                  fontSize: '0.95rem',
                  fontWeight: 700,
                  cursor: loading ? 'not-allowed' : 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.4rem',
                }}
              >
                {loading ? 'Sending…' : (<>Send sign-in link <ArrowRight size={16} /></>)}
              </motion.button>
            </form>

            <p style={{ textAlign: 'center', marginTop: '1.5rem', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
              Free account gives you today's top 2 picks.{' '}
              <span style={{ color: 'var(--accent-blue)' }}>Premium</span> unlocks everything.
            </p>
          </>
        )}
      </motion.div>
    </div>
  );
}
