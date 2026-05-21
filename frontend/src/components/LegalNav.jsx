import { Link } from 'react-router-dom';
import { TrendingUp } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export default function LegalNav() {
  const { user } = useAuth();
  const home = user ? '/dashboard' : '/';
  return (
    <nav style={{
      position: 'fixed', top: 0, left: 0, right: 0, zIndex: 100,
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '0 2rem', height: '60px',
      background: 'rgba(8,12,16,0.9)', backdropFilter: 'blur(12px)',
      borderBottom: '1px solid var(--border)',
    }}>
      <Link to={home} style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', textDecoration: 'none' }}>
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
