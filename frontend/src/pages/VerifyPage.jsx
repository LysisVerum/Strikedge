import { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { TrendingUp, CheckCircle, XCircle, Loader } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export default function VerifyPage() {
  const [searchParams]  = useSearchParams();
  const { login }       = useAuth();
  const navigate        = useNavigate();
  const [status, setStatus] = useState('verifying');  // verifying | success | error
  const [message, setMessage] = useState('');

  useEffect(() => {
    const token = searchParams.get('token');
    if (!token) {
      setStatus('error');
      setMessage('No token found in link. Please request a new one.');
      return;
    }

    fetch(`/api/auth/verify?token=${encodeURIComponent(token)}`)
      .then(async res => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.description || 'Token invalid or expired');
        return data;
      })
      .then(data => {
        login(data.session_token, data.email, data.tier);
        setStatus('success');
        setTimeout(() => navigate('/dashboard'), 1200);
      })
      .catch(err => {
        setStatus('error');
        setMessage(err.message);
      });
  }, []);   // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      padding: '2rem', background: 'var(--bg-primary)',
    }}>
      {/* Logo */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '2.5rem' }}>
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

      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        style={{
          textAlign: 'center',
          padding: '2.5rem',
          borderRadius: 16,
          border: '1px solid var(--border)',
          background: 'var(--bg-card)',
          maxWidth: 380, width: '100%',
        }}
      >
        {status === 'verifying' && (
          <>
            <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}
              style={{ display: 'inline-block', marginBottom: '1rem' }}>
              <Loader size={40} color="var(--accent-blue)" />
            </motion.div>
            <h2 style={{ fontSize: '1.2rem', fontWeight: 700 }}>Signing you in…</h2>
          </>
        )}

        {status === 'success' && (
          <>
            <CheckCircle size={44} color="var(--accent-green)" style={{ marginBottom: '1rem' }} />
            <h2 style={{ fontSize: '1.2rem', fontWeight: 700, marginBottom: '0.5rem' }}>You're in!</h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
              Redirecting to your dashboard…
            </p>
          </>
        )}

        {status === 'error' && (
          <>
            <XCircle size={44} color="#f85149" style={{ marginBottom: '1rem' }} />
            <h2 style={{ fontSize: '1.2rem', fontWeight: 700, marginBottom: '0.5rem' }}>Link expired</h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', lineHeight: 1.6, marginBottom: '1.5rem' }}>
              {message}
            </p>
            <a href="/login" style={{
              display: 'inline-block', padding: '0.7rem 1.5rem',
              borderRadius: 8, background: 'linear-gradient(135deg, #1d9bf0, #0066cc)',
              color: '#fff', textDecoration: 'none', fontWeight: 600, fontSize: '0.9rem',
            }}>
              Get a new link
            </a>
          </>
        )}
      </motion.div>
    </div>
  );
}
