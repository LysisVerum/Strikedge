import { useState } from 'react';
import { motion } from 'framer-motion';
import { Lock, Unlock, Zap } from 'lucide-react';
import { api } from '../api/client';

export default function LockedPickCard({ pick, tokens, onUnlocked, onUpgrade, index = 0 }) {
  const [unlocking, setUnlocking] = useState(false);
  const [error, setError]         = useState('');

  const handleUnlock = async () => {
    if (tokens <= 0) return;
    setUnlocking(true);
    setError('');
    try {
      const data = await api.unlockPick(pick.pitcher_name);
      onUnlocked(data.pick, data.tokens_remaining);
    } catch (e) {
      setError(e.message);
      setUnlocking(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06 }}
      style={{
        padding: '1rem 1.25rem',
        borderRadius: 12,
        border: '1px solid var(--border)',
        background: 'var(--bg-card)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: '1rem',
        flexWrap: 'wrap',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Left: pitcher info (always visible) */}
      <div style={{ minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.2rem' }}>
          <Lock size={13} color="var(--text-muted)" />
          <span style={{ fontWeight: 700, fontSize: '0.95rem', color: 'var(--text-primary)' }}>
            {pick.pitcher_name}
          </span>
        </div>
        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
          {pick.matchup || "Today's game"}
        </div>
      </div>

      {/* Middle: blurred fake stats */}
      <div style={{
        display: 'flex', gap: '1.25rem', alignItems: 'center',
        filter: 'blur(5px)',
        userSelect: 'none',
        pointerEvents: 'none',
        flex: 1,
        justifyContent: 'center',
      }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--accent-green)' }}>+XX.X%</div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>edge</div>
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--text-primary)' }}>UNDER X.X K</div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>HIGH confidence</div>
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>XX%</div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>model prob</div>
        </div>
      </div>

      {/* Right: unlock or upgrade */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '0.3rem', flexShrink: 0 }}>
        {tokens > 0 ? (
          <motion.button
            whileHover={{ scale: 1.04 }}
            whileTap={{ scale: 0.96 }}
            onClick={handleUnlock}
            disabled={unlocking}
            style={{
              display: 'flex', alignItems: 'center', gap: '0.35rem',
              padding: '0.45rem 0.9rem', borderRadius: 8,
              border: 'none',
              background: 'linear-gradient(135deg, #1d9bf0, #0066cc)',
              color: '#fff', fontSize: '0.82rem', fontWeight: 700, cursor: 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            <Unlock size={13} />
            {unlocking ? 'Unlocking…' : `Unlock (${tokens} left)`}
          </motion.button>
        ) : (
          <div style={{ textAlign: 'right' }}>
            <motion.button
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.96 }}
              onClick={onUpgrade}
              style={{
                display: 'flex', alignItems: 'center', gap: '0.35rem',
                padding: '0.45rem 0.9rem', borderRadius: 8,
                border: 'none',
                background: 'linear-gradient(135deg, #1d9bf0, #0066cc)',
                color: '#fff', fontSize: '0.82rem', fontWeight: 700, cursor: 'pointer',
                whiteSpace: 'nowrap',
              }}
            >
              <Zap size={13} /> Go Premium
            </motion.button>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
              Token resets Monday
            </div>
          </div>
        )}
        {error && (
          <div style={{ fontSize: '0.75rem', color: '#f85149' }}>{error}</div>
        )}
      </div>
    </motion.div>
  );
}
