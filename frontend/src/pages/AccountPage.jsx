import { useState } from 'react';
import { motion } from 'framer-motion';
import { useNavigate, Link } from 'react-router-dom';
import { TrendingUp, LogOut, ArrowLeft } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { api } from '../api/client';

export default function AccountPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [cancelling, setCancelling]   = useState(false);
  const [cancelled,  setCancelled]    = useState(false);
  const [activeUntil, setActiveUntil] = useState(null);
  const [error, setError]             = useState(null);

  if (!user) {
    navigate('/login', { replace: true });
    return null;
  }

  const isPremium = user.tier === 'premium';
  const expiresAt = user.premium_expires_at
    ? new Date(user.premium_expires_at).toLocaleDateString('en-CA', { year: 'numeric', month: 'long', day: 'numeric' })
    : null;

  async function handleCancel() {
    if (!window.confirm('Cancel your subscription? You\'ll keep Premium access until the end of your billing period.')) return;
    setCancelling(true);
    setError(null);
    try {
      const res = await api.cancelSubscription();
      const until = new Date(res.active_until).toLocaleDateString('en-CA', { year: 'numeric', month: 'long', day: 'numeric' });
      setActiveUntil(until);
      setCancelled(true);
    } catch (e) {
      setError(e.message || 'Could not cancel subscription. Please try again.');
    } finally {
      setCancelling(false);
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-primary)' }}>
      {/* Nav */}
      <motion.nav
        initial={{ y: -20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ duration: 0.4 }}
        style={{
          position: 'fixed', top: 0, left: 0, right: 0, zIndex: 100,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '0 2rem', height: '60px',
          background: 'rgba(8,12,16,0.9)', backdropFilter: 'blur(12px)',
          borderBottom: '1px solid var(--border)',
        }}
      >
        <Link to="/dashboard" style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', textDecoration: 'none' }}>
          <div style={{ width: 26, height: 26, borderRadius: 6, background: 'linear-gradient(135deg,#1d9bf0,#0066cc)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <TrendingUp size={14} color="#fff" />
          </div>
          <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)' }}>
            Strike<span style={{ color: 'var(--accent-blue)' }}>Edge</span>
          </span>
        </Link>
        <motion.button whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.96 }}
          onClick={logout}
          style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.4rem 0.9rem', borderRadius: 8, border: '1px solid var(--border)', background: 'var(--bg-card)', color: 'var(--text-muted)', fontSize: '0.82rem', cursor: 'pointer' }}>
          <LogOut size={13} /> Sign out
        </motion.button>
      </motion.nav>

      <div style={{ maxWidth: 520, margin: '0 auto', padding: '5.5rem 1.5rem 4rem' }}>
        <motion.button
          initial={{ opacity: 0 }} animate={{ opacity: 1 }}
          onClick={() => navigate('/dashboard')}
          style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: '0.82rem', cursor: 'pointer', marginBottom: '2rem', padding: 0 }}
        >
          <ArrowLeft size={14} /> Back to Dashboard
        </motion.button>

        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 800, letterSpacing: '-0.5px', marginBottom: '2rem' }}>Account</h1>

          {/* Account info card */}
          <div style={{ borderRadius: 14, border: '1px solid var(--border)', background: 'var(--bg-card)', overflow: 'hidden', marginBottom: '1rem' }}>
            <div style={{ padding: '1.25rem 1.5rem', borderBottom: '1px solid var(--border)' }}>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.3rem' }}>Email</div>
              <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>{user.email}</div>
            </div>

            <div style={{ padding: '1.25rem 1.5rem', borderBottom: isPremium ? '1px solid var(--border)' : 'none' }}>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.4rem' }}>Plan</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                {isPremium ? (
                  <span style={{ fontSize: '0.75rem', fontWeight: 700, padding: '3px 10px', borderRadius: 999, background: 'rgba(29,155,240,0.12)', color: 'var(--accent-blue)', border: '1px solid rgba(29,155,240,0.25)' }}>
                    PREMIUM
                  </span>
                ) : (
                  <span style={{ fontSize: '0.75rem', fontWeight: 700, padding: '3px 10px', borderRadius: 999, background: 'rgba(139,148,158,0.1)', color: 'var(--text-muted)', border: '1px solid var(--border)' }}>
                    FREE
                  </span>
                )}
              </div>
            </div>

            {isPremium && expiresAt && (
              <div style={{ padding: '1.25rem 1.5rem' }}>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.3rem' }}>
                  {cancelled ? 'Access until' : 'Renews'}
                </div>
                <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>{activeUntil ?? expiresAt}</div>
              </div>
            )}
          </div>

          {/* Subscription actions */}
          {isPremium && !cancelled && (
            <div style={{ borderRadius: 14, border: '1px solid var(--border)', background: 'var(--bg-card)', padding: '1.25rem 1.5rem' }}>
              <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.35rem' }}>Cancel subscription</div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '1rem', lineHeight: 1.5 }}>
                You'll keep Premium access until the end of your current billing period.
              </div>
              {error && (
                <div style={{ fontSize: '0.8rem', color: '#ef4444', marginBottom: '0.75rem' }}>{error}</div>
              )}
              <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
                onClick={handleCancel} disabled={cancelling}
                style={{ padding: '0.5rem 1.1rem', borderRadius: 8, border: '1px solid rgba(239,68,68,0.3)', background: 'rgba(239,68,68,0.08)', color: '#ef4444', fontSize: '0.82rem', fontWeight: 600, cursor: cancelling ? 'wait' : 'pointer' }}>
                {cancelling ? 'Cancelling…' : 'Cancel Subscription'}
              </motion.button>
            </div>
          )}

          {cancelled && (
            <div style={{ borderRadius: 14, border: '1px solid rgba(0,200,83,0.25)', background: 'rgba(0,200,83,0.06)', padding: '1.25rem 1.5rem', fontSize: '0.85rem', color: 'var(--accent-green)' }}>
              Subscription cancelled. You'll have Premium access until <strong>{activeUntil}</strong>.
            </div>
          )}

          {!isPremium && (
            <div style={{ borderRadius: 14, border: '1px solid var(--border)', background: 'var(--bg-card)', padding: '1.25rem 1.5rem' }}>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
                Upgrade to unlock all daily picks, performance tracking, and history.
              </div>
              <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
                onClick={() => api.createCheckout().then(r => { window.location.href = r.url; })}
                style={{ padding: '0.5rem 1.25rem', borderRadius: 8, border: 'none', background: 'linear-gradient(135deg,#1d9bf0,#0066cc)', color: '#fff', fontSize: '0.85rem', fontWeight: 700, cursor: 'pointer' }}>
                Upgrade to Premium — $25/mo
              </motion.button>
            </div>
          )}
        </motion.div>
      </div>
    </div>
  );
}
