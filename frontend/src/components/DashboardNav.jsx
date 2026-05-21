import { motion } from 'framer-motion';
import { TrendingUp } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';

export default function DashboardNav({ user }) {
  const navigate = useNavigate();
  return (
    <motion.nav
      initial={{ y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.4 }}
      style={{
        position: 'fixed', top: 0, left: 0, right: 0, zIndex: 100,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 2rem', height: '60px',
        background: 'rgba(8, 12, 16, 0.9)',
        backdropFilter: 'blur(12px)',
        borderBottom: '1px solid var(--border)',
      }}
    >
      <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', textDecoration: 'none' }}>
        <div style={{
          width: 26, height: 26, borderRadius: 6,
          background: 'linear-gradient(135deg, #1d9bf0, #0066cc)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <TrendingUp size={14} color="#fff" />
        </div>
        <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)' }}>
          Strike<span style={{ color: 'var(--accent-blue)' }}>Edge</span>
        </span>
      </Link>

      <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'center' }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: '0.5rem',
          padding: '0.3rem 0.8rem', borderRadius: 999,
          background: 'rgba(0,200,83,0.08)', border: '1px solid rgba(0,200,83,0.2)',
          fontSize: '0.75rem', color: 'var(--accent-green)', fontWeight: 600,
        }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent-green)', display: 'inline-block' }} />
          Live
        </div>
        {user && (
          <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
            onClick={() => navigate('/account')}
            style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '0.78rem', color: 'var(--text-muted)', maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', padding: 0 }}>
            {user.email}
          </motion.button>
        )}
        {user?.tier === 'premium' && (
          <span style={{
            fontSize: '0.72rem', fontWeight: 700, padding: '2px 8px', borderRadius: 999,
            background: 'rgba(29,155,240,0.12)', color: 'var(--accent-blue)',
            border: '1px solid rgba(29,155,240,0.25)',
          }}>
            PREMIUM
          </span>
        )}
      </div>
    </motion.nav>
  );
}
