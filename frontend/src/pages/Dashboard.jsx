import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { RefreshCw, AlertCircle, TrendingUp, Clock, BarChart2, Lock, Zap, LogOut, Flame } from 'lucide-react';
import { api } from '../api/client';
import { useAuth } from '../context/AuthContext';
import PickCard from '../components/PickCard';
import LockedPickCard from '../components/LockedPickCard';
import PerformancePanel from '../components/PerformancePanel';
import HistoryLog from '../components/HistoryLog';
import DashboardNav from '../components/DashboardNav';
import HittingPickCard from '../components/HittingPickCard';
import HittingPerformancePanel from '../components/HittingPerformancePanel';
import HittingHistoryLog from '../components/HittingHistoryLog';

const TABS = [
  { id: 'picks',       label: "Today's Picks", icon: TrendingUp },
  { id: 'performance', label: 'Performance',   icon: BarChart2,  premium: true },
  { id: 'history',     label: 'History',       icon: Clock,      premium: true },
];

// Orange accent for hitting section
const H_ACCENT        = '#f97316';
const H_ACCENT_BG     = 'rgba(249,115,22,0.10)';
const H_ACCENT_BORDER = 'rgba(249,115,22,0.28)';

export default function Dashboard() {
  const { user, loading: authLoading, logout } = useAuth();
  const navigate        = useNavigate();
  const [searchParams]  = useSearchParams();

  // Prop type toggle: 'strikeout' | 'hitting'
  const [propType, setPropType] = useState('strikeout');

  // Strikeout state
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

  // Hitting state (independent of strikeout)
  const [hPicks, setHPicks]             = useState([]);
  const [hMeta, setHMeta]               = useState(null);
  const [hLoading, setHLoading]         = useState(false);
  const [hError, setHError]             = useState(null);
  const [hTab, setHTab]                 = useState('picks');
  const [hHistoryRecords, setHHistoryRecords] = useState([]);
  const [hSkippedRecords, setHSkippedRecords] = useState([]);
  const [hHistoryLoading, setHHistoryLoading] = useState(false);
  const [hHistoryLoaded,  setHHistoryLoaded]  = useState(false);

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

  const fetchHittingPicks = async () => {
    setHLoading(true); setHError(null);
    try {
      const data = await api.hittingToday();
      setHPicks(data.picks || []);
      setHMeta({ date: data.date, model_version: data.model_version, last_update: data.last_update });
    } catch (e) { setHError(e.message); }
    finally { setHLoading(false); }
  };

  const handleHittingRefresh = async () => {
    setHLoading(true); setHError(null);
    try {
      await api.hittingRefresh();
      // Pipeline re-runs in a background thread; wait for it before re-fetching
      await new Promise(r => setTimeout(r, 8000));
      await fetchHittingPicks();
    } catch (e) { setHError(e.message); setHLoading(false); }
  };

  const fetchHittingHistory = async () => {
    setHHistoryLoading(true);
    try {
      const [liveRec, skipped] = await Promise.all([api.hittingLiveRecord(), api.hittingSkipped()]);
      setHHistoryRecords(liveRec.records || []);
      setHSkippedRecords(Array.isArray(skipped) ? skipped : []);
      setHHistoryLoaded(true);
    } catch (e) {
      console.error('Hitting history fetch failed:', e);
    } finally {
      setHHistoryLoading(false);
    }
  };

  useEffect(() => {
    if (user) fetchPicks();
  }, [user]);  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (tab === 'history' && isPremium && !historyLoaded) fetchHistoryData();
  }, [tab, isPremium]); // eslint-disable-line react-hooks/exhaustive-deps

  // Hitting: fetch picks on first switch to hitting section
  useEffect(() => {
    if (propType === 'hitting' && user && hPicks.length === 0 && !hLoading) fetchHittingPicks();
  }, [propType, user]); // eslint-disable-line react-hooks/exhaustive-deps

  // Hitting: fetch history when history tab is opened
  useEffect(() => {
    if (propType === 'hitting' && hTab === 'history' && isPremium && !hHistoryLoaded) fetchHittingHistory();
  }, [propType, hTab, isPremium]); // eslint-disable-line react-hooks/exhaustive-deps

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

        {/* Prop type toggle */}
        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem' }}>
          <motion.button
            whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
            onClick={() => setPropType('strikeout')}
            style={{
              display: 'flex', alignItems: 'center', gap: '0.45rem',
              padding: '0.5rem 1.1rem', borderRadius: 9, cursor: 'pointer',
              border: `1px solid ${propType === 'strikeout' ? 'rgba(29,155,240,0.4)' : 'var(--border)'}`,
              background: propType === 'strikeout' ? 'rgba(29,155,240,0.10)' : 'transparent',
              color: propType === 'strikeout' ? 'var(--accent-blue)' : 'var(--text-muted)',
              fontSize: '0.85rem', fontWeight: 700, transition: 'all 0.15s',
            }}
          >
            <TrendingUp size={14} />
            Strikeout Props
          </motion.button>
          <motion.button
            whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
            onClick={() => setPropType('hitting')}
            style={{
              display: 'flex', alignItems: 'center', gap: '0.45rem',
              padding: '0.5rem 1.1rem', borderRadius: 9, cursor: 'pointer',
              border: `1px solid ${propType === 'hitting' ? H_ACCENT_BORDER : 'var(--border)'}`,
              background: propType === 'hitting' ? H_ACCENT_BG : 'transparent',
              color: propType === 'hitting' ? H_ACCENT : 'var(--text-muted)',
              fontSize: '0.85rem', fontWeight: 700, transition: 'all 0.15s',
            }}
          >
            <Flame size={14} />
            Hit Props
          </motion.button>
        </div>

        <AnimatePresence mode="wait">

          {/* ===== STRIKEOUT SECTION ===== */}
          {propType === 'strikeout' && (
            <motion.div key="strikeout" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.2 }}>
              {/* Header */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: '1rem', marginBottom: '1.75rem' }}>
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
                    <motion.button whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.97 }}
                      onClick={handleUpgrade} disabled={upgrading}
                      style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.45rem 0.9rem', borderRadius: 8, border: 'none', background: 'linear-gradient(135deg, #1d9bf0, #0066cc)', color: '#fff', fontSize: '0.82rem', fontWeight: 700, cursor: 'pointer' }}>
                      <Zap size={13} />
                      {upgrading ? 'Redirecting…' : 'Go Premium'}
                    </motion.button>
                  )}
                  <motion.button whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.96 }} onClick={handleRefresh}
                    style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.45rem 0.9rem', borderRadius: 8, border: '1px solid var(--border)', background: 'var(--bg-card)', color: 'var(--text-secondary)', fontSize: '0.82rem', cursor: 'pointer' }}>
                    <RefreshCw size={13} /> Refresh
                  </motion.button>
                  <motion.button whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.96 }} onClick={logout} title="Sign out"
                    style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.45rem 0.9rem', borderRadius: 8, border: '1px solid var(--border)', background: 'var(--bg-card)', color: 'var(--text-muted)', fontSize: '0.82rem', cursor: 'pointer' }}>
                    <LogOut size={13} />
                  </motion.button>
                </div>
              </div>

              {/* Tab bar */}
              <div style={{ display: 'flex', gap: '0.25rem', marginBottom: '1.75rem', borderBottom: '1px solid var(--border)' }}>
                {TABS.map(({ id, label, icon: Icon, premium }) => {
                  const locked = premium && !isPremium;
                  return (
                    <button key={id} onClick={() => setTab(id)} style={{
                      display: 'flex', alignItems: 'center', gap: '0.4rem',
                      padding: '0.6rem 1rem', background: 'none', border: 'none',
                      cursor: 'pointer', fontSize: '0.875rem', fontWeight: 600,
                      color: tab === id ? 'var(--text-primary)' : 'var(--text-muted)',
                      borderBottom: `2px solid ${tab === id ? 'var(--accent-blue)' : 'transparent'}`,
                      marginBottom: -1, transition: 'color 0.15s', opacity: locked ? 0.6 : 1,
                    }}>
                      <Icon size={14} />
                      {label}
                      {locked && <Lock size={11} style={{ opacity: 0.6 }} />}
                    </button>
                  );
                })}
              </div>

              {/* Tab content */}
              <AnimatePresence mode="wait">
                <motion.div key={tab} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.2 }}>
                  {tab === 'picks' && (
                    <>
                      {loading && <SkeletonList />}
                      {error && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '1.25rem 1.5rem', borderRadius: 12, border: '1px solid rgba(239,68,68,0.3)', background: 'rgba(239,68,68,0.07)', color: 'var(--accent-red)' }}>
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
                        const edgePicks = picks.filter(p => p.has_line !== false && p.recommendation !== 'PASS');
                        const passPicks = picks.filter(p => p.has_line !== false && p.recommendation === 'PASS' && !p.locked);
                        const noLined   = picks.filter(p => p.has_line === false);
                        return (
                          <>
                            {!isPremium && (
                              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0.6rem 1rem', borderRadius: 8, marginBottom: '1rem', background: 'rgba(29,155,240,0.06)', border: '1px solid rgba(29,155,240,0.2)', fontSize: '0.82rem' }}>
                                <span style={{ color: 'var(--text-secondary)' }}>
                                  <span style={{ color: 'var(--accent-blue)', fontWeight: 700 }}>{tokensRemaining} unlock token</span>
                                  {tokensRemaining !== 1 ? 's' : ''} remaining this week
                                  {tokensResetAt && <span style={{ color: 'var(--text-muted)', marginLeft: '0.4rem' }}>· resets {new Date(tokensResetAt).toLocaleDateString('en-CA', { weekday: 'short', month: 'short', day: 'numeric' })}</span>}
                                </span>
                                <motion.button whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.97 }} onClick={handleUpgrade} disabled={upgrading}
                                  style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', padding: '0.3rem 0.7rem', borderRadius: 6, border: 'none', background: 'linear-gradient(135deg, #1d9bf0, #0066cc)', color: '#fff', fontSize: '0.78rem', fontWeight: 700, cursor: 'pointer' }}>
                                  <Zap size={11} /> Upgrade
                                </motion.button>
                              </div>
                            )}
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
                              {edgePicks.map((pick, i) => renderPick(pick, i))}
                              {passPicks.length > 0 && (
                                <>
                                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', margin: '0.4rem 0' }}>
                                    <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
                                    <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', whiteSpace: 'nowrap' }}>No edge — model output only</span>
                                    <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
                                  </div>
                                  {passPicks.map((pick, i) => (
                                    <div key={pick.pitcher_name} style={{ opacity: 0.55 }}>
                                      <PickCard pick={pick} index={edgePicks.length + i} />
                                    </div>
                                  ))}
                                </>
                              )}
                              {noLined.length > 0 && (
                                <>
                                  {(edgePicks.length > 0 || passPicks.length > 0) && (
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', margin: '0.4rem 0' }}>
                                      <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
                                      <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', whiteSpace: 'nowrap' }}>Line unavailable</span>
                                      <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
                                    </div>
                                  )}
                                  {noLined.map((pick, i) => renderPick(pick, edgePicks.length + passPicks.length + i))}
                                </>
                              )}
                            </div>
                            {picks.length === 0 && (
                              <div style={{ textAlign: 'center', padding: '3rem 1rem', color: 'var(--text-muted)' }}>
                                <TrendingUp size={32} style={{ marginBottom: '0.75rem', opacity: 0.3 }} />
                                {refreshRunning
                                  ? <><p style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>Loading today's data…</p><p style={{ fontSize: '0.8rem', marginTop: '0.4rem' }}>Fetching Statcast & odds — takes ~2 min on first load. Refresh the page when done.</p></>
                                  : <p>No picks with sufficient edge today.</p>}
                              </div>
                            )}
                          </>
                        );
                      })()}
                    </>
                  )}
                  {(tab === 'performance' || tab === 'history') && !isPremium
                    ? <PremiumGate onUpgrade={handleUpgrade} upgrading={upgrading} />
                    : <>
                        {tab === 'performance' && <PerformancePanel />}
                        {tab === 'history' && (
                          <HistoryLog
                            records={historyRecords}
                            skippedRecords={skippedRecords}
                            loading={historyLoading}
                            onDeleteRecord={(date, name) => setHistoryRecords(prev => prev.filter(r => !(r.date === date && r.pitcher_name === name)))}
                          />
                        )}
                      </>
                  }
                </motion.div>
              </AnimatePresence>
            </motion.div>
          )}

          {/* ===== HITTING SECTION ===== */}
          {propType === 'hitting' && (
            <motion.div key="hitting" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.2 }}>
              {/* Header */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: '1rem', marginBottom: '1.75rem' }}>
                <div>
                  <h1 style={{ fontSize: 'clamp(1.4rem, 3.5vw, 2rem)', fontWeight: 800, letterSpacing: '-1px', marginBottom: '0.2rem', color: H_ACCENT }}>
                    Hit Prop Edges
                  </h1>
                  {hMeta && (
                    <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                      {hMeta.date} · {hMeta.model_version}
                      {hMeta.last_update && <> · updated {hMeta.last_update.replace('T', ' ')}</>}
                    </p>
                  )}
                </div>
                <div style={{ display: 'flex', gap: '0.6rem', alignItems: 'center' }}>
                  {!isPremium && (
                    <motion.button whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.97 }}
                      onClick={handleUpgrade} disabled={upgrading}
                      style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.45rem 0.9rem', borderRadius: 8, border: 'none', background: `linear-gradient(135deg, ${H_ACCENT}, #c2410c)`, color: '#fff', fontSize: '0.82rem', fontWeight: 700, cursor: 'pointer' }}>
                      <Zap size={13} />
                      {upgrading ? 'Redirecting…' : 'Go Premium'}
                    </motion.button>
                  )}
                  <motion.button whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.96 }} onClick={handleHittingRefresh} disabled={hLoading}
                    style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.45rem 0.9rem', borderRadius: 8, border: '1px solid var(--border)', background: 'var(--bg-card)', color: hLoading ? 'var(--text-muted)' : 'var(--text-secondary)', fontSize: '0.82rem', cursor: hLoading ? 'wait' : 'pointer' }}>
                    <RefreshCw size={13} style={{ animation: hLoading ? 'spin 1s linear infinite' : 'none' }} /> {hLoading ? 'Fetching…' : 'Refresh'}
                  </motion.button>
                  <motion.button whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.96 }} onClick={logout} title="Sign out"
                    style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.45rem 0.9rem', borderRadius: 8, border: '1px solid var(--border)', background: 'var(--bg-card)', color: 'var(--text-muted)', fontSize: '0.82rem', cursor: 'pointer' }}>
                    <LogOut size={13} />
                  </motion.button>
                </div>
              </div>

              {/* Tab bar — orange underline */}
              <div style={{ display: 'flex', gap: '0.25rem', marginBottom: '1.75rem', borderBottom: '1px solid var(--border)' }}>
                {TABS.map(({ id, label, icon: Icon, premium }) => {
                  const locked = premium && !isPremium;
                  return (
                    <button key={id} onClick={() => setHTab(id)} style={{
                      display: 'flex', alignItems: 'center', gap: '0.4rem',
                      padding: '0.6rem 1rem', background: 'none', border: 'none',
                      cursor: 'pointer', fontSize: '0.875rem', fontWeight: 600,
                      color: hTab === id ? 'var(--text-primary)' : 'var(--text-muted)',
                      borderBottom: `2px solid ${hTab === id ? H_ACCENT : 'transparent'}`,
                      marginBottom: -1, transition: 'color 0.15s', opacity: locked ? 0.6 : 1,
                    }}>
                      <Icon size={14} />
                      {label}
                      {locked && <Lock size={11} style={{ opacity: 0.6 }} />}
                    </button>
                  );
                })}
              </div>

              {/* Tab content */}
              <AnimatePresence mode="wait">
                <motion.div key={hTab} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.2 }}>
                  {hTab === 'picks' && (
                    <>
                      {hLoading && <SkeletonList accent={H_ACCENT} />}
                      {hError && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '1.25rem 1.5rem', borderRadius: 12, border: `1px solid ${H_ACCENT_BORDER}`, background: H_ACCENT_BG, color: H_ACCENT }}>
                          <AlertCircle size={18} />
                          <div>
                            <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>API unreachable</div>
                            <div style={{ fontSize: '0.78rem', opacity: 0.8, marginTop: 2 }}>{hError} — make sure the backend is running on port 5000.</div>
                          </div>
                        </div>
                      )}
                      {!hLoading && !hError && (
                        <>
                          {(() => {
                            const edgePicks    = hPicks.filter(p => !p.locked && p.has_line !== false && p.recommendation !== 'PASS');
                            const passPicks    = hPicks.filter(p => !p.locked && p.has_line !== false && p.recommendation === 'PASS');
                            const noLinedPicks = hPicks.filter(p => p.has_line === false);
                            const lockedPicks  = hPicks.filter(p => p.locked);
                            return (
                              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
                                {edgePicks.map((pick, i) => (
                                  <HittingPickCard key={pick.batter_name} pick={pick} index={i} />
                                ))}
                                {passPicks.length > 0 && (
                                  <>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', margin: '0.4rem 0' }}>
                                      <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
                                      <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', whiteSpace: 'nowrap' }}>No edge — model output only</span>
                                      <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
                                    </div>
                                    {passPicks.map((pick, i) => (
                                      <div key={pick.batter_name} style={{ opacity: 0.55 }}>
                                        <HittingPickCard pick={pick} index={edgePicks.length + i} />
                                      </div>
                                    ))}
                                  </>
                                )}
                                {noLinedPicks.length > 0 && (
                                  <>
                                    {(edgePicks.length > 0 || passPicks.length > 0) && (
                                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', margin: '0.4rem 0' }}>
                                        <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
                                        <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', whiteSpace: 'nowrap' }}>Line unavailable</span>
                                        <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
                                      </div>
                                    )}
                                    {noLinedPicks.map((pick, i) => (
                                      <HittingPickCard key={pick.batter_name} pick={pick} index={edgePicks.length + passPicks.length + i} />
                                    ))}
                                  </>
                                )}
                                {lockedPicks.length > 0 && (
                                  <>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', margin: '0.4rem 0' }}>
                                      <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
                                      <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', whiteSpace: 'nowrap' }}>Locked picks</span>
                                      <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
                                    </div>
                                    {lockedPicks.map((pick, i) => (
                                      <div key={pick.batter_name} style={{ padding: '1rem 1.5rem', borderRadius: 12, border: '1px solid var(--border)', background: 'var(--bg-card)', opacity: 0.5, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                        <span style={{ fontWeight: 600 }}>{pick.batter_name}</span>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                          <Lock size={13} style={{ color: H_ACCENT }} />
                                          <motion.button whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.97 }} onClick={handleUpgrade}
                                            style={{ padding: '0.25rem 0.65rem', borderRadius: 6, border: `1px solid ${H_ACCENT_BORDER}`, background: H_ACCENT_BG, color: H_ACCENT, fontSize: '0.75rem', fontWeight: 700, cursor: 'pointer' }}>
                                            Upgrade
                                          </motion.button>
                                        </div>
                                      </div>
                                    ))}
                                  </>
                                )}
                                {hPicks.length === 0 && (
                                  <div style={{ textAlign: 'center', padding: '3rem 1rem', color: 'var(--text-muted)' }}>
                                    <Flame size={32} style={{ marginBottom: '0.75rem', opacity: 0.3, color: H_ACCENT }} />
                                    <p>No hitting data yet — check back after lineups are posted.</p>
                                  </div>
                                )}
                              </div>
                            );
                          })()}
                        </>
                      )}
                    </>
                  )}
                  {(hTab === 'performance' || hTab === 'history') && !isPremium
                    ? <PremiumGate onUpgrade={handleUpgrade} upgrading={upgrading} accent={H_ACCENT} />
                    : <>
                        {hTab === 'performance' && <HittingPerformancePanel />}
                        {hTab === 'history' && (
                          <HittingHistoryLog
                            records={hHistoryRecords}
                            skippedRecords={hSkippedRecords}
                            loading={hHistoryLoading}
                            onDeleteRecord={(date, name) => setHHistoryRecords(prev => prev.filter(r => !(r.date === date && r.batter_name === name)))}
                          />
                        )}
                      </>
                  }
                </motion.div>
              </AnimatePresence>
            </motion.div>
          )}

        </AnimatePresence>
      </div>
    </div>
  );
}

function PremiumGate({ onUpgrade, upgrading, accent = 'var(--accent-blue)' }) {
  const bgColor = accent === 'var(--accent-blue)' ? 'rgba(29,155,240,0.1)' : 'rgba(249,115,22,0.1)';
  const gradStart = accent === 'var(--accent-blue)' ? '#1d9bf0' : '#f97316';
  const gradEnd   = accent === 'var(--accent-blue)' ? '#0066cc' : '#c2410c';
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      style={{ textAlign: 'center', padding: '4rem 2rem', borderRadius: 16, border: '1px solid var(--border)', background: 'var(--bg-card)' }}
    >
      <div style={{ width: 56, height: 56, borderRadius: '50%', margin: '0 auto 1.25rem', background: bgColor, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Lock size={24} color={accent} />
      </div>
      <h3 style={{ fontSize: '1.2rem', fontWeight: 700, marginBottom: '0.6rem' }}>Premium Feature</h3>
      <p style={{ color: 'var(--text-secondary)', maxWidth: 380, margin: '0 auto 1.5rem', lineHeight: 1.6, fontSize: '0.9rem' }}>
        Upgrade to StrikeEdge Premium to access full history, performance analytics, and all daily picks.
      </p>
      <motion.button
        whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.97 }}
        onClick={onUpgrade}
        disabled={upgrading}
        style={{ padding: '0.7rem 1.75rem', borderRadius: 8, border: 'none', background: `linear-gradient(135deg, ${gradStart}, ${gradEnd})`, color: '#fff', fontSize: '0.95rem', fontWeight: 700, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}
      >
        <Zap size={16} />
        {upgrading ? 'Redirecting…' : 'Upgrade — $25 CAD/month'}
      </motion.button>
    </motion.div>
  );
}

function SkeletonList({ accent = null }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
      {[0, 1, 2].map(i => (
        <motion.div
          key={i}
          animate={{ opacity: [0.4, 0.7, 0.4] }}
          transition={{ duration: 1.4, repeat: Infinity, delay: i * 0.12 }}
          style={{ height: 90, borderRadius: 12, background: 'var(--bg-card)', border: `1px solid ${accent ? 'rgba(249,115,22,0.2)' : 'var(--border)'}` }}
        />
      ))}
    </div>
  );
}
