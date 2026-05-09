import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { RefreshCw, AlertCircle, TrendingUp, Clock, BarChart2, XCircle, Lock, Zap, LogOut } from 'lucide-react';
import { api } from '../api/client';
import { useAuth } from '../context/AuthContext';
import PickCard from '../components/PickCard';
import LockedPickCard from '../components/LockedPickCard';
import PerformancePanel from '../components/PerformancePanel';
import HistoryLog from '../components/HistoryLog';
import DashboardNav from '../components/DashboardNav';

const TABS = [
  { id: 'picks',       label: "Today's Picks", icon: TrendingUp },
  { id: 'performance', label: 'Performance',   icon: BarChart2,  premium: true },
  { id: 'history',     label: 'History',       icon: Clock,      premium: true },
];

export default function Dashboard() {
  const { user, loading: authLoading, logout } = useAuth();
  const navigate        = useNavigate();
  const [searchParams]  = useSearchParams();

  const [picks, setPicks]               = useState([]);
  const [totalPicks, setTotalPicks]     = useState(0);
  const [tokensRemaining, setTokens]    = useState(0);
  const [tokensResetAt, setResetAt]     = useState(null);
  const [meta, setMeta]                 = useState(null);
  const [loading, setLoading]           = useState(true);
  const [error, setError]               = useState(null);
  const [tab, setTab]                   = useState('picks');
  const [refreshRunning, setRefreshRunning] = useState(false);
  const [upgrading, setUpgrading]       = useState(false);
  const [historyRecords, setHistoryRecords] = useState([]);
  const [skippedRecords, setSkippedRecords] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyLoaded,  setHistoryLoaded]  = useState(false);
  const [upgraded, setUpgraded]         = useState(searchParams.get('upgrade') === 'success');

  const isPremium   = user?.tier === 'premium';

  // Redirect unauthenticated users to login
  useEffect(() => {
    if (!authLoading && !user) navigate('/login', { replace: true });
  }, [authLoading, user, navigate]);

  const fetchPicks = async () => {
    setLoading(true); setError(null);
    try {
      const [picksData, health] = await Promise.all([
        api.todayPicks(),
        api.health().catch(() => null),
      ]);
      setPicks(picksData.picks || []);
      setTotalPicks(picksData.total_picks ?? (picksData.picks?.length ?? 0));
      if (picksData.tokens_remaining != null) setTokens(picksData.tokens_remaining);
      if (picksData.tokens_reset_at)          setResetAt(picksData.tokens_reset_at);
      setMeta({ date: picksData.date, model_version: picksData.model_version, last_update: picksData.last_update });
      setRefreshRunning(health?.refresh_running ?? false);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  const handleRefresh = async () => {
    setLoading(true); setError(null);
    try {
      await api.refresh();
      await new Promise(r => setTimeout(r, 1200));
      await fetchPicks();
    } catch (e) { setError(e.message); setLoading(false); }
  };

  const handleUnlocked = (fullPick, newTokenCount) => {
    setPicks(prev => prev.map(p => p.pitcher_name === fullPick.pitcher_name ? fullPick : p));
    setTokens(newTokenCount);
  };

  const handleUpgrade = async () => {
    setUpgrading(true);
    try {
      const data = await api.createCheckout();
      window.location.href = data.url;
    } catch (e) {
      alert(e.message);
      setUpgrading(false);
    }
  };

  const fetchHistoryData = async () => {
    setHistoryLoading(true);
    try {
      const [liveRec, skipped] = await Promise.all([api.liveRecord(), api.skipped()]);
      setHistoryRecords((liveRec.records || []).filter(r => r.bet > 0));
      setSkippedRecords(Array.isArray(skipped) ? skipped : []);
      setHistoryLoaded(true);
    } catch (e) {
      console.error('History fetch failed:', e);
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    if (user) fetchPicks();
  }, [user]);  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (tab === 'history' && isPremium && !historyLoaded) fetchHistoryData();
  }, [tab, isPremium]); // eslint-disable-line react-hooks/exhaustive-deps

  // While auth is loading or user isn't set yet, show nothing
  if (authLoading || !user) return null;

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-primary)' }}>
      <DashboardNav user={user} onLogout={logout} />

      <div style={{ maxWidth: 1000, margin: '0 auto', padding: '5rem 1.5rem 4rem' }}>

        {/* Upgrade success banner */}
        <AnimatePresence>
          {upgraded && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '0.9rem 1.25rem', borderRadius: 10, marginBottom: '1.25rem',
                background: 'rgba(0,200,83,0.1)', border: '1px solid rgba(0,200,83,0.3)',
                color: 'var(--accent-green)',
              }}
            >
              <span style={{ fontWeight: 600 }}>Welcome to Premium! Full access is now unlocked.</span>
              <button onClick={() => setUpgraded(false)} style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', fontSize: '1.1rem' }}>×</button>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
          style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: '1rem', marginBottom: '1.75rem' }}
        >
          <div>
            <h1 style={{ fontSize: 'clamp(1.4rem, 3.5vw, 2rem)', fontWeight: 800, letterSpacing: '-1px', marginBottom: '0.2rem' }}>
              Strikeout Prop Edges
            </h1>
            {meta && (
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                {meta.date} · {meta.model_version}
                {meta.last_update && <> · updated {meta.last_update.replace('T', ' ')}</>}
              </p>
            )}
          </div>
          <div style={{ display: 'flex', gap: '0.6rem', alignItems: 'center' }}>
            {!isPremium && (
              <motion.button
                whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.97 }}
                onClick={handleUpgrade}
                disabled={upgrading}
                style={{
                  display: 'flex', alignItems: 'center', gap: '0.4rem',
                  padding: '0.45rem 0.9rem', borderRadius: 8,
                  border: 'none', background: 'linear-gradient(135deg, #1d9bf0, #0066cc)',
                  color: '#fff', fontSize: '0.82rem', fontWeight: 700, cursor: 'pointer',
                }}
              >
                <Zap size={13} />
                {upgrading ? 'Redirecting…' : 'Go Premium'}
              </motion.button>
            )}
            <motion.button
              whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.96 }}
              onClick={handleRefresh}
              style={{
                display: 'flex', alignItems: 'center', gap: '0.4rem',
                padding: '0.45rem 0.9rem', borderRadius: 8,
                border: '1px solid var(--border)', background: 'var(--bg-card)',
                color: 'var(--text-secondary)', fontSize: '0.82rem', cursor: 'pointer',
              }}
            >
              <RefreshCw size={13} /> Refresh
            </motion.button>
            <motion.button
              whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.96 }}
              onClick={logout}
              title="Sign out"
              style={{
                display: 'flex', alignItems: 'center', gap: '0.4rem',
                padding: '0.45rem 0.9rem', borderRadius: 8,
                border: '1px solid var(--border)', background: 'var(--bg-card)',
                color: 'var(--text-muted)', fontSize: '0.82rem', cursor: 'pointer',
              }}
            >
              <LogOut size={13} />
            </motion.button>
          </div>
        </motion.div>

        {/* Tab bar */}
        <div style={{
          display: 'flex', gap: '0.25rem', marginBottom: '1.75rem',
          borderBottom: '1px solid var(--border)',
        }}>
          {TABS.map(({ id, label, icon: Icon, premium }) => {
            const locked = premium && !isPremium;
            return (
              <button
                key={id}
                onClick={() => setTab(id)}
                style={{
                  display: 'flex', alignItems: 'center', gap: '0.4rem',
                  padding: '0.6rem 1rem', background: 'none', border: 'none',
                  cursor: 'pointer', fontSize: '0.875rem', fontWeight: 600,
                  color: tab === id ? 'var(--text-primary)' : locked ? 'var(--text-muted)' : 'var(--text-muted)',
                  borderBottom: `2px solid ${tab === id ? 'var(--accent-blue)' : 'transparent'}`,
                  marginBottom: -1, transition: 'color 0.15s',
                  opacity: locked ? 0.6 : 1,
                }}
              >
                <Icon size={14} />
                {label}
                {locked && <Lock size={11} style={{ opacity: 0.6 }} />}
              </button>
            );
          })}
        </div>

        {/* Tab content */}
        <AnimatePresence mode="wait">
          <motion.div
            key={tab}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.2 }}
          >
            {tab === 'picks' && (
              <>
                {loading && <SkeletonList />}

                {error && (
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: '0.75rem',
                    padding: '1.25rem 1.5rem', borderRadius: 12,
                    border: '1px solid rgba(239,68,68,0.3)',
                    background: 'rgba(239,68,68,0.07)', color: 'var(--accent-red)',
                  }}>
                    <AlertCircle size={18} />
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>API unreachable</div>
                      <div style={{ fontSize: '0.78rem', opacity: 0.8, marginTop: 2 }}>{error} — make sure the backend is running on port 5000.</div>
                    </div>
                  </div>
                )}

                {!loading && !error && (() => {
                  const renderPick = (pick, i) => pick.locked
                    ? <LockedPickCard key={pick.pitcher_name} pick={pick} index={i} tokens={tokensRemaining} onUnlocked={handleUnlocked} onUpgrade={handleUpgrade} />
                    : <PickCard       key={pick.pitcher_name} pick={pick} index={i} />;

                  const lined   = picks.filter(p => p.has_line !== false);
                  const noLined = picks.filter(p => p.has_line === false);

                  return (
                    <>
                      {/* Token strip for free users */}
                      {!isPremium && (
                        <div style={{
                          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                          padding: '0.6rem 1rem', borderRadius: 8, marginBottom: '1rem',
                          background: 'rgba(29,155,240,0.06)', border: '1px solid rgba(29,155,240,0.2)',
                          fontSize: '0.82rem',
                        }}>
                          <span style={{ color: 'var(--text-secondary)' }}>
                            <span style={{ color: 'var(--accent-blue)', fontWeight: 700 }}>{tokensRemaining} unlock token</span>
                            {tokensRemaining !== 1 ? 's' : ''} remaining this week
                            {tokensResetAt && (
                              <span style={{ color: 'var(--text-muted)', marginLeft: '0.4rem' }}>
                                · resets {new Date(tokensResetAt).toLocaleDateString('en-CA', { weekday: 'short', month: 'short', day: 'numeric' })}
                              </span>
                            )}
                          </span>
                          <motion.button
                            whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.97 }}
                            onClick={handleUpgrade}
                            disabled={upgrading}
                            style={{
                              display: 'flex', alignItems: 'center', gap: '0.3rem',
                              padding: '0.3rem 0.7rem', borderRadius: 6, border: 'none',
                              background: 'linear-gradient(135deg, #1d9bf0, #0066cc)',
                              color: '#fff', fontSize: '0.78rem', fontWeight: 700, cursor: 'pointer',
                            }}
                          >
                            <Zap size={11} /> Upgrade
                          </motion.button>
                        </div>
                      )}

                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
                        {lined.map((pick, i) => renderPick(pick, i))}
                        {noLined.length > 0 && (
                          <>
                            {lined.length > 0 && (
                              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', margin: '0.4rem 0' }}>
                                <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
                                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', whiteSpace: 'nowrap' }}>
                                  Line unavailable
                                </span>
                                <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
                              </div>
                            )}
                            {noLined.map((pick, i) => renderPick(pick, lined.length + i))}
                          </>
                        )}
                      </div>

                      {picks.length === 0 && (
                        <div style={{ textAlign: 'center', padding: '3rem 1rem', color: 'var(--text-muted)' }}>
                          <TrendingUp size={32} style={{ marginBottom: '0.75rem', opacity: 0.3 }} />
                          {refreshRunning ? (
                            <>
                              <p style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>Loading today's data…</p>
                              <p style={{ fontSize: '0.8rem', marginTop: '0.4rem' }}>
                                Fetching Statcast & odds — takes ~2 min on first load. Refresh the page when done.
                              </p>
                            </>
                          ) : (
                            <p>No picks with sufficient edge today.</p>
                          )}
                        </div>
                      )}
                    </>
                  );
                })()}
              </>
            )}

            {(tab === 'performance' || tab === 'history' || tab === 'skipped') && !isPremium ? (
              <PremiumGate onUpgrade={handleUpgrade} upgrading={upgrading} />
            ) : (
              <>
                {tab === 'performance' && <PerformancePanel />}
                {tab === 'history'     && (
                  <HistoryLog
                    records={historyRecords}
                    skippedRecords={skippedRecords}
                    loading={historyLoading}
                    onDeleteRecord={(date, name) =>
                      setHistoryRecords(prev => prev.filter(r => !(r.date === date && r.pitcher_name === name)))
                    }
                  />
                )}
              </>
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}

function PremiumGate({ onUpgrade, upgrading }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      style={{
        textAlign: 'center',
        padding: '4rem 2rem',
        borderRadius: 16,
        border: '1px solid var(--border)',
        background: 'var(--bg-card)',
      }}
    >
      <div style={{
        width: 56, height: 56, borderRadius: '50%', margin: '0 auto 1.25rem',
        background: 'rgba(29,155,240,0.1)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <Lock size={24} color="var(--accent-blue)" />
      </div>
      <h3 style={{ fontSize: '1.2rem', fontWeight: 700, marginBottom: '0.6rem' }}>Premium Feature</h3>
      <p style={{ color: 'var(--text-secondary)', maxWidth: 380, margin: '0 auto 1.5rem', lineHeight: 1.6, fontSize: '0.9rem' }}>
        Upgrade to StrikeEdge Premium to access full history, performance analytics, and all daily picks.
      </p>
      <motion.button
        whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.97 }}
        onClick={onUpgrade}
        disabled={upgrading}
        style={{
          padding: '0.7rem 1.75rem', borderRadius: 8, border: 'none',
          background: 'linear-gradient(135deg, #1d9bf0, #0066cc)',
          color: '#fff', fontSize: '0.95rem', fontWeight: 700, cursor: 'pointer',
          display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
        }}
      >
        <Zap size={16} />
        {upgrading ? 'Redirecting…' : 'Upgrade — $25 CAD/month'}
      </motion.button>
    </motion.div>
  );
}

function SkeletonList() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
      {[0, 1, 2].map(i => (
        <motion.div
          key={i}
          animate={{ opacity: [0.4, 0.7, 0.4] }}
          transition={{ duration: 1.4, repeat: Infinity, delay: i * 0.12 }}
          style={{ height: 90, borderRadius: 12, background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        />
      ))}
    </div>
  );
}
